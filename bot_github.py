import os
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env.local"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

GH_PAT = os.getenv("GH_PAT", "").strip()
GH_REPO = os.getenv("GH_REPO", "nexpectArpit/obo").strip()
GH_WORKFLOW = os.getenv("GH_WORKFLOW", "run_agent.yml").strip()
GH_API = f"https://api.github.com/repos/{GH_REPO}"

def gh_headers():
    return {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def trigger_workflow(topic="random", resume=False, level_up=False, track="none"):
    url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "mode": topic,
            "resume": "true" if resume else "false",
            "level_up": "true" if level_up else "false",
            "track": track
        }
    }
    r = requests.post(url, headers=gh_headers(), json=payload)
    return r.status_code == 204

def get_running_runs():
    runs = []
    for status in ["in_progress", "queued"]:
        url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/runs?status={status}"
        r = requests.get(url, headers=gh_headers())
        if r.status_code == 200:
            runs.extend(r.json().get("workflow_runs", []))
    return runs

def cancel_run(run_id):
    url = f"{GH_API}/actions/runs/{run_id}/cancel"
    r = requests.post(url, headers=gh_headers())
    return r.status_code == 202

def get_latest_run():
    url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/runs?per_page=1"
    r = requests.get(url, headers=gh_headers())
    if r.status_code == 200:
        runs = r.json().get("workflow_runs", [])
        return runs[0] if runs else None
    return None

def get_run_jobs(run_id):
    url = f"{GH_API}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=gh_headers())
    if r.status_code == 200:
        return r.json().get("jobs", [])
    return []

def format_elapsed(started_at_str, ended_at_str=None):
    try:
        started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        if ended_at_str:
            ended = datetime.fromisoformat(ended_at_str.replace("Z", "+00:00"))
        else:
            ended = datetime.now(timezone.utc)
        elapsed = ended - started
        mins = int(elapsed.total_seconds()) // 60
        secs = int(elapsed.total_seconds()) % 60
        return f"{mins}m {secs}s"
    except Exception:
        return "unknown"
