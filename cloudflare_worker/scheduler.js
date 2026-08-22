/**
 * Cloudflare Worker: Scheduler Logic Module (Authoritative GHA Cooldown Engine)
 */
import { trackSkillMap, trackDisplayNames } from "./config.js";
import { sendTelegram } from "./telegram.js";
import { triggerGitHubWorkflow, getLatestRun } from "./github.js";

export async function handleScheduled(env) {
  try {
    const token = env.TELEGRAM_BOT_TOKEN ? env.TELEGRAM_BOT_TOKEN.trim() : "";
    const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
    const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
    const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
    const allowedUserChatId = (env.ALLOWED_TELEGRAM_CHAT_ID || env.ALLOWED_TELEGRAM_USER_ID || "").trim();

    // 1. Get current IST time (UTC + 5:30)
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const nowIst = new Date(now.getTime() + istOffset);
    const hour = nowIst.getUTCHours();
    
    // 2. Fetch scheduler_state.json from GitHub Content API
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
      console.warn("[AUTO-LOOP] Non-fatal: Failed to fetch state from GitHub, using defaults:", err);
    }
    
    if (state.enabled === false) {
      console.log("[AUTO-LOOP] Scheduler is disabled in state.");
      return;
    }

    // Dynamic config parsing
    const config = state.config || {};
    const startHour = config.start_hour_ist !== undefined ? config.start_hour_ist : 3;
    const endHour = config.end_hour_ist !== undefined ? config.end_hour_ist : 8;
    const testMode = config.test_mode === true || !!state.override;
    const withinWindow = testMode || (hour >= startHour && hour < endHour);
    
    // 3. Authoritative check on GitHub Actions (Zero file persistence needed!)
    const latestRun = await getLatestRun(pat, repo, workflow);
    
    if (latestRun) {
      const status = latestRun.status;
      const conclusion = latestRun.conclusion;

      // Gating A: If a run is currently active, WAIT!
      if (status === "in_progress" || status === "queued") {
        console.log(`[AUTO-LOOP] Run #${latestRun.run_number} is currently ${status}. Waiting...`);
        return;
      }

      // Gating B: Authoritative Cooldown Check (Based on real GHA completion timestamp)
      const finishedTimestamp = Date.parse(latestRun.updated_at || latestRun.created_at);
      const elapsedMins = (Date.now() - finishedTimestamp) / (60 * 1000);
      
      const minCool = config.min_cooldown_mins !== undefined ? config.min_cooldown_mins : 10;
      
      if (elapsedMins < minCool && !state.override) {
        console.log(`[AUTO-LOOP] Cooldown active: Run #${latestRun.run_number} finished ${elapsedMins.toFixed(1)} mins ago. Minimum cooldown is ${minCool} mins. Waiting...`);
        return;
      }
    }
    
    // 4. Time Window Gating Check
    if (!withinWindow) {
      console.log(`[AUTO-LOOP] Outside active ${startHour}:00 - ${endHour}:00 IST window.`);
      return;
    }
    
    // 5. Select Track (Check Override vs Dynamic Mastery Ranking)
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
        console.warn("[AUTO-LOOP] Non-fatal: Failed to fetch learned_skills.json:", err);
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
    
    // 6. Generate dynamic session duration (Check Override vs Random Range)
    let durationMins = state.override && state.override.duration ? parseInt(state.override.duration) : null;
    if (!durationMins || isNaN(durationMins)) {
      const minDur = config.min_duration !== undefined ? config.min_duration : 50;
      const maxDur = config.max_duration !== undefined ? config.max_duration : 85;
      durationMins = Math.floor(Math.random() * (maxDur - minDur + 1)) + minDur;
    }
    
    // 7. Dispatch GHA run
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, selectedTrack, durationMins);
    if (ok) {
      console.log(`[AUTO-LOOP] Successfully dispatched session for track '${selectedTrack}' with duration ${durationMins}m`);
      
      if (allowedUserChatId) {
        await sendTelegram(token, "sendMessage", {
          chat_id: allowedUserChatId,
          text: `🎯 <b>[AUTO-LOOP] Triggered session:</b>\n• <b>Track:</b> ${trackDisplay}\n• <b>Duration:</b> ${durationMins} minutes\n\nGitHub Actions runner is booting up...`,
          parse_mode: "HTML"
        });
      }
    } else {
      console.error("[AUTO-LOOP] Failed to trigger GitHub Actions workflow.");
    }
  } catch (err) {
    console.error("[AUTO-LOOP] Uncaught error in scheduler execution:", err);
  }
}
