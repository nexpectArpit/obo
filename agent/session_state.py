import time
import json
from pathlib import Path
from agent.time_tracker import update_time_tracker
import config

class OboeStateManager:
    @staticmethod
    def save_current_state(agent, status="RUNNING"):
        state_path = Path(__file__).resolve().parent.parent / "data" / "agent_state.json"
        elapsed = time.time() - agent.start_time if getattr(agent, "start_time", None) else 0
        
        # Calculate live IST totals by reading the time tracker history
        rolling_24h_sec = 0
        today_ist_sec = 0
        try:
            tracker_path = Path(__file__).resolve().parent.parent / "data" / "time_tracker.json"
            if tracker_path.exists():
                data = json.loads(tracker_path.read_text())
                sessions = data.get("sessions", [])
                
                # Combine history with a virtual session of the current elapsed time
                current_ts = time.time()
                virtual_session = {
                    "timestamp": current_ts,
                    "duration_seconds": round(elapsed),
                    "topic": agent.topic
                }
                temp_sessions = sessions + [virtual_session]
                
                # Deduplicate concurrent entries to match update_time_tracker logic
                deduplicated = []
                for s in temp_sessions:
                    is_dup = False
                    s_ts = s.get("timestamp", 0)
                    s_topic = s.get("topic", "")
                    for existing in deduplicated:
                        e_ts = existing.get("timestamp", 0)
                        e_topic = existing.get("topic", "")
                        same_topic_close = (s_topic == e_topic and abs(s_ts - e_ts) < 300)
                        any_topic_very_close = (abs(s_ts - e_ts) < 5)
                        if same_topic_close or any_topic_very_close:
                            is_dup = True
                            if s.get("duration_seconds", 0) > existing.get("duration_seconds", 0):
                                existing["duration_seconds"] = s["duration_seconds"]
                            break
                    if not is_dup:
                        deduplicated.append(s)
                
                # Calculate rolling 24h
                twenty_four_hours_ago = current_ts - 86400
                rolling_24h_sec = sum(s.get("duration_seconds", 0) for s in deduplicated if s.get("timestamp", 0) > twenty_four_hours_ago)
                
                # Calculate calendar day (IST)
                from datetime import datetime, timezone, timedelta
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                ist_now = datetime.now(timezone.utc).astimezone(ist_tz)
                current_date_ist = ist_now.date()
                
                for s in deduplicated:
                    s_ts = s.get("timestamp", 0)
                    try:
                        s_dt_ist = datetime.fromtimestamp(s_ts, timezone.utc).astimezone(ist_tz)
                        if s_dt_ist.date() == current_date_ist:
                            today_ist_sec += s.get("duration_seconds", 0)
                    except Exception:
                        pass
        except Exception:
            pass

        state_data = {
            "status": status,
            "topic": agent.topic,
            "started_at": getattr(agent, "start_time", None),
            "elapsed_seconds": int(elapsed),
            "mcqs_total": agent.stats.total_mcqs_count,
            "mcqs_wrong": agent.stats.wrong_mcqs_count,
            "achieved_skills": agent.achieved_skills,
            "last_session": {
                "topic": agent.topic,
                "elapsed_seconds": int(elapsed),
                "mcqs_total": agent.stats.total_mcqs_count,
                "mcqs_wrong": agent.stats.wrong_mcqs_count,
                "achieved_skills": agent.achieved_skills,
                "total_24h_seconds": rolling_24h_sec,
                "total_today_ist_seconds": today_ist_sec
            }
        }
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception as e:
            print(f"[WARNING] Failed to write agent_state.json: {e}")

    @staticmethod
    def finalize_session(agent, start_time, state_path, pid_path, status="COMPLETED"):
        """Cleanup: save final state, close browser, save skills, update DAG."""
        session_started = agent.active_chat_start_time is not None
        elapsed_time = time.time() - start_time if session_started else 0

        if session_started:
            rolling_24h_sec, today_ist_sec = update_time_tracker(elapsed_time, agent.topic)
        else:
            rolling_24h_sec, today_ist_sec = 0, 0

        # Save learned skills to disk
        try:
            agent.learned_skills_path.write_text(json.dumps(agent.learned_skills, indent=4))
            print(f"[INFO] Saved skill levels to {agent.learned_skills_path.name}")
        except Exception as e:
            print(f"[WARNING] Failed to save learned_skills.json: {e}")

        # Update Parent Anchor level metadata for Depth Mode
        if config.SKILL_DEPTH_MODE:
            try:
                from curriculum.mastery_evidence import MasteryEvidenceManager, TREE_FILE
                if TREE_FILE.exists():
                    tree_data = json.loads(TREE_FILE.read_text())
                    anchor_id = agent.pin or "maths"
                    parent_lv = MasteryEvidenceManager.get_parent_mastery_level(anchor_id)
                    if anchor_id in tree_data.get("anchors", {}):
                        tree_data["anchors"][anchor_id]["mastery_level"] = parent_lv
                        TREE_FILE.write_text(json.dumps(tree_data, indent=4))
                        print(f"[EVIDENCE] Re-aggregated Parent Anchor Level for '{anchor_id}': LV {parent_lv}")
            except Exception as ee:
                print(f"[EVIDENCE] Error saving parent level: {ee}")

        # Write final session summary to agent_state.json immediately (before browser closing, which can hang)
        today_h = int(today_ist_sec // 3600)
        today_m = int((today_ist_sec % 3600) // 60)
        try:
            summary = {
                "status": status,
                "topic": agent.topic or "Unknown",
                "elapsed_seconds": int(elapsed_time),
                "mcqs_total": agent.stats.total_mcqs_count,
                "mcqs_correct": max(0, agent.stats.total_mcqs_count - agent.stats.wrong_mcqs_count),
                "mcqs_wrong": agent.stats.wrong_mcqs_count,
                "today_ist_hours": today_h,
                "today_ist_minutes": today_m,
                "total_today_ist_seconds": int(today_ist_sec),
                "achieved_skills": agent.achieved_skills or {},
                "session_skills": agent.session_skills or {},
                "side_skills": agent.side_skills or {},
                "telemetry": getattr(agent.llm, "telemetry", {}),
                "last_session": {
                    "topic": agent.topic or "Unknown",
                    "elapsed_seconds": int(elapsed_time),
                    "mcqs_total": agent.stats.total_mcqs_count,
                    "mcqs_correct": max(0, agent.stats.total_mcqs_count - agent.stats.wrong_mcqs_count),
                    "mcqs_wrong": agent.stats.wrong_mcqs_count,
                    "today_ist_hours": today_h,
                    "today_ist_minutes": today_m,
                    "total_today_ist_seconds": int(today_ist_sec),
                    "achieved_skills": agent.achieved_skills or {},
                    "session_skills": agent.session_skills or {},
                    "side_skills": agent.side_skills or {},
                    "telemetry": getattr(agent.llm, "telemetry", {})
                }
            }
            state_path.write_text(json.dumps(summary, indent=4))
        except Exception as state_err:
            print(f"[WARNING] Failed to write final agent_state.json: {state_err}")

        # Clean up PID
        if pid_path.exists():
            try: pid_path.unlink()
            except Exception: pass

        # Close browser last
        try:
            agent.browser.close()
        except Exception as close_err:
            print(f"[INFO] Browser close status: {close_err}")
        except KeyboardInterrupt:
            print("\n[INFO] Browser shutdown interrupted.")
            raise
