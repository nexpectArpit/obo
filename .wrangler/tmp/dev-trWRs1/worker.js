var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// .wrangler/tmp/bundle-lowulp/checked-fetch.js
var urls = /* @__PURE__ */ new Set();
function checkURL(request, init) {
  const url = request instanceof URL ? request : new URL(
    (typeof request === "string" ? new Request(request, init) : request).url
  );
  if (url.port && url.port !== "443" && url.protocol === "https:") {
    if (!urls.has(url.toString())) {
      urls.add(url.toString());
      console.warn(
        `WARNING: known issue with \`fetch()\` requests to custom HTTPS ports in published Workers:
 - ${url.toString()} - the custom port will be ignored when the Worker is published using the \`wrangler deploy\` command.
`
      );
    }
  }
}
__name(checkURL, "checkURL");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    const [request, init] = argArray;
    checkURL(request, init);
    return Reflect.apply(target, thisArg, argArray);
  }
});

// cloudflare_worker/config.js
var trackSkillMap = {
  "cpp": [["DP", "Dynamic Programming"], ["Algo", "Algorithms"]],
  "arch": [["Mem", "Memory Systems"], ["Arch", "Computer Architecture"]],
  "os": [["SysCall", "System Calls"], ["OS", "Operating Systems"]],
  "ds": [["ML", "Machine Learning"], ["Hyp", "Hypothesis Testing"]],
  "dl": [["DL", "Deep Learning"], ["NN", "Neural Networks"]],
  "maths": [["Alg", "Algebra"], ["Opt", "Optimization"]]
};
var trackDisplayNames = {
  cpp: "1. CP / DSA",
  arch: "2. Computer Arch & Net",
  os: "3. OS",
  ds: "4. Data Science",
  dl: "5. DL",
  maths: "6. Maths for DS"
};

// cloudflare_worker/telegram.js
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
    console.error(`[ERROR] Telegram API error (${method}): ${res.status} - ${errText}`);
  }
  return res;
}
__name(sendTelegram, "sendTelegram");
async function deleteTelegramMessage(token, chatId, messageId) {
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
__name(deleteTelegramMessage, "deleteTelegramMessage");
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
      const lvl = skills[longName] !== void 0 ? skills[longName] : 1;
      levels.push(String(lvl));
    }
    if (levels.length > 0) {
      return `${label} (${levels.join(", ")})`;
    }
    return label;
  }
  __name(getBtnText, "getBtnText");
  return {
    inline_keyboard: [
      [{ text: getBtnText("1. CP / DSA", "cpp"), callback_data: "pin_cpp" }, { text: getBtnText("2. Arch & Net", "arch"), callback_data: "pin_arch" }],
      [{ text: getBtnText("3. OS", "os"), callback_data: "pin_os" }, { text: getBtnText("4. Data Science", "ds"), callback_data: "pin_ds" }],
      [{ text: getBtnText("5. DL", "dl"), callback_data: "pin_dl" }, { text: getBtnText("6. Maths for DS", "maths"), callback_data: "pin_maths" }],
      [{ text: "\u2B05\uFE0F Back to Menu", callback_data: "back_to_menu" }]
    ]
  };
}
__name(getDynamicTracksKeyboard, "getDynamicTracksKeyboard");
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
  const loopText = enabled ? "\u23F0 Auto-Loop: ACTIVE" : "\u23F0 Auto-Loop: INACTIVE";
  return {
    inline_keyboard: [
      [{ text: "\u{1F680} Start Random", callback_data: "start_random" }, { text: "\u{1F4C8} Focus Pinned Track", callback_data: "level_up" }],
      [{ text: "\u{1F4DA} Start Topic", callback_data: "start_topic" }, { text: "\u{1F504} Resume Last", callback_data: "resume" }],
      [{ text: "\u{1F6D1} Stop Agent", callback_data: "stop" }, { text: "\u{1F4CA} Status", callback_data: "status" }],
      [{ text: loopText, callback_data: "toggle_auto_loop" }]
    ]
  };
}
__name(getMenuKeyboard, "getMenuKeyboard");

