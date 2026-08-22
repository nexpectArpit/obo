/**
 * Cloudflare Worker: Telegram Webhook Controller for Oboe Agent
 * 
 * Security Features:
 * 1. Verifies X-Telegram-Bot-Api-Secret-Token header matching env.TELEGRAM_SECRET_TOKEN.
 * 2. Validates user ID against env.ALLOWED_TELEGRAM_USER_ID.
 * 3. Triggers GitHub Actions workflow_dispatch API using fine-grained PAT.
 */

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("Oboe Cloudflare Telegram Worker Active", { status: 200 });
    }

    // 1. Verify Telegram Webhook Secret Token
    const incomingSecret = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "").trim();
    const secretToken = (env.TELEGRAM_SECRET_TOKEN || "").trim();
    if (secretToken && incomingSecret !== secretToken) {
      console.warn(`Unauthorized webhook request: secret token mismatch (got '${incomingSecret}', expected '${secretToken}')`);
      return new Response("Forbidden", { status: 403 });
    }

    try {
      const update = await request.json();
      await handleUpdate(update, env);
    } catch (err) {
      console.error("Error handling update:", err);
    }

    return new Response("OK", { status: 200 });
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(handleScheduled(env));
  }
};

const trackSkillMap = {
  "cpp": [["DP", "Dynamic Programming"], ["Algo", "Algorithms"]],
  "arch": [["Mem", "Memory Systems"], ["Arch", "Computer Architecture"]],
  "os": [["SysCall", "System Calls"], ["OS", "Operating Systems"]],
  "ds": [["ML", "Machine Learning"], ["Hyp", "Hypothesis Testing"]],
  "dl": [["DL", "Deep Learning"], ["NN", "Neural Networks"]],
  "maths": [["Alg", "Algebra"], ["Opt", "Optimization"]]
};

async function getDynamicTracksKeyboard(pat, repo) {
  let skills = {};
  try {
    const r = await fetch(`https://api.github.com/repos/${repo}/contents/data/learned_skills.json`, {
      headers: {
        "Authorization": `Bearer ${pat}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "cloudflare-worker-obo"
      }
    });
    if (r.ok) {
      const fileData = await r.json();
      const decoded = atob(fileData.content.replace(/\s/g, ""));
      skills = JSON.parse(decoded);
    }
  } catch (err) {
    console.error("Failed to load dynamic skill levels from GitHub:", err);
  }

  function getBtnText(label, trackKey) {
    const mappings = trackSkillMap[trackKey] || [];
    const levels = [];
    for (const [shortName, longName] of mappings) {
      const lvl = skills[longName] !== undefined ? skills[longName] : 1;
      levels.push(String(lvl));
    }
    if (levels.length > 0) {
      return `${label} (${levels.join(", ")})`;
    }
    return label;
  }

  return {
    inline_keyboard: [
      [{ text: getBtnText("1. CP / DSA", "cpp"), callback_data: "pin_cpp" }, { text: getBtnText("2. Arch & Net", "arch"), callback_data: "pin_arch" }],
      [{ text: getBtnText("3. OS", "os"), callback_data: "pin_os" }, { text: getBtnText("4. Data Science", "ds"), callback_data: "pin_ds" }],
      [{ text: getBtnText("5. DL", "dl"), callback_data: "pin_dl" }, { text: getBtnText("6. Maths for DS", "maths"), callback_data: "pin_maths" }],
      [{ text: "⬅️ Back to Menu", callback_data: "back_to_menu" }]
    ]
  };
}

async function getMenuKeyboard(pat, repo) {
  let enabled = false;
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
      const state = JSON.parse(decoded);
      enabled = state.enabled === true;
    }
  } catch (e) {
    console.error("Failed to fetch scheduler_state.json:", e);
  }
  
  const loopText = enabled ? "⏰ Auto-Loop: ACTIVE" : "⏰ Auto-Loop: INACTIVE";
  return {
    inline_keyboard: [
      [{ text: "🚀 Start Random", callback_data: "start_random" }, { text: "📈 Focus Pinned Track", callback_data: "level_up" }],
      [{ text: "📚 Start Topic", callback_data: "start_topic" }, { text: "🔄 Resume Last", callback_data: "resume" }],
      [{ text: "🛑 Stop Agent", callback_data: "stop" }, { text: "📊 Status", callback_data: "status" }],
      [{ text: loopText, callback_data: "toggle_auto_loop" }]
    ]
  };
}

async function updateSchedulerState(pat, repo, updateFn) {
  let attempts = 0;
  while (attempts < 3) {
    try {
      const getRes = await fetch(`https://api.github.com/repos/${repo}/contents/data/scheduler_state.json`, {
        headers: {
          "Authorization": `Bearer ${pat}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "cloudflare-worker-obo"
        }
      });
      if (!getRes.ok) {
        throw new Error(`Failed to fetch scheduler_state.json: ${getRes.status}`);
      }
      const fileData = await getRes.json();
      const sha = fileData.sha;
      const decoded = atob(fileData.content.replace(/\s/g, ""));
      const state = JSON.parse(decoded);
      
      const updatedState = updateFn(state);
      
      const putRes = await fetch(`https://api.github.com/repos/${repo}/contents/data/scheduler_state.json`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${pat}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "cloudflare-worker-obo",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: "chore(scheduler): update scheduler state",
          content: btoa(JSON.stringify(updatedState, null, 2)),
          sha: sha
        })
      });
      
      if (putRes.status === 200 || putRes.status === 201) {
        return updatedState;
      } else if (putRes.status === 409) {
        attempts++;
        await new Promise(r => setTimeout(r, 1000));
        continue;
      } else {
        const bodyText = await putRes.text();
        throw new Error(`Failed to write state: ${putRes.status} - ${bodyText}`);
      }
    } catch (err) {
      console.error(`Attempt ${attempts} failed:`, err);
      attempts++;
      if (attempts >= 3) {
        throw err;
      }
    }
  }
}

