#!/usr/bin/env python3
"""
CLI & Helper to manage dynamic scheduling, overrides, and production switches with ZERO redeploys.
"""
import sys
import json
import argparse
import subprocess
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

def save_state(state, push=True):
    STATE_PATH.write_text(json.dumps(state, indent=2))
    print(f"✅ Updated {STATE_PATH.name}")
    if push:
        try:
            subprocess.run(
                ["git", "add", "data/scheduler_state.json"],
                cwd=str(BASE_DIR), check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "chore(scheduler): update dynamic schedule config"],
                cwd=str(BASE_DIR), check=True, capture_output=True
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(BASE_DIR), check=True, capture_output=True
            )
            print("🚀 Pushed dynamic config to GitHub in 1s.")
        except Exception as e:
            print(f"⚠️ Git push notice: {e}")

def main():
    parser = argparse.ArgumentParser(description="Manage Oboe Scheduler Dynamic Config & Overrides")
    
    # Custom Schedule Windows & Metrics
    parser.add_argument("--start-hour", type=int, help="Active window start hour in IST (0-23)")
    parser.add_argument("--end-hour", type=int, help="Active window end hour in IST (0-23)")
    parser.add_argument("--min-duration", type=int, help="Minimum random duration in minutes")
    parser.add_argument("--max-duration", type=int, help="Maximum random duration in minutes")
    parser.add_argument("--min-cooldown", type=int, help="Minimum cooldown between runs in minutes")
    parser.add_argument("--max-cooldown", type=int, help="Maximum cooldown between runs in minutes")
    
    # Immediate Overrides & Flags
    parser.add_argument("--track", choices=["cpp", "arch", "os", "ds", "dl", "maths", "auto"], help="Curriculum track for next run")
    parser.add_argument("--duration", type=int, help="Session duration in minutes for next run")
    parser.add_argument("--clear-override", action="store_true", help="Clear any active override")
    parser.add_argument("--prod", action="store_true", help="Set to standard production mode (3-8 AM IST, 50-85m duration, 10-17m cooldown)")
    parser.add_argument("--test-mode", action="store_true", help="Enable test mode (bypasses time window restriction)")
    parser.add_argument("--disable-test-mode", action="store_true", help="Disable test mode (enforces time window restriction)")
    parser.add_argument("--run-now", action="store_true", help="Directly trigger GitHub Actions run right now (0.5s)")
    parser.add_argument("--no-push", action="store_true", help="Do not push changes to GitHub repository")
    
    args = parser.parse_args()
    state = load_state()
    if "config" not in state:
        state["config"] = {}

    push = not args.no_push

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
        save_state(state, push=push)
        print("🚀 Production mode enabled: Active 3:00 AM - 8:00 AM IST | 50-85 min sessions | 10-17 min cooldown.")
        return

    # Update individual config metrics if specified
    if args.start_hour is not None:
        state["config"]["start_hour_ist"] = args.start_hour
    if args.end_hour is not None:
        state["config"]["end_hour_ist"] = args.end_hour
    if args.min_duration is not None:
        state["config"]["min_duration"] = args.min_duration
    if args.max_duration is not None:
        state["config"]["max_duration"] = args.max_duration
    if args.min_cooldown is not None:
        state["config"]["min_cooldown_mins"] = args.min_cooldown
    if args.max_cooldown is not None:
        state["config"]["max_cooldown_mins"] = args.max_cooldown
    if args.test_mode:
        state["config"]["test_mode"] = True
    if args.disable_test_mode:
        state["config"]["test_mode"] = False

    if args.clear_override:
        state["override"] = None

    if args.track or args.duration:
        state["override"] = {
            "track": args.track or "auto",
            "duration": args.duration or 5
        }
        print(f"🎯 Scheduler override set: Track '{state['override']['track']}', Duration {state['override']['duration']} mins.")

    save_state(state, push=push)
    print("📊 Current Active Schedule Config:", json.dumps(state.get("config", {}), indent=2))
    if state.get("override"):
        print("⚡ Active Immediate Override:", json.dumps(state.get("override"), indent=2))

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
