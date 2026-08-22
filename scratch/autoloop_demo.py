import os
import json
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
env_path = Path(__file__).resolve().parent.parent / ".env.local"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

GH_PAT = os.getenv("GH_PAT", "").strip()
GH_REPO = os.getenv("GH_REPO", "nexpectArpit/obo").strip()
GH_WORKFLOW = os.getenv("GH_WORKFLOW", "run_agent.yml").strip()
GH_API = f"https://api.github.com/repos/{GH_REPO}"

TRACK_SKILL_MAP = {
    "cpp": [("DP", "Dynamic Programming"), ("Algo", "Algorithms")],
    "arch": [("Mem", "Memory Systems"), ("Arch", "Computer Architecture")],
    "os": [("SysCall", "System Calls"), ("OS", "Operating Systems")],
    "ds": [("ML", "Machine Learning"), ("Hyp", "Hypothesis Testing")],
    "dl": [("DL", "Deep Learning"), ("NN", "Neural Networks")],
    "maths": [("Alg", "Algebra"), ("Opt", "Optimization")]
}

TRACK_DISPLAY_NAMES = {
    "cpp": "1. CP / DSA",
    "arch": "2. Computer Arch & Net",
    "os": "3. OS",
    "ds": "4. Data Science",
    "dl": "5. DL",
    "maths": "6. Maths for DS"
}

def gh_headers():
    return {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "autoloop-local-demo"
    }

def run_simulation():
    print("="*60)
    print("🤖 STARTING LOCAL AUTOLOOP SCHEDULER SIMULATION 🤖")
    print("="*60)

    # 1. Fetch scheduler_state.json from GitHub
    print("\n[Step 1] Fetching scheduler_state.json from GitHub...")
    url = f"{GH_API}/contents/data/scheduler_state.json"
    r = requests.get(url, headers=gh_headers())
    if r.status_code != 200:
        print(f"❌ Failed to fetch state: HTTP {r.status_code}")
        print(r.text)
        return
    
    file_data = r.json()
    import base64
    decoded = base64.b64decode(file_data["content"]).decode("utf-8")
    state = json.loads(decoded)
    print(f"✅ Current scheduler state: {json.dumps(state, indent=2)}")

    # 2. Check if active run is already running
    print("\n[Step 2] Checking for active workflow runs...")
    running_url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/runs?status=in_progress"
    r = requests.get(running_url, headers=gh_headers())
    if r.status_code == 200:
        runs = r.json().get("workflow_runs", [])
        if runs:
            print(f"⚠️ Active run found: Run #{runs[0]['run_number']} (ID: {runs[0]['id']}) is currently in progress.")
            print("🕒 Autoloop would normally wait for this run to finish.")
        else:
            print("✅ No active runs in progress on GitHub Actions.")
    else:
        print(f"❌ Failed to check runs: HTTP {r.status_code}")

    # 3. Check Cooldown
    print("\n[Step 3] Checking Cooldown epoch...")
    next_allowed = state.get("next_run_allowed_epoch", 0)
    current_time_ms = int(time.time() * 1000)
    if current_time_ms < next_allowed:
        remaining_secs = (next_allowed - current_time_ms) // 1000
        print(f"⏳ Cooldown is active. Next run allowed in {remaining_secs} seconds.")
    else:
        print("✅ Cooldown period has expired.")

    # 4. Check Active Learning Window
    print("\n[Step 4] Checking Active Window (3:00 AM - 8:00 AM IST)...")
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = datetime.now(timezone.utc) + ist_offset
    hour = now_ist.hour
    within_window = 3 <= hour < 8
    print(f"🕒 Current IST Time: {now_ist.strftime('%I:%M %p IST')}")
    if within_window:
        print("✅ Within active learning window.")
    else:
        print("ℹ️ Outside active window (would only trigger in test/force mode).")

    # 5. Fetch learned_skills.json and Select Track
    print("\n[Step 5] Resolving next focus track based on master levels...")
    skill_url = f"{GH_API}/contents/data/learned_skills.json"
    r = requests.get(skill_url, headers=gh_headers())
    skills = {}
    if r.status_code == 200:
        file_data = r.json()
        decoded_skills = base64.b64decode(file_data["content"]).decode("utf-8")
        skills = json.loads(decoded_skills)
        print("✅ Successfully loaded learned_skills.json from GitHub.")
    else:
        print(f"⚠️ Failed to fetch learned_skills.json (HTTP {r.status_code}). Defaulting to level 1 for all skills.")

    track_levels = []
    for track_key, mappings in TRACK_SKILL_MAP.items():
        total_level = 0
        for short_name, long_name in mappings:
            total_level += skills.get(long_name, 1)
        avg = total_level / len(mappings)
        track_levels.append((track_key, avg))

    # Sort in descending order (highest value = lowest master priority)
    track_levels.sort(key=lambda x: x[1], reverse=True)
    top_3 = track_levels[:3]
    print("📈 Top 3 tracks with lowest mastery priority:")
    for rank, (track, score) in enumerate(top_3, 1):
        print(f"  {rank}. {TRACK_DISPLAY_NAMES[track]} (Average Level: {score:.2f})")
    
    selected_track = random.choice(top_3)[0]
    duration_mins = random.randint(22, 92)
    print(f"\n🎯 Selected Track for this loop: {TRACK_DISPLAY_NAMES[selected_track]}")
    print(f"⏱️ Selected Duration: {duration_mins} minutes")

    print("\n" + "="*60)
    print("🎉 DEMO DRY-RUN SIMULATION COMPLETE 🎉")
    print("="*60)

if __name__ == "__main__":
    run_simulation()