async function handleUpdate(update, env) {
  const token = env.TELEGRAM_BOT_TOKEN ? env.TELEGRAM_BOT_TOKEN.trim() : "";
  const allowedUser = env.ALLOWED_TELEGRAM_USER_ID ? String(env.ALLOWED_TELEGRAM_USER_ID).trim() : "";
  const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
  const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
  const pat = env.GH_PAT ? env.GH_PAT.trim() : "";

  let chatId = null;
  let userId = null;
  let text = null;
  let callbackQueryId = null;
  let callbackData = null;

  if (update.message) {
    chatId = update.message.chat.id;
    userId = String(update.message.from.id).trim();
    text = update.message.text;
  } else if (update.callback_query) {
    chatId = update.callback_query.message.chat.id;
    userId = String(update.callback_query.from.id).trim();
    callbackQueryId = update.callback_query.id;
    callbackData = update.callback_query.data;
  }

  // 2. Validate Telegram User Authorization
  if (userId && allowedUser && userId !== allowedUser) {
    console.warn(`Unauthorized user ID: '${userId}' (expected '${allowedUser}')`);
    if (chatId) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: `⛔ Unauthorized user (ID: ${userId}).`
      });
    }
    return;
  }

  if (callbackQueryId) {
    await sendTelegram(token, "answerCallbackQuery", { callback_query_id: callbackQueryId });
  }

  const menuKeyboard = await getMenuKeyboard(pat, repo);

  const tracksKeyboard = {
    inline_keyboard: [
      [{ text: "1. CP / DSA", callback_data: "pin_cpp" }, { text: "2. Computer Arch & Net", callback_data: "pin_arch" }],
      [{ text: "3. OS", callback_data: "pin_os" }, { text: "4. Data Science", callback_data: "pin_ds" }],
      [{ text: "5. DL", callback_data: "pin_dl" }, { text: "6. Maths for DS", callback_data: "pin_maths" }],
      [{ text: "⬅️ Back to Menu", callback_data: "back_to_menu" }]
    ]
  };

  // Handle Command /start, /menu, menu, start
  const cleanText = text ? text.trim().toLowerCase() : "";
  if (cleanText === "/start" || cleanText === "/menu" || cleanText === "menu" || cleanText === "start") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "🎵 *Oboe Cloud Agent Controller*\n\nChoose an action:",
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle Command /clear or clear (Deletes up to 300 previous messages from chat screen)
  if (cleanText === "/clear" || cleanText === "clear") {
    const currentId = update.message ? update.message.message_id : null;
    if (currentId) {
      const deletePromises = [];
      for (let i = 0; i <= 300; i++) {
        deletePromises.push(deleteTelegramMessage(token, chatId, currentId - i));
      }
      await Promise.allSettled(deletePromises);

    }
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "🧹 *Dashboard Cleared!*\n\nChoose an action:",
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle Command /topic <topic_name>
  if (cleanText.startsWith("/topic")) {
    const customTopic = text.substring(6).trim();
    if (!customTopic) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "📚 *Please specify a topic name.*\n\n*Usage:* `/topic Quantum Computing`\n*Example:* `/topic Neural Networks`",
        parse_mode: "Markdown",
        reply_markup: menuKeyboard
      });
      return;
    }

    const ok = await triggerGitHubWorkflow(pat, repo, workflow, customTopic, false, false, "none");
    const replyText = ok
      ? `📚 *Started Topic Session:* _${customTopic}_\n\nGitHub Actions runner is booting up.`
      : "❌ *Failed to trigger workflow on GitHub.*";

    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: replyText,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "back_to_menu" button
  if (callbackData === "back_to_menu") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "🎵 *Oboe Cloud Agent Controller*\n\nChoose an action:",
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "📚 Start Topic" button
  if (callbackData === "start_topic") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "📚 *Start Specific Topic*\n\nPlease reply with your desired topic using `/topic`:\n\n*Usage:* `/topic <topic_name>`\n*Example:* `/topic Quantum Computing`",
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "🚀 Start Random" button
  if (callbackData === "start_random") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, false, "none");
    
    const replyText = ok
      ? "🚀 *Random Learning Session Triggered!*\n\nGitHub Actions runner is booting up.\nYou will receive session summary when complete."
      : "❌ *Failed to trigger workflow on GitHub.* Check GH_PAT permissions.";

    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: replyText,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "📈 Focus Pinned Track" button
  if (callbackData === "level_up") {
    const dynamicKeyboard = await getDynamicTracksKeyboard(pat, repo);
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "📈 *Select Pinned Track to Focus:*\n\nChoose one of the 6 pinned tracks to run and progress in Oboe continuous chats:",
      parse_mode: "Markdown",
      reply_markup: dynamicKeyboard
    });
    return;
  }

  // Handle "pin_*" callbacks
  if (callbackData && callbackData.startsWith("pin_")) {
    const trackName = callbackData.replace("pin_", "");
    const trackDisplay = {
      cpp: "1. CP / DSA",
      arch: "2. Computer Arch & Net",
      os: "3. OS",
      ds: "4. Data Science",
      dl: "5. DL",
      maths: "6. Maths for DS"
    }[trackName] || trackName.toUpperCase();

    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, false, trackName);
    const replyText = ok
      ? `🎯 *Focus Mode active on Pinned Track: ${trackDisplay}*\n\nThe agent will open the corresponding pinned chat in the sidebar and process the next sub-topic.`
      : `❌ *Failed to trigger workflow on GitHub for ${trackDisplay}.*`;

    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: replyText,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "🔄 Resume Last" button
  if (callbackData === "resume") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", true, false, "none");
    
    const replyText = ok
      ? "🔄 *Resume Last Session Triggered!*\n\nGitHub Actions runner is resuming your previous chat."
      : "❌ *Failed to trigger workflow on GitHub.*";

    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: replyText,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "🛑 Stop Agent" button
  if (callbackData === "stop") {
    const runs = await getRunningRuns(pat, repo, workflow);
    if (!runs || runs.length === 0) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "✅ No active runs currently running on GitHub Actions.",
        reply_markup: menuKeyboard
      });
    } else {
      let count = 0;
      for (const run of runs) {
        if (await cancelRun(pat, repo, run.id)) count++;
      }
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: `🛑 *Cancelled ${count} active run(s).* Progress is being saved to main.`,
        parse_mode: "Markdown",
        reply_markup: menuKeyboard
      });
    }
    return;
  }

  // Handle "📊 Status" button
  if (callbackData === "status") {
    const runs = await getRunningRuns(pat, repo, workflow);
    let statusText = "";
    if (runs && runs.length > 0) {
      for (const r of runs) {
        statusText += await formatRunStatus(pat, repo, r);
      }
    } else {
      statusText = "📭 *No active workflow runs currently running on GitHub Actions.*";
    }
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: statusText,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle "toggle_auto_loop" button
  if (callbackData === "toggle_auto_loop") {
    try {
      const updatedState = await updateSchedulerState(pat, repo, (state) => {
        state.enabled = !(state.enabled === true);
        return state;
      });
      
      const statusMsg = updatedState.enabled 
        ? "⏰ *Auto-Loop Scheduler activated!*" 
        : "🛑 *Auto-Loop Scheduler deactivated.*";
        
      // Fetch fresh dynamic keyboard with the updated text
      const newMenuKeyboard = await getMenuKeyboard(pat, repo);
      
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: statusMsg,
        parse_mode: "Markdown",
        reply_markup: newMenuKeyboard
      });
    } catch (err) {
      console.error("Failed to toggle auto loop:", err);
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "❌ *Failed to update scheduler state.*",
        parse_mode: "Markdown",
        reply_markup: menuKeyboard
      });
    }
    return;
  }
}

