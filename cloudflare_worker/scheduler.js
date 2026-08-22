/**
 * Cloudflare Worker: Dynamic Precision Scheduler & Auto-Loop Engine
 */
import { trackSkillMap, trackDisplayNames } from "./config.js";
import { sendTelegram } from "./telegram.js";
import { triggerGitHubWorkflow, getLatestRun } from "./github.js";

/**
 * Parses time string (e.g. "03:00", "23:45", or hour number 3) into minutes from midnight.
 */
function parseTimeToMinutes(val, defaultMinutes) {
  if (val === undefined || val === null) return defaultMinutes;
  if (typeof val === "number") return val * 60;
  const str = String(val).trim();
  if (str.includes(":")) {
    const parts = str.split(":");
    const h = parseInt(parts[0], 10) || 0;
    const m = parseInt(parts[1], 10) || 0;
    return h * 60 + m;
  }
  const h = parseInt(str, 10);
  return isNaN(h) ? defaultMinutes : h * 60;
}

export async function handleScheduled(env) {
  try {
    const token = env.TELEGRAM_BOT_TOKEN ? env.TELEGRAM_BOT_TOKEN.trim() : "";
    const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
    const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
    const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
    const allowedUserChatId = (env.ALLOWED_TELEGRAM_CHAT_ID || env.ALLOWED_TELEGRAM_USER_ID || "").trim();

    // 1. Get current IST time (UTC + 5:30) in minutes from midnight
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const nowIst = new Date(now.getTime() + istOffset);
    const currentIstMinutes = nowIst.getUTCHours() * 60 + nowIst.getUTCMinutes();
    const currentIstTimeStr = `${String(nowIst.getUTCHours()).padStart(2, '0')}:${String(nowIst.getUTCMinutes()).padStart(2, '0')}`;

    // 2. Fetch scheduler_state.json from GitHub Content API (Live Dynamic Config)
    let state = { enabled: true, config: {}, override: null };
    try {
      const r = await fetch(`https://api.github.com/repos/${repo}/contents/data/scheduler_state.json`, {
        headers: {
          "Authorization": `Bearer ${pat}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "cloudflare-worker-obo"
        }
      });
      if (r.ok) {
        const fileData = await r.json();
        const decoded = atob(fileData.content.replace(/\s/g, ""));
        state = JSON.parse(decoded);
      }
    } catch (err) {
      console.warn("[AUTO-LOOP] Non-fatal: State fetch notice:", err);
    }
    
    if (state.enabled === false) {
      console.log("[AUTO-LOOP] Scheduler is disabled.");
      return;
    }

    const config = state.config || {};
    
    // Dynamic Time Window Parsing (Supports "HH:MM" or hour numbers)
    const startMinutes = parseTimeToMinutes(config.start_time || config.start_hour_ist, 3 * 60); // Default 03:00 IST
    const endMinutes = parseTimeToMinutes(config.end_time || config.end_hour_ist, 8 * 60);       // Default 08:00 IST
    
    let withinWindow = false;
    if (startMinutes <= endMinutes) {
      withinWindow = (currentIstMinutes >= startMinutes && currentIstMinutes < endMinutes);
    } else {
      // Handles overnight windows like 22:00 to 04:00
      withinWindow = (currentIstMinutes >= startMinutes || currentIstMinutes < endMinutes);
    }

    const testMode = config.test_mode === true || !!state.override;
    const isAllowedToRun = testMode || withinWindow;

    // 3. Authoritative check on GitHub Actions
    const latestRun = await getLatestRun(pat, repo, workflow);
    
    if (latestRun) {
      const status = latestRun.status;
      
      // Gating A: If a run is currently in progress, wait!
      if (status === "in_progress" || status === "queued") {
        console.log(`[AUTO-LOOP] Run #${latestRun.run_number} is in progress (${status}). Waiting for completion...`);
        return;
      }

      // Gating B: Authoritative Cooldown Engine
      const finishedTimestamp = Date.parse(latestRun.updated_at || latestRun.created_at);
      const elapsedMins = (Date.now() - finishedTimestamp) / (60 * 1000);
      
      const minCool = config.min_cooldown_mins !== undefined ? config.min_cooldown_mins : 10;
      const maxCool = config.max_cooldown_mins !== undefined ? config.max_cooldown_mins : 18;
      
      // Calculate target cooldown pause
      const targetCooldown = state.active_cooling_duration || minCool;
      
      if (elapsedMins < targetCooldown && !state.override) {
        const remainingMins = (targetCooldown - elapsedMins).toFixed(1);
        console.log(`[AUTO-LOOP] Cooldown Active: ${remainingMins}m remaining of ${targetCooldown}m pause. Waiting...`);
        return;
      }
    }
    
    // 4. Time Window Check
    if (!isAllowedToRun) {
      console.log(`[AUTO-LOOP] Outside active window (${currentIstTimeStr} IST). Scheduled window: ${Math.floor(startMinutes/60)}:${String(startMinutes%60).padStart(2,'0')} - ${Math.floor(endMinutes/60)}:${String(endMinutes%60).padStart(2,'0')} IST.`);
      return;
    }
    
    // 5. Select Track
    let selectedTrack = state.override && state.override.track && state.override.track !== "auto" ? state.override.track : null;

    if (!selectedTrack) {
      let skills = {};
      try {
        const skillRes = await fetch(`https://api.github.com/repos/${repo}/contents/data/learned_skills.json`, {
          headers: {
            "Authorization": `Bearer ${pat}`,
            "Accept": "application/vnd.github+json",
            "User-Agent": "cloudflare-worker-obo"
          }
        });
        if (skillRes.ok) {
          const fileData = await skillRes.json();
          const decoded = atob(fileData.content.replace(/\s/g, ""));
          skills = JSON.parse(decoded);
        }
      } catch (err) {
        console.warn("[AUTO-LOOP] Non-fatal: Learned skills fetch notice:", err);
      }
      
      const trackLevels = [];
      for (const [trackKey, mappings] of Object.entries(trackSkillMap)) {
        let sum = 0;
        for (const [shortName, longName] of mappings) {
          sum += skills[longName] !== undefined ? skills[longName] : 1;
        }
        const avg = sum / mappings.length;
        trackLevels.push({ key: trackKey, avg: avg });
      }
      
      trackLevels.sort((a, b) => b.avg - a.avg);
      const top3 = trackLevels.slice(0, 3);
      const selectedTrackObj = top3[Math.floor(Math.random() * top3.length)];
      selectedTrack = selectedTrackObj ? selectedTrackObj.key : "cpp";
    }

    const trackDisplay = trackDisplayNames[selectedTrack] || selectedTrack;
    
    // 6. Dynamic Duration Calculation
    let durationMins = state.override && state.override.duration ? parseInt(state.override.duration) : null;
    if (!durationMins || isNaN(durationMins)) {
      const minDur = config.min_duration !== undefined ? config.min_duration : 22;
      const maxDur = config.max_duration !== undefined ? config.max_duration : 92;
      durationMins = Math.floor(Math.random() * (maxDur - minDur + 1)) + minDur;
    }
    
    // 7. Dispatch GHA Session
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, selectedTrack, durationMins);
    if (ok) {
      console.log(`[AUTO-LOOP] Dispatched session: Track '${selectedTrack}', Duration ${durationMins}m`);
      
      if (allowedUserChatId) {
        await sendTelegram(token, "sendMessage", {
          chat_id: allowedUserChatId,
          text: `🎯 <b>[AUTO-LOOP] Session Started:</b>\n• <b>Track:</b> ${trackDisplay}\n• <b>Duration:</b> ${durationMins} minutes\n• <b>Window:</b> ${config.start_time || '03:00'} - ${config.end_time || '08:00'} IST\n\nRunner is active. Auto-stopping at completion.`,
          parse_mode: "HTML"
        });
      }
    } else {
      console.error("[AUTO-LOOP] Failed to trigger GitHub Actions workflow.");
    }
  } catch (err) {
    console.error("[AUTO-LOOP] Uncaught scheduler error:", err);
  }
}
