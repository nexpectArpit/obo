import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env.local"
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

def trigger_workflow(topic="random", resume=False, level_up=False, pin="none", duration=None):
    url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "topic": topic,
            "resume": "true" if resume else "false",
            "level_up": "true" if level_up else "false",
            "pin": pin,
            "duration": str(duration) if duration else "none"
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

def get_file_json(path_in_repo):
    """Fetch a JSON file directly from the repo (always latest, bypasses local stale copy)."""
    import base64
    url = f"{GH_API}/contents/{path_in_repo}"
    r = requests.get(url, headers=gh_headers())
    if r.status_code == 200:
        content = r.json().get("content", "")
        decoded = base64.b64decode(content).decode("utf-8")
        return json.loads(decoded)
    return None

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

def update_scheduler_state_on_github(update_fn):
    """
    Fetch data/scheduler_state.json from GitHub, apply update_fn(state), and PUT back to GitHub.
    Returns the updated state dict, or None on failure.
    """
    import base64
    import time
    url = f"{GH_API}/contents/data/scheduler_state.json"
    headers = gh_headers()
    
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                print(f"[ERROR] Failed to fetch scheduler_state.json from GitHub: {r.status_code}")
                return None
            
            file_data = r.json()
            sha = file_data["sha"]
            content_b64 = file_data.get("content", "")
            decoded = base64.b64decode(content_b64).decode("utf-8")
            state = json.loads(decoded)
            
            updated_state = update_fn(state)
            
            new_content = json.dumps(updated_state, indent=2)
            new_b64 = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
            
            payload = {
                "message": "chore(scheduler): update scheduler state",
                "content": new_b64,
                "sha": sha
            }
            
            put_r = requests.put(url, headers=headers, json=payload)
            if put_r.status_code in (200, 201):
                return updated_state
            elif put_r.status_code == 409:
                time.sleep(1)
                continue
            else:
                print(f"[ERROR] Failed to update scheduler_state.json on GitHub: {put_r.status_code} - {put_r.text}")
                return None
        except Exception as e:
            print(f"[ERROR] Error updating scheduler_state.json on GitHub: {e}")
            return None
    return None