// GitHub REST API Integration
async function triggerGitHubWorkflow(pat, repo, workflow, topic, resume, levelUp, pin = "none", duration = "none") {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${pat}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cloudflare-worker-obo"
    },
    body: JSON.stringify({
      ref: "main",
      inputs: {
        topic: topic,
        resume: String(resume),
        level_up: String(levelUp),
        pin: String(pin),
        duration: String(duration)
      }
    })
  });
  return r.status === 204;
}

async function getRunningRuns(pat, repo, workflow) {
  let runs = [];
  for (const status of ["in_progress", "queued"]) {
    const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/runs?status=${status}&per_page=5`;
    const r = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${pat}`,
        "Accept": "application/vnd.github+json",
        "User-Agent": "cloudflare-worker-obo"
      }
    });
    if (r.status === 200) {
      const data = await r.json();
      runs = runs.concat(data.workflow_runs || []);
    }
  }
  return runs;
}

async function cancelRun(pat, repo, runId) {
  const url = `https://api.github.com/repos/${repo}/actions/runs/${runId}/cancel`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${pat}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cloudflare-worker-obo"
    }
  });
  return r.status === 202;
}

async function formatRunStatus(pat, repo, run) {
  const jobsUrl = `https://api.github.com/repos/${repo}/actions/runs/${run.id}/jobs`;
  const r = await fetch(jobsUrl, {
    headers: {
      "Authorization": `Bearer ${pat}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cloudflare-worker-obo"
    }
  });
  
  let agentStarted = null;
  let stepsText = "";
  if (r.status === 200) {
    const data = await r.json();
    const jobs = data.jobs || [];
    if (jobs.length > 0) {
      const steps = jobs[0].steps || [];
      for (const step of steps) {
        if (step.name === "Run Agent" && step.started_at) {
          agentStarted = step.started_at;
        }
        if (step.name.startsWith("Post ") || ["Get Playwright Version", "Cache Playwright Browsers"].includes(step.name)) continue;
        const icon = step.status === "completed" 
          ? (step.conclusion === "success" ? "✅" : step.conclusion === "skipped" ? "⏭️" : step.conclusion === "cancelled" ? "🟡" : "❌")
          : (step.status === "in_progress" ? "⏳" : "⬜");
        stepsText += `${icon} ${step.name}\n`;
      }
    }
  }

  let header = "";
  if (agentStarted) {
    const elapsedSec = Math.floor((Date.now() - new Date(agentStarted).getTime()) / 1000);
    const m = Math.floor(elapsedSec / 60);
    const s = elapsedSec % 60;
    header = `🟢 *Run #${run.run_number}* — Learning for ${m}m ${s}s\n\n`;
  } else {
    header = `⚙️ *Run #${run.run_number}* — Setting up environment...\n\n`;
  }

  return header + stepsText;
}

async function sendTelegram(token, method, payload) {
  if (!token) {
    console.error("[ERROR] TELEGRAM_BOT_TOKEN is missing in Cloudflare environment variables!");
    return;
  }
  const url = `https://api.telegram.org/bot${token}/${method}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const errText = await res.text();
    console.error(`[ERROR] Telegram API (${method}) failed status ${res.status}: ${errText}`);
  }
}

async function deleteTelegramMessage(token, chatId, messageId) {
  if (!token || !chatId || !messageId) return;
  const url = `https://api.telegram.org/bot${token}/deleteMessage`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, message_id: messageId })
    });
  } catch (err) {
    console.error("[WARNING] Failed to delete Telegram message:", err);
  }
}

