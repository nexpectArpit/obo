/**
 * Cloudflare Worker: Telegram Messaging & Keyboards Helper Module
 */
import { trackSkillMap } from "./config.js";

export async function sendTelegram(token, method, payload) {
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
    console.error(`[ERROR] Telegram API error (${method}): ${res.status} - ${errText}`);
  }
  return res;
}

export async function deleteTelegramMessage(token, chatId, messageId) {
  if (!token || !chatId || !messageId) return;
  try {
    await fetch(`https://api.telegram.org/bot${token}/deleteMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, message_id: messageId })
    });
  } catch (err) {
    console.error("[WARNING] Failed to delete Telegram message:", err);
  }
}

export async function getDynamicTracksKeyboard(pat, repo) {
  let skills = {};
  let trackTargets = {};
  
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

  const trackFiles = {
    "cpp": "1_cpp.json",
    "arch": "2_computer_architecture_and_networking.json",
    "os": "3_os.json",
    "ds": "4_data_science.json",
    "dl": "5_dl.json",
    "maths": "6_maths.json"
  };

  // Fetch track target skills in parallel
  const trackPromises = Object.entries(trackFiles).map(async ([trackKey, fileName]) => {
    try {
      const r = await fetch(`https://api.github.com/repos/${repo}/contents/tracks/${fileName}`, {
        headers: {
          "Authorization": `Bearer ${pat}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "cloudflare-worker-obo"
        }
      });
      if (r.ok) {
        const fileData = await r.json();
        const decoded = atob(fileData.content.replace(/\s/g, ""));
        const trackData = JSON.parse(decoded);
        trackTargets[trackKey] = trackData.target_skills || [];
      }
    } catch (err) {
      console.error(`Failed to load target skills for ${trackKey}:`, err);
    }
  });

  await Promise.all(trackPromises);

  function getBtnText(label, trackKey) {
    let targetSkills = trackTargets[trackKey] || [];
    if (targetSkills.length === 0) {
      const mappings = trackSkillMap[trackKey] || [];
      targetSkills = mappings.map(m => m[1]);
    }
    const levels = [];
    for (const skillName of targetSkills) {
      const lvl = skills[skillName] !== undefined ? skills[skillName] : 1;
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

export async function getMenuKeyboard(pat, repo) {
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
