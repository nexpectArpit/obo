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
    const incomingSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
    if (env.TELEGRAM_SECRET_TOKEN && incomingSecret !== env.TELEGRAM_SECRET_TOKEN) {
      console.warn("Unauthorized webhook request: secret token mismatch");
      return new Response("Forbidden", { status: 403 });
    }

    try {
      const update = await request.json();
      await handleUpdate(update, env);
    } catch (err) {
      console.error("Error handling update:", err);
    }

    return new Response("OK", { status: 200 });
  }
};

async function handleUpdate(update, env) {
  const token = env.TELEGRAM_BOT_TOKEN;
  const allowedUser = String(env.ALLOWED_TELEGRAM_USER_ID || "");
  const repo = env.GH_REPO || "nexpectArpit/obo";
  const workflow = env.GH_WORKFLOW || "run_agent.yml";
  const pat = env.GH_PAT;

  let chatId = null;
  let userId = null;
  let text = null;
  let callbackQueryId = null;
  let callbackData = null;

  if (update.message) {
    chatId = update.message.chat.id;
    userId = String(update.message.from.id);
    text = update.message.text;
  } else if (update.callback_query) {
    chatId = update.callback_query.message.chat.id;
    userId = String(update.callback_query.from.id);
    callbackQueryId = update.callback_query.id;
    callbackData = update.callback_query.data;
  }

  // 2. Validate Telegram User Authorization
  if (userId && allowedUser && userId !== allowedUser) {
    if (chatId) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "⛔ Unauthorized user."
      });
    }
    return;
  }

  if (callbackQueryId) {
    await sendTelegram(token, "answerCallbackQuery", { callback_query_id: callbackQueryId });
  }

  const menuKeyboard = {
    inline_keyboard: [
      [{ text: "🚀 Start Random", callback_data: "start_random" }, { text: "📈 Focus Level Up", callback_data: "level_up" }],
      [{ text: "📚 Start Topic", callback_data: "start_topic" }, { text: "🔄 Resume Last", callback_data: "resume" }],
      [{ text: "🛑 Stop Agent", callback_data: "stop" }, { text: "📊 Status", callback_data: "status" }]
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

  // Handle "🚀 Start Random" button
  if (callbackData === "start_random") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, false);
    
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

  // Handle "📈 Focus Level Up" button
  if (callbackData === "level_up") {
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true);
    
    const replyText = ok
      ? "📈 *Focus Level Up Session Triggered!*\n\nGitHub Actions runner is booting up in Level-Up mode."
      : "❌ *Failed to trigger workflow on GitHub.*";

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
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", true, false);
    
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
    const runs = await getRunningRuns(pat, repo);
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
    const runs = await getRunningRuns(pat, repo);
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
}

// GitHub REST API Integration
async function triggerGitHubWorkflow(pat, repo, workflow, topic, resume, levelUp) {
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
        level_up: String(levelUp)
      }
    })
  });
  return r.status === 204;
}

async function getRunningRuns(pat, repo) {
  let runs = [];
  for (const status of ["in_progress", "queued"]) {
    const url = `https://api.github.com/repos/${repo}/actions/runs?status=${status}&per_page=5`;
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