async function handleScheduled(env) {
  try {
    const token = env.TELEGRAM_BOT_TOKEN ? env.TELEGRAM_BOT_TOKEN.trim() : "";
  const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
  const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
  const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
  const allowedUserChatId = env.ALLOWED_TELEGRAM_CHAT_ID ? String(env.ALLOWED_TELEGRAM_CHAT_ID).trim() : "";

  // 1. Get current IST time (UTC + 5:30)
  const now = new Date();
  const istOffset = 5.5 * 60 * 60 * 1000;
  const nowIst = new Date(now.getTime() + istOffset);
  const hour = nowIst.getUTCHours();
  
  // Gating window: 3:00 AM - 8:00 AM IST or 8:05 PM - 8:20 PM IST (for testing)
  const withinWindow = (hour >= 3 && hour < 8) || (hour === 20 && nowIst.getUTCMinutes() >= 5 && nowIst.getUTCMinutes() <= 20);
  
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
    }
  } catch (err) {
    console.error("[AUTO-LOOP] Failed to fetch scheduler_state.json:", err);
    return;
  }
  
  if (!state) return;
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
  
  const trackDisplay = {
    cpp: "1. CP / DSA",
    arch: "2. Computer Arch & Net",
    os: "3. OS",
    ds: "4. Data Science",
    dl: "5. DL",
    maths: "6. Maths for DS"
  }[selectedTrack];
  
  // 6. Generate dynamic session duration
  let durationMins = Math.floor(Math.random() * (92 - 22 + 1)) + 22; // 22 to 92 mins
  if (hour === 20) {
    durationMins = 3; // Force 3 minutes for 8:07 PM to 8:10 PM test
  }
  
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
