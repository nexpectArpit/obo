/**
 * Cloudflare Worker: Main Entrypoint & Web Dashboard Controller
 */
import { trackDisplayNames } from "./config.js";
import { sendTelegram, deleteTelegramMessage, getDynamicTracksKeyboard, getMenuKeyboard } from "./telegram.js";
import { triggerGitHubWorkflow, getRunningRuns, getLatestRun, cancelRun, formatRunStatus, updateSchedulerState } from "./github.js";
import { handleScheduled } from "./scheduler.js";

export default {
  async fetch(request, env, ctx) {
    const requestUrl = new URL(request.url);
    const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
    const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
    const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();

    // 1. Web Dashboard & API Endpoints (GET only)
    if ((requestUrl.pathname === "/" || requestUrl.pathname === "/dashboard") && request.method === "GET") {
      return new Response(renderDashboardHtml(), {
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    if (requestUrl.pathname === "/api/status") {
      try {
        const latestRun = await getLatestRun(pat, repo, workflow);
        let state = { enabled: true, config: {}, override: null };
        try {
          const r = await fetch(`https://api.github.com/repos/${repo}/contents/data/scheduler_state.json?t=${Date.now()}`, {
            headers: { "Authorization": `Bearer ${pat}`, "Accept": "application/vnd.github+json", "User-Agent": "cloudflare-worker-obo", "Cache-Control": "no-cache" },
            cf: { cacheTtl: 0 }
          });
          if (r.ok) {
            const fileData = await r.json();
            state = JSON.parse(atob(fileData.content.replace(/\s/g, "")));
          }
          if (env.OBO_STATE) {
            try {
              const kvState = await env.OBO_STATE.get("state", "json");
              if (kvState) {
                state = Object.assign(state, kvState);
              }
            } catch (e) {}
          }
        } catch (e) {}

        return new Response(JSON.stringify({
          status: "ok",
          latestRun: latestRun ? {
            id: latestRun.id,
            run_number: latestRun.run_number,
            status: latestRun.status,
            conclusion: latestRun.conclusion,
            updated_at: latestRun.updated_at,
            created_at: latestRun.created_at
          } : null,
          state: state
        }), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ status: "error", message: err.message }), { status: 500 });
      }
    }

    if (requestUrl.pathname === "/api/trigger" && request.method === "POST") {
      try {
        const body = await request.json();
        const track = body.track || "cpp";
        const duration = parseInt(body.duration) || 5;
        const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, track, duration);
        return new Response(JSON.stringify({ success: ok }), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), { status: 500 });
      }
    }

    if (requestUrl.pathname === "/api/stop" && request.method === "POST") {
      try {
        const latestRun = await getLatestRun(pat, repo, workflow);
        if (latestRun && (latestRun.status === "in_progress" || latestRun.status === "queued")) {
          const ok = await cancelRun(pat, repo, latestRun.id);
          return new Response(JSON.stringify({ success: ok, cancelled_run_id: latestRun.id }), {
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
          });
        }
        return new Response(JSON.stringify({ success: false, message: "No active run in progress" }), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), { status: 500 });
      }
    }

    if (requestUrl.pathname === "/api/toggle-scheduler" && request.method === "POST") {
      try {
        const body = await request.json().catch(() => ({}));
        const newState = await updateSchedulerState(pat, repo, (state) => {
          if (typeof body.enabled === "boolean") {
            state.enabled = body.enabled;
          } else {
            state.enabled = !state.enabled;
          }
          return state;
        });
        if (env.OBO_STATE && newState) {
          try {
            await env.OBO_STATE.put("state", JSON.stringify(newState));
          } catch (e) {}
        }
        return new Response(JSON.stringify({ success: true, enabled: newState ? newState.enabled : false, state: newState }), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), { status: 500 });
      }
    }

    if (requestUrl.searchParams.has("test")) {
      ctx.waitUntil(handleScheduled(env));
      return new Response("Test cron trigger launched successfully!", { status: 200 });
    }

    if (request.method !== "POST") {
      return new Response("Oboe Cloudflare Telegram Worker Active", { status: 200 });
    }

    // 2. Verify Telegram Webhook Secret Token
    const incomingSecret = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "").trim();
    const secretToken = (env.TELEGRAM_SECRET_TOKEN || "").trim();
    console.log(`[AUTH-CHECK] incomingSecretLength=${incomingSecret.length}, secretTokenLength=${secretToken.length}, match=${incomingSecret === secretToken}`);
    if (secretToken && incomingSecret !== secretToken) {
      console.warn(`Unauthorized webhook request: secret token mismatch`);
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

  console.log(`[TELEGRAM-WEBHOOK] chatId=${chatId}, userId=${userId}, text=${text}, allowedUser=${allowedUser}, tokenLength=${token ? token.length : 0}`);

  // Validate Telegram User Authorization
  if (userId && allowedUser && userId !== allowedUser) {
    if (chatId) {
      await sendTelegram(token, "sendMessage", { chat_id: chatId, text: `⛔ Unauthorized user (ID: ${userId}).` });
    }
    return;
  }

  if (callbackQueryId) {
    await sendTelegram(token, "answerCallbackQuery", { callback_query_id: callbackQueryId });
  }

  const menuKeyboard = await getMenuKeyboard(pat, repo);
  const cleanText = text ? text.trim().toLowerCase() : "";

  // Handle Force Reply for custom topics
  if (update.message && update.message.reply_to_message) {
    const parentText = update.message.reply_to_message.text || "";
    if (parentText.includes("Type the custom topic name")) {
      const customTopic = update.message.text.trim();
      const ok = await triggerGitHubWorkflow(pat, repo, workflow, customTopic, false, false, "none");
      if (ok) {
        await sendTelegram(token, "sendMessage", {
          chat_id: chatId,
          text: `🚀 <b>Custom topic started!</b>\n\nTopic: <i>${customTopic}</i>\n\nThe agent is booting up on GitHub Actions.\n\nTap 📊 Status to track progress.`,
          parse_mode: "HTML",
          reply_markup: menuKeyboard
        });
      } else {
        await sendTelegram(token, "sendMessage", {
          chat_id: chatId,
          text: `❌ Failed to trigger workflow for topic: ${customTopic}.`,
          reply_markup: menuKeyboard
        });
      }
      return;
    }
  }

  // Command /schedule <start> <end> [duration] [cooldown]
  if (cleanText.startsWith("/schedule")) {
    const parts = text.split(/\s+/).slice(1);
    if (parts.length < 2) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "ℹ️ <b>Usage:</b>\n<code>/schedule &lt;start_time&gt; &lt;end_time&gt; [duration_mins] [cooldown_mins]</code>\n\n<b>Example:</b>\n<code>/schedule 23:45 23:55 5 10</code>\n<code>/schedule 03:00 08:00 50 15</code>",
        parse_mode: "HTML"
      });
      return;
    }

    const startTime = parts[0];
    const endTime = parts[1];
    const duration = parts[2] ? parseInt(parts[2], 10) : 50;
    const cooldown = parts[3] ? parseInt(parts[3], 10) : 15;

    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: `✅ <b>Schedule Updated:</b>\n• <b>Window:</b> ${startTime} - ${endTime} IST\n• <b>Duration:</b> ${duration} mins\n• <b>Cooldown:</b> ${cooldown} mins`,
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }

  if (cleanText === "/start" || cleanText === "/menu" || cleanText === "menu" || cleanText === "start") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "🎵 <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }

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
      text: "🧹 <b>Dashboard Cleared!</b>",
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }

  // Handle Callback Queries (Inline Buttons)
  if (callbackData === "back_to_menu") {
    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "🎵 <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }

  if (callbackData === "start_random") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, false, "none");
    if (ok) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "🚀 <b>Random topic started!</b>\n\nThe agent is booting up on GitHub Actions.\nIt will take ~2 minutes to set up, then begin learning.\n\nTap 📊 Status to track progress.",
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "❌ Failed to trigger workflow. Check your GH_PAT permissions.",
        reply_markup: menuKeyboard
      });
    }
    return;
  }

  if (callbackData === "start_topic") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "📚 <b>Type the custom topic name you want to start learning:</b>\n\n(Write-in response will trigger GitHub Actions)",
      parse_mode: "HTML",
      reply_markup: {
        force_reply: true,
        selective: true
      }
    });
    return;
  }

  if (callbackData === "level_up") {
    const tracksKeyboard = await getDynamicTracksKeyboard(pat, repo);
    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "📈 <b>Select Pinned Track to Focus:</b>\n\nChoose one of the 6 pinned tracks to run and progress in Oboe continuous chats:",
      parse_mode: "HTML",
      reply_markup: tracksKeyboard
    });
    return;
  }

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
    if (ok) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: `🎯 <b>Focus Mode active on Pinned Track: ${trackDisplay}</b>\n\nThe agent will open the corresponding pinned chat in the sidebar and process the next sub-topic.\n\nTap 📊 Status to track progress.`,
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: `❌ Failed to trigger workflow for ${trackDisplay}.`,
        reply_markup: menuKeyboard
      });
    }
    return;
  }

  if (callbackData === "resume") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", true, false, "none");
    if (ok) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "🔄 <b>Resuming last chat!</b>\n\nThe agent will pick up where you left off.\n\nTap 📊 Status to track progress.",
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "❌ Failed to trigger workflow. Check your GH_PAT permissions.",
        reply_markup: menuKeyboard
      });
    }
    return;
  }

  if (callbackData === "toggle_auto_loop") {
    let enabled = false;
    try {
      const newState = await updateSchedulerState(pat, repo, (state) => {
        state.enabled = !state.enabled;
        enabled = state.enabled;
        return state;
      });
      if (newState) {
        enabled = newState.enabled;
      }
    } catch (e) {
      console.error("Failed to toggle auto loop:", e);
    }

    const freshMenuKeyboard = {
      inline_keyboard: [
        [{ text: "🚀 Start Random", callback_data: "start_random" }, { text: "📈 Focus Pinned Track", callback_data: "level_up" }],
        [{ text: "📚 Start Topic", callback_data: "start_topic" }, { text: "🔄 Resume Last", callback_data: "resume" }],
        [{ text: "🛑 Stop Agent", callback_data: "stop" }, { text: "📊 Status", callback_data: "status" }],
        [{ text: enabled ? "⏰ Auto-Loop: ACTIVE" : "⏰ Auto-Loop: INACTIVE", callback_data: "toggle_auto_loop" }]
      ]
    };

    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "🎵 <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
      parse_mode: "HTML",
      reply_markup: freshMenuKeyboard
    });
    return;
  }

  if (cleanText === "status" || cleanText === "/status" || callbackData === "status") {
    const statusMsg = await formatRunStatus(pat, repo, workflow);
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: statusMsg,
      parse_mode: "Markdown",
      reply_markup: menuKeyboard
    });
    return;
  }

  if (cleanText === "stop" || cleanText === "/stop" || callbackData === "stop") {
    const activeRuns = await getRunningRuns(pat, repo, workflow);
    if (!activeRuns || activeRuns.length === 0) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "ℹ️ No learning sessions are currently running.",
        reply_markup: menuKeyboard
      });
      return;
    }
    for (const run of activeRuns) {
      await cancelRun(pat, repo, run.id);
    }
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: `🛑 <b>Stopped ${activeRuns.length} running session(s).</b>`,
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }
}

