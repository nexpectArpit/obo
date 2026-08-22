#!/usr/bin/env python3
"""
CLI & Helper to manage dynamic scheduling, overrides, and production switches with ZERO redeploys.
"""
import sys
import json
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from bot.github_api import trigger_workflow

STATE_PATH = BASE_DIR / "data" / "scheduler_state.json"

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"enabled": True, "config": {}, "override": None}

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"✅ Updated {STATE_PATH.name}")

def main():
    parser = argparse.ArgumentParser(description="Manage Oboe Scheduler Dynamic Config & Overrides")
    parser.add_argument("--track", choices=["cpp", "arch", "os", "ds", "dl", "maths", "auto"], help="Curriculum track")
    parser.add_argument("--duration", type=int, help="Session duration in minutes")
    parser.add_argument("--clear-override", action="store_true", help="Clear any active override")
    parser.add_argument("--prod", action="store_true", help="Set to production mode (3-8 AM IST, 50-85m duration, 10-17m cooling)")
    parser.add_argument("--test-mode", action="store_true", help="Enable test mode (bypasses 3-8 AM IST window)")
    parser.add_argument("--run-now", action="store_true", help="Directly trigger GitHub Actions run right now (0.5s)")
    
    args = parser.parse_args()
    state = load_state()

    if args.prod:
        state["config"] = {
            "test_mode": False,
            "start_hour_ist": 3,
            "end_hour_ist": 8,
            "min_duration": 50,
            "max_duration": 85,
            "min_cooldown_mins": 10,
            "max_cooldown_mins": 17
        }
        state["override"] = None
        save_state(state)
        print("🚀 Production mode enabled: Active 3:00 AM - 8:00 AM IST | 50-85 min sessions | 10-17 min cooldown.")
        return

    if args.test_mode:
        if "config" not in state:
            state["config"] = {}
        state["config"]["test_mode"] = True
        save_state(state)
        print("🧪 Test mode enabled: Window restriction bypassed.")

    if args.clear_override:
        state["override"] = None
        save_state(state)
        print("🧹 Cleared scheduler override.")

    if args.track or args.duration:
        state["override"] = {
            "track": args.track or "auto",
            "duration": args.duration or 5
        }
        save_state(state)
        print(f"🎯 Scheduler override set: Track '{state['override']['track']}', Duration {state['override']['duration']} mins.")

    if args.run_now:
        track = args.track if args.track and args.track != "auto" else "cpp"
        duration = args.duration if args.duration else 5
        print(f"⚡ Dispatching GitHub Actions run immediately: Track '{track}', Duration {duration} mins...")
        ok = trigger_workflow(topic="random", pin=track, duration=duration)
        if ok:
            print("🚀 GitHub Actions workflow dispatched successfully!")
        else:
            print("❌ Failed to dispatch workflow.")

if __name__ == "__main__":
    main()
