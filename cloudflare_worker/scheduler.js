/**
 * Cloudflare Worker: Automated Cron Job Scheduler
 * Reads configuration directly from data/scheduler_state.json
 */
import { trackSkillMap, trackDisplayNames } from "./config.js";
import { sendTelegram } from "./telegram.js";
import { triggerGitHubWorkflow, getLatestRun } from "./github.js";

/**
 * Converts "HH:MM" or hour numbers into minutes from midnight.
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

    // 1. Current IST time (UTC + 5:30)
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const nowIst = new Date(now.getTime() + istOffset);
    const currentIstMinutes = nowIst.getUTCHours() * 60 + nowIst.getUTCMinutes();
    const currentIstTimeStr = `${String(nowIst.getUTCHours()).padStart(2, '0')}:${String(nowIst.getUTCMinutes()).padStart(2, '0')}`;

    // 2. Read state directly from data/scheduler_state.json
    let state = {
      enabled: true,
      start_time_ist: "03:00",
      end_time_ist: "08:00",
      min_duration_mins: 22,
      max_duration_mins: 92,
      min_cooldown_mins: 10,
      max_cooldown_mins: 18,
      test_mode: false
    };

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
        const parsed = JSON.parse(decoded);
        state = Object.assign(state, parsed);
      }
    } catch (err) {
      console.warn("[AUTO-CRON] State fetch notice:", err);
    }
    
    if (state.enabled === false) {
      console.log("[AUTO-CRON] Scheduler is disabled in data/scheduler_state.json.");
      return;
    }

    // 3. Time Window Gating Check
    const startMinutes = parseTimeToMinutes(state.start_time_ist, 3 * 60);
    const endMinutes = parseTimeToMinutes(state.end_time_ist, 8 * 60);
    
    let withinWindow = false;
    if (startMinutes <= endMinutes) {
      withinWindow = (currentIstMinutes >= startMinutes && currentIstMinutes < endMinutes);
    } else {
      // Overnight window (e.g. 23:00 to 04:00)
      withinWindow = (currentIstMinutes >= startMinutes || currentIstMinutes < endMinutes);
    }

    const isAllowedToRun = state.test_mode === true || withinWindow;

    // 4. Authoritative Check on GitHub Actions
    const latestRun = await getLatestRun(pat, repo, workflow);
    
    if (latestRun) {
      const status = latestRun.status;
      
      // If a run is currently in progress, wait
      if (status === "in_progress" || status === "queued") {
        console.log(`[AUTO-CRON] Run #${latestRun.run_number} is currently active (${status}). Waiting...`);
        return;
      }

      // Authoritative Cooldown Pause Calculation
      const finishedTimestamp = Date.parse(latestRun.updated_at || latestRun.created_at);
      const elapsedMins = (Date.now() - finishedTimestamp) / (60 * 1000);
      
      const minCool = state.min_cooldown_mins !== undefined ? state.min_cooldown_mins : 10;
      
      if (elapsedMins < minCool) {
        const remaining = (minCool - elapsedMins).toFixed(1);
        console.log(`[AUTO-CRON] In Cooldown: ${remaining}m remaining of ${minCool}m pause. Waiting...`);
        return;
      }
    }
    
    // 5. If outside window, wait
    if (!isAllowedToRun) {
      console.log(`[AUTO-CRON] Outside active window (${currentIstTimeStr} IST). Scheduled: ${state.start_time_ist} - ${state.end_time_ist} IST.`);
      return;
    }
    
    // 6. Select Track
    let selectedTrack = state.track && state.track !== "auto" ? state.track : null;

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
        console.warn("[AUTO-CRON] Skills fetch notice:", err);
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
    
    // 7. Calculate Duration (Random range or fixed)
    const minDur = state.min_duration_mins !== undefined ? state.min_duration_mins : 22;
    const maxDur = state.max_duration_mins !== undefined ? state.max_duration_mins : 92;
    const durationMins = minDur === maxDur ? minDur : Math.floor(Math.random() * (maxDur - minDur + 1)) + minDur;
    
    // 8. Trigger Session on GitHub Actions
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, selectedTrack, durationMins);
    if (ok) {
      console.log(`[AUTO-CRON] Triggered session: Track '${selectedTrack}', Duration ${durationMins}m`);
      
      if (allowedUserChatId) {
        await sendTelegram(token, "sendMessage", {
          chat_id: allowedUserChatId,
          text: `🎯 <b>[AUTO-LOOP] Session Started:</b>\n• <b>Track:</b> ${trackDisplay}\n• <b>Duration:</b> ${durationMins} minutes\n• <b>Window:</b> ${state.start_time_ist} - ${state.end_time_ist} IST\n\nGitHub Actions runner is running. Will stop automatically.`,
          parse_mode: "HTML"
        });
      }
    } else {
      console.error("[AUTO-CRON] Failed to dispatch workflow on GitHub.");
    }
  } catch (err) {
    console.error("[AUTO-CRON] Uncaught error in scheduler execution:", err);
  }
}
