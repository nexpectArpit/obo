"""
Time Tracking Module: Manages rolling 24h and calendar-day (IST) session totals.
Extracted from agent.py for modularity.
"""
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta


def update_time_tracker(elapsed_time, topic):
    """Track sessions and calculate rolling 24h & calendar day (IST) totals.
    
    Returns:
        tuple: (rolling_24h_seconds, today_ist_seconds)
    """
    tracker_path = Path(__file__).resolve().parent.parent / "data" / "time_tracker.json"
    
    # Load existing sessions
    data = {"sessions": []}
    if tracker_path.exists():
        try:
            data = json.loads(tracker_path.read_text())
        except Exception:
            pass
            
    if "sessions" not in data:
        data["sessions"] = []
        
    # Append current session
    current_ts = time.time()
    data["sessions"].append({
        "timestamp": current_ts,
        "duration_seconds": int(elapsed_time),
        "topic": topic
    })
    
    # Deduplicate concurrent/redundant sessions (same topic within 5 mins, or close timestamps within 5s)
    deduplicated = []
    for s in data["sessions"]:
        is_dup = False
        s_ts = s.get("timestamp", 0)
        s_topic = s.get("topic", "")
        for existing in deduplicated:
            e_ts = existing.get("timestamp", 0)
            e_topic = existing.get("topic", "")
            if abs(s_ts - e_ts) < 300 and (s_topic == e_topic or abs(s_ts - e_ts) < 5):
                is_dup = True
                # Retain the session record with the longer duration
                if s.get("duration_seconds", 0) > existing.get("duration_seconds", 0):
                    existing["duration_seconds"] = s["duration_seconds"]
                    existing["timestamp"] = s_ts
                break
        if not is_dup:
            deduplicated.append(s)
    data["sessions"] = deduplicated

    # Filter sessions to keep only the last 7 days (to prevent file growing indefinitely)
    one_week_ago = current_ts - (7 * 86400)
    data["sessions"] = [s for s in data["sessions"] if s.get("timestamp", 0) > one_week_ago]
    
    # Save tracker file
    try:
        tracker_path.write_text(json.dumps(data, indent=4))
    except Exception as e:
        print(f"[WARNING] Failed to write time_tracker.json: {e}")

        
    # 1. Calculate rolling 24h total
    twenty_four_hours_ago = current_ts - 86400
    rolling_24h_seconds = sum(
        s.get("duration_seconds", 0) 
        for s in data["sessions"] 
        if s.get("timestamp", 0) > twenty_four_hours_ago
    )
    
    # 2. Calculate calendar day (IST) total
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ist_now = datetime.now(timezone.utc).astimezone(ist_tz)
    current_date_ist = ist_now.date()
    
    today_ist_seconds = 0
    for s in data["sessions"]:
        s_ts = s.get("timestamp", 0)
        try:
            s_dt_ist = datetime.fromtimestamp(s_ts, timezone.utc).astimezone(ist_tz)
            if s_dt_ist.date() == current_date_ist:
                today_ist_seconds += s.get("duration_seconds", 0)
        except Exception:
            pass
            
    return rolling_24h_seconds, today_ist_seconds