function renderDashboardHtml() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Oboe Agent Control Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(22, 29, 47, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.3);
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: radial-gradient(circle at top center, rgba(99, 102, 241, 0.15), transparent 70%);
      font-family: 'Outfit', sans-serif;
      color: var(--text);
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 24px 16px;
    }
    .container { width: 100%; max-width: 720px; display: flex; flex-direction: column; gap: 20px; }
    .header { text-align: center; margin-bottom: 8px; }
    .header h1 { font-size: 26px; font-weight: 700; background: linear-gradient(135deg, #fff, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .header p { color: var(--text-muted); font-size: 14px; margin-top: 4px; }
    
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .card-title { font-size: 16px; font-weight: 600; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between; }
    .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
    .badge-idle { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-running { background: rgba(99, 102, 241, 0.15); color: var(--accent); border: 1px solid rgba(99, 102, 241, 0.3); animation: pulse 2s infinite; }
    
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    label { font-size: 13px; color: var(--text-muted); font-weight: 500; }
    input, select {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 10px 14px;
      border-radius: 10px;
      font-family: inherit;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 10px var(--accent-glow); }
    
    .btn-group { display: flex; gap: 12px; margin-top: 10px; }
    button {
      flex: 1;
      padding: 12px 18px;
      border-radius: 12px;
      font-family: inherit;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    .btn-primary { background: var(--accent); color: #fff; box-shadow: 0 4px 20px var(--accent-glow); }
    .btn-primary:hover { transform: translateY(-2px); filter: brightness(1.1); }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }
    .btn-danger:hover { background: var(--danger); color: #fff; }
    
    .status-box {
      background: rgba(10, 15, 28, 0.5);
      border-radius: 10px;
      padding: 12px 16px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
      color: #cbd5e1;
      line-height: 1.6;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🎵 Oboe Precision Controller</h1>
      <p>Instant Zero-Redeploy Scheduler & Real-Time Loop Monitor</p>
    </div>

    <!-- Live Status Card -->
    <div class="card">
      <div class="card-title">
        <span>Live Runner State</span>
        <span id="statusBadge" class="badge badge-idle">CHECKING...</span>
      </div>
      <div id="statusDetails" class="status-box">Fetching live telemetry from GitHub Actions...</div>
    </div>

    <!-- Auto-Loop Scheduler Card -->
    <div class="card">
      <div class="card-title">
        <span>⏰ Auto-Loop Cron Scheduler</span>
        <span id="schedulerBadge" class="badge badge-idle">CHECKING...</span>
      </div>
      <div id="schedulerDetails" class="status-box" style="margin-bottom: 12px;">Fetching scheduler state...</div>
      <div class="btn-group">
        <button id="toggleSchedulerBtn" class="btn-primary" onclick="toggleScheduler()">
          ⏰ Toggle Active / Inactive
        </button>
      </div>
    </div>

    <!-- Instant One-Click Trigger -->
    <div class="card">
      <div class="card-title"><span>⚡ Instant Run Now (0.5s Trigger)</span></div>
      <div class="grid">
        <div class="form-group">
          <label>Curriculum Track</label>
          <select id="runTrack">
            <option value="cpp">1. CP / DSA (C++)</option>
            <option value="arch">2. Computer Arch & Networks</option>
            <option value="os">3. Operating Systems</option>
            <option value="ds">4. Data Science</option>
            <option value="dl">5. Deep Learning</option>
            <option value="maths">6. Maths for DS</option>
          </select>
        </div>
        <div class="form-group">
          <label>Session Duration (Minutes)</label>
          <input type="number" id="runDuration" value="5" min="1" max="180">
        </div>
      </div>
      <div class="btn-group">
        <button class="btn-primary" onclick="triggerRun()">🚀 Launch Session Now</button>
        <button class="btn-danger" onclick="stopRun()">🛑 Emergency Stop</button>
      </div>
    </div>
  </div>

  <script>
    async function fetchStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const badge = document.getElementById('statusBadge');
        const details = document.getElementById('statusDetails');
        
        if (data.latestRun) {
          const isRunning = data.latestRun.status === 'in_progress' || data.latestRun.status === 'queued';
          badge.className = 'badge ' + (isRunning ? 'badge-running' : 'badge-idle');
          badge.innerText = isRunning ? 'RUNNING #' + data.latestRun.run_number : 'IDLE';
          
          details.innerHTML = '• <b>Last Run:</b> #' + data.latestRun.run_number + '<br>' +
                            '• <b>Status:</b> ' + data.latestRun.status + ' (' + (data.latestRun.conclusion || 'running') + ')<br>' +
                            '• <b>Last Updated:</b> ' + new Date(data.latestRun.updated_at).toLocaleTimeString();
        }

        const schedBadge = document.getElementById('schedulerBadge');
        const schedDetails = document.getElementById('schedulerDetails');
        if (data.state) {
          const isEnabled = data.state.enabled !== false;
          schedBadge.className = 'badge ' + (isEnabled ? 'badge-running' : 'badge-idle');
          schedBadge.innerText = isEnabled ? 'ACTIVE' : 'INACTIVE';
          schedDetails.innerHTML = '• <b>Status:</b> ' + (isEnabled ? 'ACTIVE (Cron will auto-run sessions)' : 'INACTIVE (Automated cron runs STOPPED)') + '<br>' +
                                  '• <b>Window:</b> ' + (data.state.start_time_ist || '03:00') + ' - ' + (data.state.end_time_ist || '08:00') + ' IST<br>' +
                                  '• <b>Track Mode:</b> ' + (data.state.track || 'auto');
        }
      } catch (err) {
        console.error(err);
      }
    }

    async function toggleScheduler() {
      const btn = document.getElementById('toggleSchedulerBtn');
      btn.innerText = '⏳ Updating...';
      try {
        const res = await fetch('/api/toggle-scheduler', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          alert('⏰ Auto-Loop Scheduler is now ' + (data.enabled ? 'ACTIVE' : 'INACTIVE'));
          fetchStatus();
        } else {
          alert('❌ Error: ' + (data.error || 'Failed to toggle'));
        }
      } catch (e) {
        alert('Network error');
      }
      btn.innerText = '⏰ Toggle Active / Inactive';
    }

    async function triggerRun() {
      const track = document.getElementById('runTrack').value;
      const duration = document.getElementById('runDuration').value;
      const btn = event.target;
      btn.innerText = '⏳ Launching...';
      try {
        const res = await fetch('/api/trigger', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track, duration })
        });
        const data = await res.json();
        if (data.success) {
          alert('🚀 Session launched successfully!');
          fetchStatus();
        } else {
          alert('❌ Failed: ' + (data.error || 'Unknown error'));
        }
      } catch (e) {
        alert('Network error');
      }
      btn.innerText = '🚀 Launch Session Now';
    }

    async function stopRun() {
      if (!confirm('Are you sure you want to stop active runner?')) return;
      try {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          alert('🛑 Session cancelled successfully!');
          fetchStatus();
        } else {
          alert(data.message || 'No active run');
        }
      } catch (e) {
        alert('Error stopping run');
      }
    }

    setInterval(fetchStatus, 5000);
    fetchStatus();
  </script>
</body>
</html>`;
}