// cloudflare_worker/github.js
async function triggerGitHubWorkflow(pat, repo, workflow, topic = "random", resume = false, levelUp = false, pin = "none", durationMins = null) {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;
  const inputs = {
    topic,
    resume: resume ? "true" : "false",
    level_up: levelUp ? "true" : "false",
    pin
  };
  if (durationMins !== null) {
    inputs.duration = String(durationMins);
  }
  const payload = {
    ref: "main",
    inputs
  };
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${pat}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cloudflare-worker-obo",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  return r.status === 204;
}
__name(triggerGitHubWorkflow, "triggerGitHubWorkflow");
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
    if (r.ok) {
      const data = await r.json();
      runs = runs.concat(data.workflow_runs || []);
    }
  }
  return runs;
}
__name(getRunningRuns, "getRunningRuns");
async function getLatestRun(pat, repo, workflow) {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/runs?per_page=1`;
  const r = await fetch(url, {
    headers: {
      "Authorization": `Bearer ${pat}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cloudflare-worker-obo"
    }
  });
  if (r.ok) {
    const data = await r.json();
    if (data.workflow_runs && data.workflow_runs.length > 0) {
      return data.workflow_runs[0];
    }
  }
  return null;
}
__name(getLatestRun, "getLatestRun");
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
__name(cancelRun, "cancelRun");
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
        const icon = step.status === "completed" ? step.conclusion === "success" ? "\u2705" : step.conclusion === "skipped" ? "\u23ED\uFE0F" : step.conclusion === "cancelled" ? "\u{1F7E1}" : "\u274C" : step.status === "in_progress" ? "\u23F3" : "\u2B1C";
        stepsText += `${icon} ${step.name}
`;
      }
    }
  }
  let header = "";
  if (agentStarted) {
    const elapsedSec = Math.floor((Date.now() - new Date(agentStarted).getTime()) / 1e3);
    const m = Math.floor(elapsedSec / 60);
    const s = elapsedSec % 60;
    header = `\u{1F7E2} *Run #${run.run_number}* \u2014 Learning for ${m}m ${s}s

`;
  } else {
    header = `\u2699\uFE0F *Run #${run.run_number}* \u2014 Setting up environment...

`;
  }
  return header + stepsText;
}
__name(formatRunStatus, "formatRunStatus");
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
          sha
        })
      });
      if (putRes.status === 200 || putRes.status === 201) {
        return updatedState;
      } else if (putRes.status === 409) {
        attempts++;
        await new Promise((r) => setTimeout(r, 1e3));
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
__name(updateSchedulerState, "updateSchedulerState");

// cloudflare_worker/scheduler.js
function parseTimeToMinutes(val, defaultMinutes) {
  if (val === void 0 || val === null) return defaultMinutes;
  if (typeof val === "number") return val * 60;
  const str = String(val).trim();
  if (str.includes(":")) {
    const parts = str.split(":");
    const h2 = parseInt(parts[0], 10) || 0;
    const m = parseInt(parts[1], 10) || 0;
    return h2 * 60 + m;
  }
  const h = parseInt(str, 10);
  return isNaN(h) ? defaultMinutes : h * 60;
}
__name(parseTimeToMinutes, "parseTimeToMinutes");
async function handleScheduled(env) {
  try {
    const token = env.TELEGRAM_BOT_TOKEN ? env.TELEGRAM_BOT_TOKEN.trim() : "";
    const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
    const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
    const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
    const allowedUserChatId = (env.ALLOWED_TELEGRAM_CHAT_ID || env.ALLOWED_TELEGRAM_USER_ID || "").trim();
    const now = /* @__PURE__ */ new Date();
    const istOffset = 5.5 * 60 * 60 * 1e3;
    const nowIst = new Date(now.getTime() + istOffset);
    const currentIstMinutes = nowIst.getUTCHours() * 60 + nowIst.getUTCMinutes();
    const currentIstTimeStr = `${String(nowIst.getUTCHours()).padStart(2, "0")}:${String(nowIst.getUTCMinutes()).padStart(2, "0")}`;
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
    let withinWindow = false;
    let activeWindowConfig = null;
    if (Array.isArray(state.windows) && state.windows.length > 0) {
      for (const win of state.windows) {
        const sMin = parseTimeToMinutes(win.start, 0);
        const eMin = parseTimeToMinutes(win.end, 1440);
        if (sMin <= eMin) {
          if (currentIstMinutes >= sMin && currentIstMinutes < eMin) {
            withinWindow = true;
            activeWindowConfig = win;
            break;
          }
        } else {
          if (currentIstMinutes >= sMin || currentIstMinutes < eMin) {
            withinWindow = true;
            activeWindowConfig = win;
            break;
          }
        }
      }
    } else {
      const startMinutes = parseTimeToMinutes(state.start_time_ist, 3 * 60);
      const endMinutes = parseTimeToMinutes(state.end_time_ist, 8 * 60);
      if (startMinutes <= endMinutes) {
        withinWindow = currentIstMinutes >= startMinutes && currentIstMinutes < endMinutes;
      } else {
        withinWindow = currentIstMinutes >= startMinutes || currentIstMinutes < endMinutes;
      }
    }
    const isAllowedToRun = state.test_mode === true || withinWindow;
    const latestRun = await getLatestRun(pat, repo, workflow);
    if (latestRun) {
      const status = latestRun.status;
      if (status === "in_progress" || status === "queued") {
        console.log(`[AUTO-CRON] Run #${latestRun.run_number} is currently active (${status}). Waiting...`);
        return;
      }
      const finishedTimestamp = Date.parse(latestRun.updated_at || latestRun.created_at);
      const elapsedMins = (Date.now() - finishedTimestamp) / (60 * 1e3);
      let minCool = state.min_cooldown_mins !== void 0 ? state.min_cooldown_mins : 10;
      if (activeWindowConfig && activeWindowConfig.start) {
        const winStartMins = parseTimeToMinutes(activeWindowConfig.start, 0);
        if (currentIstMinutes >= winStartMins && elapsedMins >= 1) {
          minCool = Math.min(minCool, elapsedMins);
        }
      } else if (activeWindowConfig && activeWindowConfig.cooldown_mins !== void 0) {
        minCool = activeWindowConfig.cooldown_mins;
      }
      if (elapsedMins < minCool) {
        const remaining = (minCool - elapsedMins).toFixed(1);
        console.log(`[AUTO-CRON] In Cooldown: ${remaining}m remaining of ${minCool}m pause. Waiting...`);
        return;
      }
    }
    if (!isAllowedToRun) {
      console.log(`[AUTO-CRON] Outside active window (${currentIstTimeStr} IST). Scheduled: ${state.start_time_ist || "Custom"} - ${state.end_time_ist || "Custom"} IST.`);
      return;
    }
    let selectedTrack = activeWindowConfig && activeWindowConfig.track || (state.track && state.track !== "auto" ? state.track : null);
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
          sum += skills[longName] !== void 0 ? skills[longName] : 1;
        }
        const avg = sum / mappings.length;
        trackLevels.push({ key: trackKey, avg });
      }
      trackLevels.sort((a, b) => b.avg - a.avg);
      const top3 = trackLevels.slice(0, 3);
      const selectedTrackObj = top3[Math.floor(Math.random() * top3.length)];
      selectedTrack = selectedTrackObj ? selectedTrackObj.key : "cpp";
    }
    const trackDisplay = trackDisplayNames[selectedTrack] || selectedTrack;
    let minDur = state.min_duration_mins !== void 0 ? state.min_duration_mins : 22;
    let maxDur = state.max_duration_mins !== void 0 ? state.max_duration_mins : 92;
    if (activeWindowConfig) {
      if (activeWindowConfig.duration_mins !== void 0) {
        minDur = activeWindowConfig.duration_mins;
        maxDur = activeWindowConfig.duration_mins;
      } else if (activeWindowConfig.duration !== void 0) {
        minDur = activeWindowConfig.duration;
        maxDur = activeWindowConfig.duration;
      }
    }
    const durationMins = minDur === maxDur ? minDur : Math.floor(Math.random() * (maxDur - minDur + 1)) + minDur;
    const ok = await triggerGitHubWorkflow(pat, repo, workflow, "random", false, true, selectedTrack, durationMins);
    if (ok) {
      console.log(`[AUTO-CRON] Triggered session: Track '${selectedTrack}', Duration ${durationMins}m`);
      if (allowedUserChatId) {
        await sendTelegram(token, "sendMessage", {
          chat_id: allowedUserChatId,
          text: `\u{1F3AF} <b>[AUTO-LOOP] Session Started:</b>
\u2022 <b>Track:</b> ${trackDisplay}
\u2022 <b>Duration:</b> ${durationMins} minutes
\u2022 <b>Window:</b> ${activeWindowConfig ? `${activeWindowConfig.start} - ${activeWindowConfig.end}` : `${state.start_time_ist} - ${state.end_time_ist}`} IST

GitHub Actions runner is running. Will stop automatically.`,
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
__name(handleScheduled, "handleScheduled");

// cloudflare_worker/worker.js
var worker_default = {
  async fetch(request, env, ctx) {
    const requestUrl = new URL(request.url);
    const pat = env.GH_PAT ? env.GH_PAT.trim() : "";
    const repo = (env.GH_REPO || "nexpectArpit/obo").trim();
    const workflow = (env.GH_WORKFLOW || "run_agent.yml").trim();
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
          const r = await fetch(`https://api.github.com/repos/${repo}/contents/data/scheduler_state.json`, {
            headers: { "Authorization": `Bearer ${pat}`, "Accept": "application/vnd.github+json", "User-Agent": "cloudflare-worker-obo" }
          });
          if (r.ok) {
            const fileData = await r.json();
            state = JSON.parse(atob(fileData.content.replace(/\s/g, "")));
          }
        } catch (e) {
        }
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
          state
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
    if (requestUrl.searchParams.has("test")) {
      ctx.waitUntil(handleScheduled(env));
      return new Response("Test cron trigger launched successfully!", { status: 200 });
    }
    if (request.method !== "POST") {
      return new Response("Oboe Cloudflare Telegram Worker Active", { status: 200 });
    }
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
  if (userId && allowedUser && userId !== allowedUser) {
    if (chatId) {
      await sendTelegram(token, "sendMessage", { chat_id: chatId, text: `\u26D4 Unauthorized user (ID: ${userId}).` });
    }
    return;
  }
  if (callbackQueryId) {
    await sendTelegram(token, "answerCallbackQuery", { callback_query_id: callbackQueryId });
  }
  const menuKeyboard = await getMenuKeyboard(pat, repo);
  const cleanText = text ? text.trim().toLowerCase() : "";
  if (cleanText.startsWith("/schedule")) {
    const parts = text.split(/\s+/).slice(1);
    if (parts.length < 2) {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "\u2139\uFE0F <b>Usage:</b>\n<code>/schedule &lt;start_time&gt; &lt;end_time&gt; [duration_mins] [cooldown_mins]</code>\n\n<b>Example:</b>\n<code>/schedule 23:45 23:55 5 10</code>\n<code>/schedule 03:00 08:00 50 15</code>",
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
      text: `\u2705 <b>Schedule Updated:</b>
\u2022 <b>Window:</b> ${startTime} - ${endTime} IST
\u2022 <b>Duration:</b> ${duration} mins
\u2022 <b>Cooldown:</b> ${cooldown} mins`,
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }
  if (cleanText === "/start" || cleanText === "/menu" || cleanText === "menu" || cleanText === "start") {
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: "\u{1F3B5} <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
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
      text: "\u{1F9F9} <b>Dashboard Cleared!</b>",
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }
  if (callbackData === "back_to_menu") {
    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "\u{1F3B5} <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
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
        text: "\u{1F680} <b>Random topic started!</b>\n\nThe agent is booting up on GitHub Actions.\nIt will take ~2 minutes to set up, then begin learning.\n\nTap \u{1F4CA} Status to track progress.",
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "\u274C Failed to trigger workflow. Check your GH_PAT permissions.",
        reply_markup: menuKeyboard
      });
    }
    return;
  }
  if (callbackData === "level_up") {
    const tracksKeyboard = await getDynamicTracksKeyboard(pat, repo);
    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "\u{1F4C8} <b>Select Pinned Track to Focus:</b>\n\nChoose one of the 6 pinned tracks to run and progress in Oboe continuous chats:",
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
        text: `\u{1F3AF} <b>Focus Mode active on Pinned Track: ${trackDisplay}</b>

The agent will open the corresponding pinned chat in the sidebar and process the next sub-topic.

Tap \u{1F4CA} Status to track progress.`,
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: `\u274C Failed to trigger workflow for ${trackDisplay}.`,
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
        text: "\u{1F504} <b>Resuming last chat!</b>\n\nThe agent will pick up where you left off.\n\nTap \u{1F4CA} Status to track progress.",
        parse_mode: "HTML",
        reply_markup: menuKeyboard
      });
    } else {
      await sendTelegram(token, "sendMessage", {
        chat_id: chatId,
        text: "\u274C Failed to trigger workflow. Check your GH_PAT permissions.",
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
        [{ text: "\u{1F680} Start Random", callback_data: "start_random" }, { text: "\u{1F4C8} Focus Pinned Track", callback_data: "level_up" }],
        [{ text: "\u{1F4DA} Start Topic", callback_data: "start_topic" }, { text: "\u{1F504} Resume Last", callback_data: "resume" }],
        [{ text: "\u{1F6D1} Stop Agent", callback_data: "stop" }, { text: "\u{1F4CA} Status", callback_data: "status" }],
        [{ text: enabled ? "\u23F0 Auto-Loop: ACTIVE" : "\u23F0 Auto-Loop: INACTIVE", callback_data: "toggle_auto_loop" }]
      ]
    };
    await sendTelegram(token, "editMessageText", {
      chat_id: chatId,
      message_id: update.callback_query.message.message_id,
      text: "\u{1F3B5} <b>Oboe Cloud Agent Controller</b>\n\nChoose an action:",
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
        text: "\u2139\uFE0F No learning sessions are currently running.",
        reply_markup: menuKeyboard
      });
      return;
    }
    for (const run of activeRuns) {
      await cancelRun(pat, repo, run.id);
    }
    await sendTelegram(token, "sendMessage", {
      chat_id: chatId,
      text: `\u{1F6D1} <b>Stopped ${activeRuns.length} running session(s).</b>`,
      parse_mode: "HTML",
      reply_markup: menuKeyboard
    });
    return;
  }
}
__name(handleUpdate, "handleUpdate");
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
      <h1>\u{1F3B5} Oboe Precision Controller</h1>
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

    <!-- Instant One-Click Trigger -->
    <div class="card">
      <div class="card-title"><span>\u26A1 Instant Run Now (0.5s Trigger)</span></div>
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
        <button class="btn-primary" onclick="triggerRun()">\u{1F680} Launch Session Now</button>
        <button class="btn-danger" onclick="stopRun()">\u{1F6D1} Emergency Stop</button>
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
          
          details.innerHTML = '\u2022 <b>Last Run:</b> #' + data.latestRun.run_number + '<br>' +
                            '\u2022 <b>Status:</b> ' + data.latestRun.status + ' (' + (data.latestRun.conclusion || 'running') + ')<br>' +
                            '\u2022 <b>Last Updated:</b> ' + new Date(data.latestRun.updated_at).toLocaleTimeString();
        }
      } catch (err) {
        console.error(err);
      }
    }

    async function triggerRun() {
      const track = document.getElementById('runTrack').value;
      const duration = document.getElementById('runDuration').value;
      const btn = event.target;
      btn.innerText = '\u23F3 Launching...';
      try {
        const res = await fetch('/api/trigger', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track, duration })
        });
        const data = await res.json();
        if (data.success) {
          alert('\u{1F680} Session launched successfully!');
          fetchStatus();
        } else {
          alert('\u274C Failed: ' + (data.error || 'Unknown error'));
        }
      } catch (e) {
        alert('Network error');
      }
      btn.innerText = '\u{1F680} Launch Session Now';
    }

    async function stopRun() {
      if (!confirm('Are you sure you want to stop active runner?')) return;
      try {
        const res = await fetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          alert('\u{1F6D1} Session cancelled successfully!');
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
  <\/script>
</body>
</html>`;
}
__name(renderDashboardHtml, "renderDashboardHtml");

// ../../../.npm/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// ../../../.npm/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-lowulp/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = worker_default;

// ../../../.npm/_npx/32026684e21afda6/node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-lowulp/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=worker.js.map
