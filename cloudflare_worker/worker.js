/**
 * Cloudflare Worker: Main Entrypoint
 */
import { trackDisplayNames } from "./config.js";
import { sendTelegram, deleteTelegramMessage, getDynamicTracksKeyboard, getMenuKeyboard } from "./telegram.js";
import { triggerGitHubWorkflow, getRunningRuns, cancelRun, formatRunStatus, updateSchedulerState } from "./github.js";
import { handleScheduled } from "./scheduler.js";

export default {
  async fetch(request, env, ctx) {
    const requestUrl = new URL(request.url);
    if (requestUrl.searchParams.has("test")) {
      ctx.waitUntil(handleScheduled(env));
      return new Response("Test cron trigger launched successfully!", { status: 200 });
    }
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
    const trackDisplay = trackDisplayNames[trackName] || trackName.toUpperCase();

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
