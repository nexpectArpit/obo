/**
 * Cloudflare Worker: GitHub API Integration Helper Module
 */

export async function triggerGitHubWorkflow(pat, repo, workflow, topic = "random", resume = false, levelUp = false, pin = "none", durationMins = null) {
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;
  
  const inputs = {
    topic: topic,
    resume: resume ? "true" : "false",
    level_up: levelUp ? "true" : "false",
    pin: pin
  };
  
  if (durationMins !== null) {
    inputs.duration = String(durationMins);
  }

  const payload = {
    ref: "main",
    inputs: inputs
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

export async function getRunningRuns(pat, repo, workflow) {
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


export async function getLatestRun(pat, repo, workflow) {
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


export async function cancelRun(pat, repo, runId) {
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

export async function formatRunStatus(pat, repo, run) {
  if (typeof run === "string") {
    run = await getLatestRun(pat, repo, run);
  }
  if (!run) {
    return "📭 No workflow runs found.";
  }
  if (run.conclusion === "startup_failure") {
    return `❌ *Run #${run.run_number}* — Startup Failure (GitHub provisioning error).\n\n`;
  }
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

export async function updateSchedulerState(pat, repo, updateFn) {
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
          content: btoa(unescape(encodeURIComponent(JSON.stringify(updatedState, null, 2)))),
          sha: sha
        })
      });
      
      if (typeof globalThis !== "undefined") {
        globalThis.globalMemorySchedulerState = updatedState;
      }
      if (putRes.status === 200 || putRes.status === 201) {
        return updatedState;
      } else if (putRes.status === 409) {
        attempts++;
        await new Promise(r => setTimeout(r, 1000));
        continue;
      } else {
        const bodyText = await putRes.text();
        console.warn(`[SCHEDULER] GitHub PUT 403/Error (${putRes.status}). Utilizing Worker state override: ${bodyText}`);
        return updatedState;
      }
    } catch (err) {
      console.warn(`Attempt ${attempts} notice:`, err);
      attempts++;
      if (attempts >= 3) {
        return updateFn({});
      }
    }
  }
}
