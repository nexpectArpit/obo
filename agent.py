import os
import json
import random
import time
from pathlib import Path
from browser import OboeBrowser
from llm import OboeLLM
from skill_dag_engine import SkillDAGEngine
import config


# Load topics from topics.json
topics_path = Path(__file__).resolve().parent / "topics.json"
try:
    with open(topics_path, "r") as f:
        RANDOM_TOPICS = json.load(f)
except Exception:
    RANDOM_TOPICS = {"new_topics": ["Quantum computing basics"], "level_up_topics": []}


class OboeAgent:
    def __init__(self, topic="random", headless=False, resume=False, level_up=False, pin=None):
        self.topic = topic
        self.browser = OboeBrowser(headless=headless)
        self.llm = OboeLLM()
        self.dag_engine = SkillDAGEngine()
        self.resume = resume
        self.level_up = level_up
        self.pin = pin  # Pinned track name (e.g. "cpp", "os", "dl")
        self.target_skill = None
        self.target_level = None
        self.active_pillar = None
        self.active_node = None
        self.active_chat_start_time = None
        # Pinned track session state
        self.active_track_name = None
        self.active_track_topic_index = None
        self.active_track_chat_title = None

        
        # Load learned skills history
        self.learned_skills_path = Path(__file__).resolve().parent / "learned_skills.json"
        self.learned_skills = {}
        if self.learned_skills_path.exists():
            try:
                self.learned_skills = json.loads(self.learned_skills_path.read_text())
            except Exception as e:
                print(f"[WARNING] Failed to load learned_skills.json: {e}")
                
        self.achieved_skills = {}
        self.total_mcqs_count = 0
        self.wrong_mcqs_count = 0
        self.last_action_was_mcq = False

    def update_time_tracker(self, elapsed_time):
        """Track sessions and calculate rolling 24h & calendar day (IST) totals."""
        tracker_path = Path(__file__).resolve().parent / "time_tracker.json"
        
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
            "topic": self.topic
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
        from datetime import datetime, timezone, timedelta
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

    def save_summary(self, status="COMPLETED", start_time=None):
        """Save state and write agent_state.json summary for Telegram notifications."""
        if start_time is None:
            start_time = getattr(self, "active_chat_start_time", None) or getattr(self, "start_time", time.time())
        
        if getattr(self, "active_chat_start_time", None) is None and status == "CANCELLED":
            elapsed_time = 0
        else:
            elapsed_time = max(0, int(time.time() - start_time))
            
        rolling_24h_sec, today_ist_sec = self.update_time_tracker(elapsed_time)
        today_h = int(today_ist_sec // 3600)
        today_m = int((today_ist_sec % 3600) // 60)

        # Save learned skills to disk
        if self.achieved_skills:
            try:
                self.learned_skills_path.write_text(json.dumps(self.learned_skills, indent=4))
                print(f"[INFO] Saved skill levels to {self.learned_skills_path.name}")
            except Exception as e:
                print(f"[WARNING] Failed to save learned_skills.json: {e}")

        # Write final session summary to agent_state.json for Telegram notification
        state_path = Path(__file__).resolve().parent / "agent_state.json"
        try:
            summary = {
                "status": status,
                "topic": self.topic or "Unknown",
                "elapsed_seconds": int(elapsed_time),
                "mcqs_total": self.total_mcqs_count,
                "mcqs_correct": self.total_mcqs_count - self.wrong_mcqs_count,
                "mcqs_wrong": self.wrong_mcqs_count,
                "today_ist_hours": today_h,
                "today_ist_minutes": today_m,
                "achieved_skills": self.achieved_skills or {},
                "telemetry": getattr(self.llm, "telemetry", {})
            }
            state_path.write_text(json.dumps(summary, indent=4))
        except Exception as se:
            print(f"[WARNING] Failed to write state file: {se}")

    def _setup_pinned_track_session(self, state_data, state_path):
        """Helper to resolve next topic for pinned track and navigate to its sidebar chat."""
        from skill_dag_engine import SkillDAGEngine
        resolved = SkillDAGEngine.resolve_next_track_topic(self.pin)
        self.active_track_name = resolved["track_name"]
        self.active_track_topic_index = resolved["topic_index"]
        self.active_track_chat_title = resolved["pinned_chat_title"]
        self.topic = resolved["topic_name"]
        track_prompt = resolved["prompt"]

        print(f"\n{'='*60}")
        print(f"[PINNED TRACK] Track: {self.pin}")
        print(f"[PINNED TRACK] Chat: '{self.active_track_chat_title}'")
        print(f"[PINNED TRACK] Topic #{resolved['topic_index']}: {self.topic}")
        print(f"[PINNED TRACK] Prompt: {track_prompt[:100]}...")
        print(f"{'='*60}\n")

        # Navigate to the pinned chat in the sidebar
        # Open sidebar if needed
        trigger = self.browser.page.locator('[data-sidebar="trigger"]')
        if trigger.count() > 0 and trigger.first.is_visible():
            trigger.first.click()
            time.sleep(2)

        # Look for the pinned chat link in the PINNED section
        pinned_title = self.active_track_chat_title
        # Try matching by partial text in sidebar links
        all_links = self.browser.page.locator('a[href*="/chat/"]').all()
        target_link = None
        for link in all_links:
            link_text = (link.text_content() or "").strip()
            if pinned_title.lower() in link_text.lower() or link_text.lower() in pinned_title.lower():
                target_link = link
                break

        if target_link:
            chat_href = target_link.get_attribute("href") or ""
            print(f"[PINNED TRACK] Found pinned chat: '{pinned_title}' -> {chat_href}")
            target_link.click()
            time.sleep(5)
            # Type the sub-topic prompt into the existing chat
            self.browser.type_and_submit(track_prompt)
            self.active_chat_start_time = time.time()
            time.sleep(5)
        else:
            print(f"[WARNING] Could not find pinned chat '{pinned_title}' in sidebar. Falling back to new chat.")
            # Fallback: start a new chat with the topic
            new_chat_btn = self.browser.page.locator('button').filter(has_text="New Chat")
            if new_chat_btn.count() > 0:
                new_chat_btn.first.click()
                time.sleep(3)
            self.browser.type_and_submit(track_prompt)
            self.active_chat_start_time = time.time()
            time.sleep(5)

        # Update state file
        state_data["topic"] = self.topic
        state_data["pinned_track"] = self.pin
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception:
            pass

    def run(self):
        """Run the main observe-reason-act loop."""
        import signal, sys
        print("Starting obo agent...")
        start_time = time.time()
        self.start_time = start_time
        self._final_status = "COMPLETED"

        def handle_signal(sig, frame):
            print(f"\n[INFO] Received signal {sig}. Interrupted/Cancelled. Saving session state...")
            self._final_status = "CANCELLED"
            self.save_summary(status="CANCELLED", start_time=start_time)
            try:
                self.browser.close()
            except Exception:
                pass
            sys.exit(0)

        try:
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
        except Exception:
            pass
        
        # Write PID file
        pid_path = Path(__file__).resolve().parent / "agent.pid"
        try:
            pid_path.write_text(str(os.getpid()))
        except Exception as pe:
            print(f"[WARNING] Failed to write PID file: {pe}")

        # Write initial state
        state_path = Path(__file__).resolve().parent / "agent_state.json"
        state_data = {
            "status": "RUNNING",
            "topic": self.topic,
            "started_at": start_time
        }
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception as se:
            print(f"[WARNING] Failed to write state file: {se}")

        try:
            self.browser.start()
            self.browser.navigate_to_home()
            
            if self.resume:
                # Target history links specifically (skipping PINNED section)
                history_xpath = 'xpath=//div[text()="Chat History"]/following::a[contains(@href, "/chat/")]'
                
                # Check if links are already visible
                links = self.browser.page.locator(history_xpath).all()
                if not links:
                    # Sidebar is collapsed, toggle it
                    trigger = self.browser.page.locator('[data-sidebar="trigger"]')
                    if trigger.count() > 0 and trigger.first.is_visible():
                        print("[INFO] Collapsed sidebar detected. Toggling sidebar trigger to show history...")
                        trigger.first.click()
                        time.sleep(2)
                    else:
                        print("[INFO] Sidebar trigger is hidden/already open. Waiting for links...")
                        time.sleep(2)
                    links = self.browser.page.locator(history_xpath).all()

                # Find the most recent chat in the Chat History list and click it
                if links:
                    target_link = links[0]
                    chat_title = (target_link.text_content() or "").strip()
                    target_href = target_link.get_attribute("href")
                    print(f"\n==================================================")
                    print(f"[INFO] RESUMING CHAT: '{chat_title}'")
                    print(f"[INFO] Href: {target_href}")
                    print("==================================================\n")
                    target_link.click()
                    # Wait for chat history to fully render
                    time.sleep(5)
                else:
                    print("[WARNING] No chat history found to resume. Proceeding with topic selection.")
                    self.resume = False

            if not self.resume:
                # ──── PINNED TRACK MODE ────────────────────────────────
                if self.pin:
                    self._setup_pinned_track_session(state_data, state_path)

                # ──── NORMAL MODE (Random / Level-Up / Custom Topic) ───
                else:
                    # If the browser defaults to an active chat page, force a fresh session
                    current_url = self.browser.page.url
                    if "/chat/" in current_url:
                        print("[INFO] Active chat page detected on startup. Navigating to New Chat dashboard...")
                        # Toggle sidebar trigger to ensure New Chat button is clickable
                        trigger = self.browser.page.locator('[data-sidebar="trigger"]')
                        if trigger.count() > 0:
                            trigger.first.click()
                            time.sleep(1.5)
                        
                        new_chat_btn = self.browser.page.locator('button').filter(has_text="New Chat")
                        if new_chat_btn.count() > 0:
                            new_chat_btn.first.click()
                            print("[INFO] Clicked 'New Chat' button successfully.")
                            time.sleep(3)

                    # If topic is random, select one from the list
                    if self.topic == "random":
                        new_list = RANDOM_TOPICS.get("new_topics", [])
                        lvl_list = RANDOM_TOPICS.get("level_up_topics", [])
                        
                        if self.level_up:
                            # Use zero-LLM deterministic DAG Curriculum Manager
                            resolved = self.dag_engine.resolve_next_topic()
                            self.topic = resolved["topic"]
                            self.target_skill = resolved.get("target_skill")
                            self.target_level = resolved.get("target_level")
                            self.active_pillar = resolved.get("pillar")
                            self.active_node = resolved.get("node")
                            print(f"[INFO] Selected DAG curriculum topic: '{self.topic}' (Pillar: '{resolved.get('pillar_name', self.active_pillar)}') targeting '{self.target_skill}' to LV {self.target_level}")

                        else:
                            combined = []
                            for t in new_list:
                                combined.append(("new", t))
                            for entry in lvl_list:
                                if isinstance(entry, dict) and "topic" in entry:
                                    combined.append(("level_up", entry))
                                    
                            if combined:
                                choice_type, entry = random.choice(combined)
                                if choice_type == "level_up":
                                    self.topic = entry["topic"]
                                    self.target_skill = entry.get("associated_skill")
                                    self.target_level = entry.get("level_target")
                                else:
                                    self.topic = entry
                                print(f"[INFO] Selected random learning topic: '{self.topic}' (type: {choice_type})")
                            else:
                                self.topic = "Quantum computing basics"
                                print("[WARNING] topics.json is empty! Defaulting to 'Quantum computing basics'")

                    # Remove the topic from topics.json if it is present (including explicit CLI topics)
                    new_list = RANDOM_TOPICS.get("new_topics", [])
                    lvl_list = RANDOM_TOPICS.get("level_up_topics", [])
                    
                    removed = False
                    if self.topic in new_list:
                        new_list.remove(self.topic)
                        removed = True
                    else:
                        for entry in list(lvl_list):
                            if isinstance(entry, dict):
                                entry_top = entry.get("topic", "")
                                # Remove exact topic match or any duplicate entry targeting the same skill level
                                if entry_top == self.topic or (self.target_skill and entry.get("associated_skill") == self.target_skill and entry.get("level_target") == self.target_level):
                                    lvl_list.remove(entry)
                                    removed = True

                                
                    RANDOM_TOPICS["new_topics"] = new_list
                    RANDOM_TOPICS["level_up_topics"] = lvl_list

                    # Save updated list back to topics.json
                    try:
                        with open(topics_path, "w") as f:
                            json.dump(RANDOM_TOPICS, f, indent=4)
                        if removed:
                            print(f"[INFO] Removed '{self.topic}' from topics.json to prevent repeats.")
                    except Exception as e:
                        print(f"[WARNING] Failed to save updated topics.json: {e}")

                    # Update state file with the actual selected topic
                    state_data["topic"] = self.topic
                    try:
                        state_path.write_text(json.dumps(state_data, indent=4))
                    except Exception:
                        pass

                    # If a new topic is specified and we are on the dashboard, start it
                    state = self.browser.get_interaction_state()
                    if self.topic and state == "free_text":
                        # Check if the page is the new chat dashboard (placeholder exists)
                        textarea = self.browser.page.locator('textarea[name="prompt"]')
                        placeholder = textarea.get_attribute("placeholder") or ""
                        if "I want to learn" in placeholder:
                            # Determine prompt based on target skill and level
                            if self.target_skill:
                                current_lv = self.learned_skills.get(self.target_skill, 0)
                                if current_lv >= 4:
                                    initial_prompt = f"I'm already very familiar with the basics of {self.topic}. Can we skip the introductory stuff and dive straight into the advanced concepts/complex math? I'd love to challenge myself with some tough questions."
                                elif current_lv == 3:
                                    initial_prompt = f"I understand the basic overview of {self.topic} already. Let's look at the intermediate concepts and the math behind them."
                                else:
                                    initial_prompt = f"I want to learn about {self.topic}. Can we start with the core concepts?"
                            else:
                                initial_prompt = self.topic

                            print(f"Starting new chat with prompt: '{initial_prompt}'")
                            self.browser.type_and_submit(initial_prompt)
                            self.active_chat_start_time = time.time()
                            # Allow generation to kick off
                            time.sleep(5)
            
            # Run the interaction loop
            consecutive_loadings = 0
            while True:
                if self.active_chat_start_time is None:
                    self.active_chat_start_time = time.time()

                # First observation
                obs1 = self.browser.observe_page()
                state1 = obs1["state"]

                if state1 == "loading":
                    consecutive_loadings += 1
                    if consecutive_loadings > 30:
                        print("Page stuck in loading state for too long. Exiting.")
                        break
                    print("Oboe is thinking/generating... waiting 3 seconds...")
                    time.sleep(3)
                    continue

                # Ensure page is stable (Oboe finished typing)
                print("Waiting 5 seconds to verify page stability...")
                time.sleep(5)
                obs2 = self.browser.observe_page()
                state2 = obs2["state"]

                if state1 != state2:
                    print("Page state changed during wait. Retrying observation...")
                    continue
                if len(obs1["messages"]) != len(obs2["messages"]):
                    print("New messages arrived. Oboe is still writing...")
                    continue
                if obs1["messages"] and obs2["messages"]:
                    last_msg_1 = obs1["messages"][-1]
                    last_msg_2 = obs2["messages"][-1]
                    if last_msg_1["role"] == last_msg_2["role"] and last_msg_1["text"] != last_msg_2["text"]:
                        print("Message text is updating. Oboe is still typing...")
                        continue

                # Page is stable, proceed with decision
                obs = obs2
                state = state2
                choices = obs["choices"]
                messages = obs["messages"]

                # Evaluate last MCQ action result if applicable
                if self.last_action_was_mcq and messages:
                    # Find the last assistant message (Oboe's reply to our choice selection)
                    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
                    if assistant_msgs:
                        oboe_reply = assistant_msgs[-1]["text"].lower()
                        self.total_mcqs_count += 1
                        wrong_indicators = ["actually", "incorrect", "wrong", "snag", "correct answer is", "close, but", "consequence of", "different"]
                        if any(ind in oboe_reply for ind in wrong_indicators):
                            self.wrong_mcqs_count += 1
                            print(f"\n>>> [STATS Update] MCQ Answer: INCORRECT <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                        else:
                            print(f"\n>>> [STATS Update] MCQ Answer: CORRECT! <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                    self.last_action_was_mcq = False

                # Configured human reading & rate-limit pacing delay (7-20 seconds)
                if messages and messages[-1]["role"] == "assistant":
                    reading_delay = round(random.uniform(config.MIN_DELAY, config.MAX_DELAY), 2)
                    print(f"Reading Oboe's response... Simulating human delay for {reading_delay:.2f} seconds (Configured Range: {config.MIN_DELAY}-{config.MAX_DELAY}s)...")
                    time.sleep(reading_delay)


                # Log new skills and levels, and update memory
                if obs.get("skills"):
                    for skill, lv_str in obs["skills"].items():
                        try:
                            new_lv = int(lv_str.replace("LV", "").strip())
                        except ValueError:
                            new_lv = 0
                        current_max = self.learned_skills.get(skill, 0)
                        if new_lv > current_max:
                            self.learned_skills[skill] = new_lv
                            self.achieved_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [ACHIEVEMENT] Skill Level Up: {skill} -> LV {new_lv}! <<<\n")

                print(f"\n[Agent Observe] State: {state.upper()} | Message count: {len(messages)}")
                
                # Check if Oboe has replied to our last turn yet
                if messages and messages[-1]["role"] == "user":
                    print("Last message was from user. Waiting for Oboe to reply...")
                    time.sleep(3)
                    continue

                consecutive_loadings = 0

                if state == "suggested_replies":
                    print(f"Available options: {choices}")
                    decision = self.llm.decide_action(
                        state, 
                        messages, 
                        choices, 
                        self.learned_skills, 
                        target_skill=self.target_skill, 
                        target_level=self.target_level
                    )
                    selection = decision.get("selection")
                    if selection in choices:
                        self.browser.click_suggestion_by_text(selection)
                    else:
                        # Fallback click first
                        print(f"Warning: Selected option '{selection}' not in choices. Clicking first choice.")
                        self.browser.click_suggestion_by_text(choices[0])
                    self.last_action_was_mcq = True

                elif state == "free_text":
                    decision = self.llm.decide_action(
                        state, 
                        messages, 
                        choices, 
                        self.learned_skills, 
                        target_skill=self.target_skill, 
                        target_level=self.target_level
                    )
                    text = decision.get("text")
                    if not text or str(text).strip() == "" or str(text).lower() == "none":
                        text = "I'm interested to learn more about this."
                    self.browser.type_and_submit(text)

                else:
                    # Unknown state (perhaps course completed or error)
                    print("Unknown or finished state. Waiting 5 seconds to observe any changes...")
                    time.sleep(5)
                    # Check again, if still unknown, stop.
                    new_state = self.browser.get_interaction_state()
                    if new_state == "unknown":
                        print("No interactive elements found. Task complete.")
                        self.browser.take_screenshot("session_finished.png")
                        break

                # Sleep to prevent high-frequency loop and allow Oboe platform to render
                time.sleep(2)

        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
        except Exception as e:
            print(f"Error in agent execution: {e}")
            self.browser.take_screenshot("error_state.png")
        finally:
            elapsed_time = time.time() - start_time
            rolling_24h_sec, today_ist_sec = self.update_time_tracker(elapsed_time)
            
            rolling_h, rolling_m = rolling_24h_sec // 3600, (rolling_24h_sec % 3600) // 60
            today_h, today_m = today_ist_sec // 3600, (today_ist_sec % 3600) // 60
            
            try:
                self.browser.close()
            except Exception as close_err:
                print(f"[INFO] Browser close status: {close_err}")
            except KeyboardInterrupt:
                print("\n[INFO] Browser shutdown interrupted.")
                
            # Clean up PID
            if pid_path.exists():
                try: pid_path.unlink()
                except Exception: pass
                
            # Update state file
            state_data = {
                "status": "STOPPED",
                "topic": None,
                "started_at": None,
                "last_session": {
                    "topic": self.topic,
                    "elapsed_seconds": int(elapsed_time),
                    "mcqs_total": self.total_mcqs_count,
                    "mcqs_wrong": self.wrong_mcqs_count,
                    "achieved_skills": self.achieved_skills,
                    "total_24h_seconds": rolling_24h_sec,
                    "total_today_ist_seconds": today_ist_sec
                }
            }
            try:
                state_path.write_text(json.dumps(state_data, indent=4))
            except Exception:
                pass

            # Save updated skill levels
            try:
                self.learned_skills_path.write_text(json.dumps(self.learned_skills, indent=4))
                print(f"[INFO] Saved skill levels to {self.learned_skills_path.name}")
            except Exception as se:
                print(f"[WARNING] Failed to save learned_skills.json: {se}")

            # Update DAG Curriculum Engine graph state based on actual achieved levels
            if getattr(self, "active_pillar", None) and getattr(self, "active_node", None):
                target_skill_name = self.target_skill or self.active_node.replace("_", " ")
                achieved_lv = self.learned_skills.get(target_skill_name, 1)
                self.dag_engine.update_skill_level(self.active_pillar, self.active_node, achieved_lv)

            # Mark pinned track topic as covered
            if getattr(self, "active_track_name", None) is not None and getattr(self, "active_track_topic_index", None) is not None:
                from skill_dag_engine import SkillDAGEngine
                # Find the highest achieved level across all skills this session
                max_achieved = max(self.achieved_skills.values()) if self.achieved_skills else 0
                SkillDAGEngine.mark_topic_covered(self.active_track_name, self.active_track_topic_index, max_achieved)

            if self.achieved_skills:
                print(f"[INFO] Skills leveled up: {self.achieved_skills}.")

            self.save_summary(status=self._final_status, start_time=start_time)

