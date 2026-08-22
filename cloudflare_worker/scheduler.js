/**
 * Cloudflare Worker: Scheduler Logic Module
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
    
    // Gating window: 3:00 AM - 8:00 AM IST (Set to true for testing mode)
    const withinWindow = true;
    
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
                    text: `⚠️ *[AUTO-LOOP] Emergency Stop!*\n\n2 consecutive infrastructure failures detected (last run: ${conclusion}).\nAuto-Loop has been disabled.`,
                    parse_mode: "Markdown"
                  });
                }
              }
            }
            
            // Clear active run ID and set cooldown
            const coolingMins = Math.floor(Math.random() * (18 - 10 + 1)) + 10; // 10 to 18 minutes random
            const nextAllowed = Date.now() + coolingMins * 60 * 1000;
            
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
            
            if (allowedUserChatId) {
              await sendTelegram(token, "sendMessage", {
                chat_id: allowedUserChatId,
                text: `✅ *[AUTO-LOOP] Session finished: ${conclusion}*\n\nCooling down for ${coolingMins} minutes before checking next window.`,
                parse_mode: "Markdown"
              });
            }
            return;
          } else {
            console.log(`[AUTO-LOOP] Run ${state.active_run_id} is still in status: ${status}`);
            return;
          }
        } else if (checkRes.status === 404) {
          console.warn(`[AUTO-LOOP] Run ${state.active_run_id} not found. Reconciling state.`);
          await updateSchedulerState(pat, repo, (s) => {
            s.active_run_id = null;
            s.active_run_started_at = null;
            s.next_run_allowed_epoch = Date.now() + 5 * 60 * 1000; // 5 min cooldown
            return s;
          });
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
    if (Date.now() < state.next_run_allowed_epoch) {
      console.log("[AUTO-LOOP] Cooldown period active.");
      return;
    }
    
    if (!withinWindow) {
      console.log("[AUTO-LOOP] Outside active 3:00 AM - 8:00 AM IST window.");
      return;
    }
    
    // 5. Select Track using Top 3 Priority Filter
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
    const selectedTrack = selectedTrackObj.key;
    const trackDisplay = trackDisplayNames[selectedTrack] || selectedTrack;
    
    // 6. Generate dynamic session duration
    let durationMins = Math.floor(Math.random() * (92 - 22 + 1)) + 22; // 22 to 92 mins
    
    // 7. Dispatch GHA run
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, selectedTrack, durationMins);
    if (ok) {
      await new Promise(r => setTimeout(r, 10000));
      const runs = await getRunningRuns(pat, repo, workflow);
      const newRunId = (runs && runs.length > 0) ? runs[0].id : null;
      
      await updateSchedulerState(pat, repo, (s) => {
        s.active_run_id = newRunId;
        s.active_run_started_at = Date.now();
        return s;
      });
      
      if (allowedUserChatId) {
        await sendTelegram(token, "sendMessage", {
          chat_id: allowedUserChatId,
          text: `🎯 *[AUTO-LOOP] Triggered session:*\n• *Track:* ${trackDisplay}\n• *Duration:* ${durationMins} minutes\n\nGitHub Actions runner is booting up...`,
          parse_mode: "Markdown"
        });
      }
    } else {
      console.error("[AUTO-LOOP] Failed to trigger GitHub Actions workflow.");
    }
  } catch (err) {
    console.error("[AUTO-LOOP] Uncaught error in scheduler execution:", err);
  }
}
