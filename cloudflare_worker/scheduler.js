/**
 * Cloudflare Worker: Scheduler Logic Module (Fully Dynamic State-Driven)
 */
import { trackSkillMap, trackDisplayNames } from "./config.js";
import { sendTelegram } from "./telegram.js";
import { triggerGitHubWorkflow, getRunningRuns, updateSchedulerState } from "./github.js";

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
    let state = null;
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
      } else {
        console.error(`[AUTO-LOOP] Failed to fetch scheduler_state.json. HTTP status: ${r.status}`);
      }
    } catch (err) {
      console.error("[AUTO-LOOP] Failed to fetch scheduler_state.json:", err);
      return;
    }
    
    if (!state) {
      console.error("[AUTO-LOOP] State is null or fetch failed.");
      return;
    }
    if (state.enabled !== true) {
      console.log("[AUTO-LOOP] Scheduler is disabled in state.");
      return;
    }

    // Dynamic config parsing
    const config = state.config || {};
    const startHour = config.start_hour_ist !== undefined ? config.start_hour_ist : 3;
    const endHour = config.end_hour_ist !== undefined ? config.end_hour_ist : 8;
    const testMode = config.test_mode === true || !!state.override;
    const withinWindow = testMode || (hour >= startHour && hour < endHour);
    
    // 3. Query GitHub Actions to check active run (Authoritative check)
    const activeRuns = await getRunningRuns(pat, repo, workflow);
    const hasActiveRun = (activeRuns && activeRuns.length > 0);
    
    // Check if we have an active run tracked in state
    if (state.active_run_id) {
      try {
        const checkRes = await fetch(`https://api.github.com/repos/${repo}/actions/runs/${state.active_run_id}`, {
          headers: {
            "Authorization": `Bearer ${pat}`,
            "Accept": "application/vnd.github+json",
            "User-Agent": "cloudflare-worker-obo"
          }
        });
        if (checkRes.ok) {
          const runInfo = await checkRes.json();
          const status = runInfo.status;
          const conclusion = runInfo.conclusion;
          
          if (status === "completed") {
            console.log(`[AUTO-LOOP] Run ${state.active_run_id} completed with conclusion: ${conclusion}`);
            
            let consecutive_failures = state.consecutive_failures || 0;
            let enabled = state.enabled;
            let last_run_status = conclusion;
            
            if (conclusion === "success") {
              consecutive_failures = 0;
            } else if (conclusion === "cancelled") {
              // User stopped or manual cancellation, don't increment failure counter
            } else {
              // Infrastructure error or timeout
              consecutive_failures += 1;
              if (consecutive_failures >= 2) {
                enabled = false;
                if (allowedUserChatId) {
                  await sendTelegram(token, "sendMessage", {
                    chat_id: allowedUserChatId,
                    text: `⚠️ <b>[AUTO-LOOP] Emergency Stop!</b>\n\n2 consecutive infrastructure failures detected (last run: ${conclusion}).\nAuto-Loop has been disabled.`,
                    parse_mode: "HTML"
                  });
                }
              }
            }
            
            // Dynamic cooldown calculation (Default 10 to 17 mins)
            const minCool = config.min_cooldown_mins !== undefined ? config.min_cooldown_mins : 10;
            const maxCool = config.max_cooldown_mins !== undefined ? config.max_cooldown_mins : 17;
            const coolingMins = Math.floor(Math.random() * (maxCool - minCool + 1)) + minCool;
            const nextAllowed = Date.now() + coolingMins * 60 * 1000;
            
            try {
              await updateSchedulerState(pat, repo, (s) => {
                s.active_run_id = null;
                s.active_run_started_at = null;
                s.consecutive_failures = consecutive_failures;
                s.enabled = enabled;
                s.last_run_status = last_run_status;
                s.last_run_finished_at = Date.now();
                s.next_run_allowed_epoch = nextAllowed;
                return s;
              });
            } catch (err) {
              console.error("[AUTO-LOOP] Failed to write scheduler state (completion check):", err);
            }
            
            if (allowedUserChatId) {
              await sendTelegram(token, "sendMessage", {
                chat_id: allowedUserChatId,
                text: `✅ <b>[AUTO-LOOP] Session finished: ${conclusion}</b>\n\nCooling down for ${coolingMins} minutes before checking next window.`,
                parse_mode: "HTML"
              });
            }
            return;
          } else {
            console.log(`[AUTO-LOOP] Run ${state.active_run_id} is still in status: ${status}`);
            return;
          }
        } else if (checkRes.status === 404) {
          console.warn(`[AUTO-LOOP] Run ${state.active_run_id} not found. Reconciling state.`);
          try {
            await updateSchedulerState(pat, repo, (s) => {
              s.active_run_id = null;
              s.active_run_started_at = null;
              s.next_run_allowed_epoch = Date.now() + 5 * 60 * 1000; // 5 min cooldown
              return s;
            });
          } catch (err) {
            console.error("[AUTO-LOOP] Failed to write scheduler state (reconcile check):", err);
          }
          return;
        }
      } catch (e) {
        console.error("[AUTO-LOOP] Error checking GHA active run:", e);
        return;
      }
    }
    
    if (hasActiveRun) {
      console.log("[AUTO-LOOP] An active run is running on GHA, waiting...");
      return;
    }
    
    // 4. Cooldown and Time Window Gating Check
    if (Date.now() < (state.next_run_allowed_epoch || 0) && !state.override) {
      console.log("[AUTO-LOOP] Cooldown period active.");
      return;
    }
    
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
        console.error("[AUTO-LOOP] Failed to fetch learned_skills.json:", err);
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
      await new Promise(r => setTimeout(r, 10000));
      const runs = await getRunningRuns(pat, repo, workflow);
      const newRunId = (runs && runs.length > 0) ? runs[0].id : null;
      
      try {
        await updateSchedulerState(pat, repo, (s) => {
          s.active_run_id = newRunId;
          s.active_run_started_at = Date.now();
          // Clear one-time override once triggered
          if (s.override) {
            s.override = null;
          }
          return s;
        });
      } catch (err) {
        console.error("[AUTO-LOOP] Failed to write scheduler state (dispatch update):", err);
      }
      
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
