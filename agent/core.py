import os
import json
import random
import time
from pathlib import Path
from agent.browser import OboeBrowser
from agent.llm import OboeLLM
from curriculum import SkillDAGEngine
from agent.time_tracker import update_time_tracker
from agent.topic_selector import select_topic, remove_topic_from_pool
import config


OBOE_COMPLETION_SIGNALS = [
    "you've completed", "curriculum is complete", "journey is complete",
    "well done on completing", "you've mastered this module", "session complete",
]


class OboeAgent:
    def __init__(self, topic="random", headless=False, resume=False, level_up=False, pin=None, max_duration=None):
        self.topic = topic
        self.browser = OboeBrowser(headless=headless)
        self.llm = OboeLLM()
        self.max_duration = max_duration # in minutes
        self.dag_engine = SkillDAGEngine()

        # Load the scheduler's min_duration_mins so we never allow a wrap-up
        # transition before that floor has elapsed (prevents <10-min early exits).
        self._min_session_seconds = 0
        try:
            sched_path = Path(__file__).resolve().parent.parent / "data" / "scheduler_state.json"
            if sched_path.exists():
                sched = json.loads(sched_path.read_text())
                self._min_session_seconds = int(sched.get("min_duration_mins", 0)) * 60
        except Exception:
            pass
        # Hard floor: even if scheduler file is missing, never wrap-up inside 20 min
        if self._min_session_seconds < 20 * 60:
            self._min_session_seconds = 20 * 60
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
        self.active_track_target_skills = None
        
        self.side_skills = {}
        self.newly_leveled_target_this_turn = False
        self.steering_controller = None

        # session_skills: ALL skills seen on-screen this session (regardless of level-up or classification)
        # This is the source of truth for "what skills did Oboe show during this session"
        # Separate from achieved_skills (which is curriculum-filtered level-ups only)
        self.session_skills = {}


        
        # Load learned skills history
        self.learned_skills_path = Path(__file__).resolve().parent.parent / "data" / "learned_skills.json"
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
        self.last_action_was_q_answer = False  # initialize alongside last_action_was_mcq

    def save_summary(self, status="COMPLETED", start_time=None):
        """Save state and write agent_state.json summary for Telegram notifications."""
        if start_time is None:
            start_time = getattr(self, "active_chat_start_time", None) or getattr(self, "start_time", time.time())
        
        if getattr(self, "active_chat_start_time", None) is None and status == "CANCELLED":
            elapsed_time = 0
        else:
            elapsed_time = max(0, int(time.time() - start_time))
            
        rolling_24h_sec, today_ist_sec = update_time_tracker(elapsed_time, self.topic)
        today_h = int(today_ist_sec // 3600)
        today_m = int((today_ist_sec % 3600) // 60)

        # Save learned skills to disk — always, not just when achieved_skills is populated
        # (skills can be updated in-memory without new achievements, and on SIGTERM
        # _finalize_session is not called, so this is the only save path)
        try:
            self.learned_skills_path.write_text(json.dumps(self.learned_skills, indent=4))
            print(f"[INFO] Saved skill levels to {self.learned_skills_path.name}")
        except Exception as e:
            print(f"[WARNING] Failed to save learned_skills.json: {e}")

        # Update Parent Anchor level metadata for Depth Mode
        if config.SKILL_DEPTH_MODE:
            try:
                from curriculum.mastery_evidence import MasteryEvidenceManager, TREE_FILE
                if TREE_FILE.exists():
                    tree_data = json.loads(TREE_FILE.read_text())
                    anchor_id = self.pin or "maths"
                    parent_lv = MasteryEvidenceManager.get_parent_mastery_level(anchor_id)
                    if anchor_id in tree_data.get("anchors", {}):
                        tree_data["anchors"][anchor_id]["mastery_level"] = parent_lv
                        TREE_FILE.write_text(json.dumps(tree_data, indent=4))
                        print(f"[EVIDENCE] Re-aggregated Parent Anchor Level for '{anchor_id}': LV {parent_lv}")
            except Exception as ee:
                print(f"[EVIDENCE] Error saving parent level: {ee}")

        # Write final session summary to agent_state.json for Telegram notification
        state_path = Path(__file__).resolve().parent.parent / "data" / "agent_state.json"
        try:
            summary = {
                "status": status,
                "topic": self.topic or "Unknown",
                "elapsed_seconds": int(elapsed_time),
                "mcqs_total": self.total_mcqs_count,
                "mcqs_correct": max(0, self.total_mcqs_count - self.wrong_mcqs_count),
                "mcqs_wrong": self.wrong_mcqs_count,
                "today_ist_hours": today_h,
                "today_ist_minutes": today_m,
                "total_today_ist_seconds": int(today_ist_sec),
                "achieved_skills": self.achieved_skills or {},
                "session_skills": self.session_skills or {},
                "side_skills": self.side_skills or {},
                "telemetry": getattr(self.llm, "telemetry", {}),
                "last_session": {
                    "topic": self.topic or "Unknown",
                    "elapsed_seconds": int(elapsed_time),
                    "mcqs_total": self.total_mcqs_count,
                    "mcqs_correct": max(0, self.total_mcqs_count - self.wrong_mcqs_count),
                    "mcqs_wrong": self.wrong_mcqs_count,
                    "today_ist_hours": today_h,
                    "today_ist_minutes": today_m,
                    "total_today_ist_seconds": int(today_ist_sec),
                    "achieved_skills": self.achieved_skills or {},
                    "session_skills": self.session_skills or {},
                    "side_skills": self.side_skills or {},
                    "telemetry": getattr(self.llm, "telemetry", {})
                }
            }
            state_path.write_text(json.dumps(summary, indent=4))
        except Exception as se:
            print(f"[WARNING] Failed to write state file: {se}")

    def _setup_pinned_track_session(self, state_data, state_path):
        """Helper to resolve next topic for pinned track and navigate to its sidebar chat."""
        from curriculum import SkillDAGEngine
        
        resolved = None
        if config.SKILL_DEPTH_MODE:
            try:
                from curriculum.depth_first_resolver import DepthFirstResolver
                resolver = DepthFirstResolver(self.pin)
                resolved = resolver.resolve_next_node()
                print(f"[DFS] Successfully resolved next node target: '{resolved['topic_name']}'")
            except Exception as e:
                print(f"[DFS_FALLBACK] Error in DepthFirstResolver: {e}. Falling back to legacy selector.")
                resolved = None

        if not resolved:
            resolved = SkillDAGEngine.resolve_next_track_topic(self.pin)

        self.active_track_name = resolved["track_name"]
        self.active_track_topic_index = resolved["topic_index"]
        self.active_track_chat_title = resolved["pinned_chat_title"]
        self.topic = resolved["topic_name"]
        self.active_track_target_skills = resolved.get("target_skills", [])
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

    def _setup_normal_session(self, state_data, state_path):
        """Handle normal mode topic selection, navigation, and initial prompt submission."""
        current_url = self.browser.page.url
        if "/chat/" in current_url:
            print("[INFO] Active chat page detected on startup. Navigating to New Chat dashboard...")
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
            result = select_topic(self.level_up, self.dag_engine, self.learned_skills)
            self.topic = result["topic"]
            self.target_skill = result["target_skill"]
            self.target_level = result["target_level"]
            self.active_pillar = result["active_pillar"]
            self.active_node = result["active_node"]

        # Remove the topic from topics.json if it is present (including explicit CLI topics)
        remove_topic_from_pool(self.topic, self.target_skill, self.target_level)

        # Update state file with the actual selected topic
        state_data["topic"] = self.topic
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception:
            pass

        # If a new topic is specified and we are on the dashboard, start it
        state = self.browser.get_interaction_state()
        if self.topic and state == "free_text":
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

    def _run_interaction_loop(self, start_time):
        """Core observe-reason-act loop. Returns when session ends."""
        # Wall-clock timeout for loading state: if Oboe keeps loading for more than
        # 8 minutes continuously, bail out of that wait and move on.
        # This replaces the old consecutive_loadings counter which could reset on
        # DOM flickers, trapping the agent for entire sessions (run-96 bug: 3 calls / 51 min).
        MAX_LOADING_WAIT_SECS = 8 * 60  # 8 minutes
        loading_started_at = None       # wall-clock time loading began

        while True:
            self._save_current_state()
            if self.max_duration and (time.time() - start_time) > (self.max_duration * 60):
                print(f"\n[DURATION LIMIT] Session has reached the maximum duration of {self.max_duration} minutes. Exiting loop cleanly.")
                break

            if self.active_chat_start_time is None:
                self.active_chat_start_time = time.time()

            # First observation
            obs1 = self.browser.observe_page()
            state1 = obs1["state"]

            if state1 == "loading":
                now = time.time()
                if loading_started_at is None:
                    loading_started_at = now
                waited = now - loading_started_at
                if waited > MAX_LOADING_WAIT_SECS:
                    print(f"[TIMEOUT] Page stuck in loading state for {int(waited)}s (>{MAX_LOADING_WAIT_SECS}s limit). Moving on.")
                    loading_started_at = None
                    # Force a re-observe to get whatever partial state exists
                    obs1 = self.browser.observe_page()
                    state1 = obs1["state"]
                    if state1 == "loading":
                        elapsed_so_far = time.time() - start_time
                        if elapsed_so_far < self._min_session_seconds:
                            print(f"[TIMEOUT] Still loading but only {int(elapsed_so_far/60)}m elapsed (min {int(self._min_session_seconds/60)}m). Waiting instead of breaking...")
                            time.sleep(10)
                            continue
                        print("[TIMEOUT] Still loading after timeout. Breaking loop.")
                        break
                    # Fall through to normal handling with current state
                else:
                    remaining = int(MAX_LOADING_WAIT_SECS - waited)
                    print(f"Oboe is thinking/generating... waited {int(waited)}s so far ({remaining}s before timeout)...")
                    time.sleep(3)
                    continue
            else:
                # Not loading — reset the loading wall-clock
                loading_started_at = None

            # Ensure page is stable (Oboe finished typing) — 1s is enough, 2s wastes time
            print("Waiting 1 second to verify page stability...")
            time.sleep(1)
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

            # Evaluate last action (MCQ or conceptual free-text answer)
            # Clear flags immediately before evaluation to prevent double-counting
            # if the page requires multiple loop iterations to stabilize after an action.
            was_mcq = self.last_action_was_mcq
            was_q_answer = self.last_action_was_q_answer
            self.last_action_was_mcq = False
            self.last_action_was_q_answer = False
            if (was_mcq or was_q_answer) and messages:
                assistant_msgs = [m for m in messages if m["role"] == "assistant"]
                if assistant_msgs:
                    oboe_reply = assistant_msgs[-1]["text"].lower()
                    wrong_indicators = ["actually", "incorrect", "wrong", "snag", "correct answer is", "close, but", "consequence of", "different", "not quite"]
                    correct_indicators = ["spot on", "correct", "perfect", "flawless", "exactly", "well done", "right", "great job", "accurate", "precisely"]

                    has_correct = any(ind in oboe_reply for ind in correct_indicators)
                    has_wrong = any(ind in oboe_reply for ind in wrong_indicators)

                    if has_correct and not has_wrong:
                        self.total_mcqs_count += 1
                        print(f"\n>>> [STATS Update] Question Answer: CORRECT! <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                    elif has_wrong:
                        self.total_mcqs_count += 1
                        self.wrong_mcqs_count += 1
                        print(f"\n>>> [STATS Update] Question Answer: INCORRECT <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                    # else: ambiguous response — don't count either way

            # Configured human reading & rate-limit pacing delay (7-20 seconds)
            if messages and messages[-1]["role"] == "assistant":
                reading_delay = round(random.uniform(config.MIN_DELAY, config.MAX_DELAY), 2)
                print(f"Reading Oboe's response... Simulating human delay for {reading_delay:.2f} seconds (Configured Range: {config.MIN_DELAY}-{config.MAX_DELAY}s)...")
                time.sleep(reading_delay)


            # Log new skills and levels, and update memory
            newly_achieved_this_turn = False
            if obs.get("skills"):
                for skill, lv_str in obs["skills"].items():
                    try:
                        new_lv = int(lv_str.replace("LV", "").strip())
                    except ValueError:
                        new_lv = 0

                    # Always record every skill seen on-screen this session at its current level
                    # (even if not a level-up — this is the full picture of what Oboe showed)
                    raw_existing = self.session_skills.get(skill, 0)
                    try:
                        existing_session_lv = int(str(raw_existing).replace("LV", "").replace("lv", "").strip())
                    except (ValueError, TypeError):
                        existing_session_lv = 0
                    if new_lv >= existing_session_lv:
                        self.session_skills[skill] = f"LV {new_lv}"

                    current_max = self.learned_skills.get(skill, 0)
                    if new_lv > current_max:
                        # Genuine level-up: update long-term memory
                        self.learned_skills[skill] = new_lv

                        # Save updated skill levels immediately to disk
                        try:
                            self.learned_skills_path.write_text(json.dumps(self.learned_skills, indent=4))
                            print(f"[DYNAMIC SAVE] Saved skill levels to {self.learned_skills_path.name}")
                        except Exception as se:
                            print(f"[WARNING] Failed to save learned_skills.json: {se}")

                        # Run dynamic adaptation immediately to update target skills in track JSON
                        if getattr(self, "active_track_name", None) is not None and getattr(self, "active_track_target_skills", None) is not None:
                            from agent.skill_adapter import adapt_track_target_skills
                            try:
                                adapt_track_target_skills(
                                    self.active_track_name,
                                    self.active_track_target_skills,
                                    self.learned_skills,
                                    self.achieved_skills,
                                    self.dag_engine.get_track_path
                                )
                                # Reload active target skills after adaptation
                                track_path = self.dag_engine.get_track_path(self.active_track_name)
                                if track_path and track_path.exists():
                                    with open(track_path, "r") as f:
                                        track_data = json.load(f)
                                    self.active_track_target_skills = track_data.get("target_skills", [])
                            except Exception as ex:
                                print(f"[WARNING] Failed dynamic skill adaptation: {ex}")

                        from agent.curriculum_policy import classify_skill
                        track_name = self.active_track_name or self.pin or "maths"
                        cls = classify_skill(track_name, skill)

                        if cls in ("TARGET", "SUPPORTING"):
                            self.achieved_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [ACHIEVEMENT] Skill Level Up: {skill} -> LV {new_lv}! [{cls}] <<<\n")
                            newly_achieved_this_turn = True
                            self.newly_leveled_target_this_turn = True

                            # Reactive MCQ Drift Check: If this is a non-targeted skill that leveled up, flag it!
                            targets = self.active_track_target_skills or []
                            is_target = any(t.lower() in skill.lower() or skill.lower() in t.lower() for t in targets)
                            if not is_target and targets:
                                print(f"[DRIFT DETECTED] Gained level-up in non-target skill: '{skill}' -> LV {new_lv} (Target: {targets})")
                                self.mcq_drift_detected = True
                        elif cls == "SIDE":
                            self.side_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [SIDE SKILL] {skill} -> LV {new_lv} [{cls}] (excluded from curriculum) <<<\n")
                            print(f"[DRIFT DETECTED] Gained level-up in side skill: '{skill}' -> LV {new_lv}")
                            self.mcq_drift_detected = True
                        else:
                            self.side_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [UNKNOWN SKILL] {skill} -> LV {new_lv} [{cls}] (excluded from curriculum) <<<\n")
                            self.mcq_drift_detected = True
                    else:
                        # Not a level-up but still active on screen — log it at existing level
                        from agent.curriculum_policy import classify_skill
                        track_name = self.active_track_name or self.pin or "maths"
                        cls = classify_skill(track_name, skill)
                        if cls == "SIDE":
                            self.side_skills[skill] = lv_str
                        print(f"[SKILL] Active on screen (no level-up): {skill} = {lv_str} [{cls}]")

            # Phase 11.5: Mastery Evidence Engine turn tracking
            if config.SKILL_DEPTH_MODE and messages:
                try:
                    from curriculum.depth_first_resolver import STATE_FILE
                    if STATE_FILE.exists():
                        traversal_state = json.loads(STATE_FILE.read_text())
                        active_track = self.pin or "maths"
                        if "anchors" in traversal_state and active_track in traversal_state["anchors"]:
                            active_node = traversal_state["anchors"][active_track].get("current_node")
                        else:
                            active_node = traversal_state.get("current_node")
                        if active_node:
                            last_msg = messages[-1]["text"]
                            correct_assessment = (self.total_mcqs_count > 0 and self.wrong_mcqs_count == 0)
                            duplicated = len(messages) >= 3 and last_msg == messages[-3]["text"]
                            
                            from curriculum.mastery_evidence import MasteryEvidenceManager
                            MasteryEvidenceManager.record_turn_evidence(
                                node_id=active_node,
                                message_text=last_msg,
                                correct_assessment=correct_assessment,
                                duplicated_content=duplicated
                            )
                except Exception as ee:
                    print(f"[EVIDENCE] Error logging evidence: {ee}")

            print(f"\n[Agent Observe] State: {state.upper()} | Message count: {len(messages)}")
            
            # Check if Oboe has replied to our last turn yet
            if messages and messages[-1]["role"] == "user":
                print("Last message was from user. Waiting for Oboe to reply...")
                time.sleep(3)
                continue

            # ── WRAP-UP CHECK: must run before state branching so it fires on
            #    suggested_replies too (Oboe can show completion + reply buttons).
            #    When completion fires here we handle it and continue the loop.
            if self._is_oboe_indicating_completion(messages, start_time):
                print("[WRAP-UP DETECTED] Oboe indicated completion with corroborating signals.")
                if self.pin:
                    achieved_lv = 0
                    levels = [self.learned_skills.get(skill, 1) for skill in (self.active_track_target_skills or [])]
                    achieved_lv = max(levels) if levels else 1
                    print(f"[WRAP-UP] Pinned track topic complete. Transitioning (Topic #{self.active_track_topic_index}, LV {achieved_lv}).")
                    from curriculum import SkillDAGEngine
                    resolved = None
                    if config.SKILL_DEPTH_MODE:
                        try:
                            from curriculum.depth_first_resolver import STATE_FILE, DepthFirstResolver
                            if STATE_FILE.exists():
                                traversal_state = json.loads(STATE_FILE.read_text())
                                active_track = self.pin or "maths"
                                active_node_key = (traversal_state.get("anchors", {}).get(active_track, {}).get("current_node")
                                                   or traversal_state.get("current_node"))
                                if active_node_key:
                                    from curriculum.mastery_evidence import MasteryEvidenceManager
                                    MasteryEvidenceManager.record_turn_evidence(active_node_key, "", correct_assessment=True)
                            resolver = DepthFirstResolver(self.pin)
                            resolved = resolver.resolve_next_node()
                            print(f"[DFS] Transitioned to next node: '{resolved['topic_name']}'")
                        except Exception as e:
                            print(f"[DFS_FALLBACK] Error: {e}")
                            resolved = None
                    if not resolved:
                        SkillDAGEngine.mark_topic_covered(self.pin, self.active_track_topic_index, achieved_lv)
                        resolved = SkillDAGEngine.resolve_next_track_topic(self.pin)
                    self.active_track_topic_index = resolved["topic_index"]
                    self.topic = resolved["topic_name"]
                    self.active_chat_start_time = time.time()
                    self.active_track_target_skills = resolved.get("target_skills", [])
                    self.steering_controller.request_redirect(reason="track topic completion transition")
                    self.browser.type_and_submit(resolved["prompt"])
                    self.last_action_was_q_answer = True
                else:
                    if self.active_pillar and self.active_node:
                        target_skill_name = self.target_skill or self.active_node.replace("_", " ")
                        achieved_lv = self.learned_skills.get(target_skill_name, 1)
                        self.dag_engine.update_skill_level(self.active_pillar, self.active_node, achieved_lv)
                        result = self.dag_engine.resolve_next_topic()
                        self.topic = result["topic"]
                        self.target_skill = result["target_skill"]
                        self.target_level = result["target_level"]
                        self.active_pillar = result["pillar"]
                        self.active_node = result["node"]
                        self.steering_controller.request_redirect(reason="DAG node completion transition")
                        self.browser.type_and_submit(f"I want to learn about {self.topic}.")
                        self.last_action_was_q_answer = True
                continue

            if state == "suggested_replies":
                print(f"Available options: {choices}")
                
                current_target = self._get_current_target_skill()
                track_name = self.active_track_name or self.pin or "maths"
                
                from agent.curriculum_policy import filter_choices
                filtered = filter_choices(
                    track_name=track_name,
                    target_skill=current_target,
                    choices=choices,
                    dag_engine=self.dag_engine,
                    active_track_topic_index=self.active_track_topic_index
                )
                valid_choices = filtered["valid"]
                preferred = filtered["preferred"]
                rejected = filtered["rejected"]
                
                if rejected:
                    print(f"[CURRICULUM GUARD] Rejected {len(rejected)} off-track option(s): {rejected}")
                
                # Double enforcement: if no valid choices, trigger redirection instead of LLM select
                if not valid_choices:
                    if self._page_accepts_free_text():
                        redirect_text = self.steering_controller.force_redirect()
                        print(f"[CURRICULUM GUARD] Zero valid choices. Injecting steering: '{redirect_text[:60]}...'")
                        self.browser.type_and_submit(redirect_text)
                        self.last_action_was_q_answer = True
                    else:
                        print("[CURRICULUM GUARD] Zero valid choices. Page has no text input. Clicking first option.")
                        self.browser.click_suggestion_by_text(choices[0])
                        self.last_action_was_mcq = True
                    continue
                
                decision = self.llm.decide_action(
                    state, 
                    messages, 
                    valid_choices,  # LLM only sees filtered choices
                    self.learned_skills, 
                    target_skill=current_target, 
                    target_level=self.target_level,
                    target_skills=self.active_track_target_skills,
                    preferred_choices=preferred,
                    is_direction_decision=True
                )
                
                action = decision.get("action")
                if action == "type" and decision.get("text"):
                    if self._page_accepts_free_text():
                        print(f"[CURRICULUM GUARD] LLM rejected MCQ to prevent drift. Typing: '{decision.get('text')[:60]}...'")
                        self.browser.type_and_submit(decision.get("text"))
                        self.last_action_was_q_answer = True
                        continue
                    else:
                        print("[CURRICULUM GUARD] LLM tried to type but page has no text input. Falling back to MCQ click.")

                selection = decision.get("selection")
                
                # Double enforcement: Selection must be in valid_choices
                if selection in valid_choices:
                    self.browser.click_suggestion_by_text(selection)
                elif preferred:
                    fallback = preferred[0]
                    print(f"[ENFORCEMENT] Selected '{selection}' not in valid set. Clicking top preferred: '{fallback}'")
                    self.browser.click_suggestion_by_text(fallback)
                else:
                    fallback = valid_choices[0]
                    print(f"[ENFORCEMENT] Selected '{selection}' not in valid set. Clicking first valid: '{fallback}'")
                    self.browser.click_suggestion_by_text(fallback)
                self.last_action_was_mcq = True

            elif state == "free_text":
                # Update steering controller
                newly_leveled = getattr(self, "newly_leveled_target_this_turn", False)
                self.steering_controller.update(messages, newly_leveled)
                self.newly_leveled_target_this_turn = False

                # Reactive MCQ Drift Steering Redirect
                if getattr(self, "mcq_drift_detected", False):
                    self.mcq_drift_detected = False  # Reset flag
                    steer_topic = self.topic or (self.active_track_target_skills[0] if self.active_track_target_skills else "Kernel Modules")
                    text = f"Let's focus on {steer_topic} for now. Can you challenge me with a question on that instead?"
                    print(f"[CURRICULUM GUARD] Reactive drift steering triggered. Redirecting to: '{text}'")
                else:
                    # Wrap-up is now handled above (before state branching) so it fires
                    # regardless of whether state is free_text or suggested_replies.
                    # Here we only handle normal steering + LLM decision.
                    steering = self.steering_controller.evaluate()
                    if steering:
                        text = steering["text"]
                    else:
                        decision = self.llm.decide_action(
                            state,
                            messages,
                            choices,
                            self.learned_skills,
                            target_skill=self._get_current_target_skill(),
                            target_level=self.target_level,
                            target_skills=self.active_track_target_skills
                        )
                        text = decision.get("text")
                        if not text or str(text).strip() == "" or str(text).lower() == "none":
                            text = "I'm interested to learn more about this."

                self.browser.type_and_submit(text)
                self.last_action_was_q_answer = True


            else:
                # Unknown state — page has no interactive elements.
                # Could be a brief transition, loading gap, or genuine session end.
                # Never break before the minimum session floor has elapsed.
                elapsed_so_far = time.time() - start_time
                if elapsed_so_far < self._min_session_seconds:
                    remaining_min = int((self._min_session_seconds - elapsed_so_far) / 60)
                    print(f"[UNKNOWN STATE] Only {int(elapsed_so_far/60)}m elapsed, minimum is {int(self._min_session_seconds/60)}m. Waiting {remaining_min}m more before considering exit...")
                    time.sleep(10)
                    continue

                print("Unknown or finished state. Waiting 5 seconds to observe any changes...")
                time.sleep(5)
                # Check again — only break if still unknown after re-observation
                new_state = self.browser.get_interaction_state()
                if new_state == "unknown":
                    print("No interactive elements found. Task complete.")
                    self.browser.take_screenshot("session_finished.png")
                    break

            # Sleep to prevent high-frequency loop and allow Oboe platform to render
            time.sleep(2)

    def _get_current_target_skill(self):
        """Determine active target skill of the current turn."""
        if self.pin and self.topic:
            # E.g. self.topic = "Algebra: Number Systems"
            parts = self.topic.split(":")
            if len(parts) > 1:
                prefix = parts[0].strip()
                if self.active_track_target_skills and any(prefix.lower() in t.lower() or t.lower() in prefix.lower() for t in self.active_track_target_skills):
                    matched = next((t for t in self.active_track_target_skills if prefix.lower() in t.lower() or t.lower() in prefix.lower()), prefix)
                    return matched
                return prefix
            if self.active_track_target_skills:
                return self.active_track_target_skills[0]
        return self.target_skill

    def _page_accepts_free_text(self) -> bool:
        """Check if Oboe's current page has a visible free-text input field."""
        try:
            textarea = self.browser.page.locator("textarea, [contenteditable='true']")
            return textarea.count() > 0 and textarea.first.is_visible()
        except Exception:
            return False

    def _is_oboe_indicating_completion(self, messages: list, start_time: float = None) -> bool:
        """
        Check if Oboe is indicating curriculum or topic completion.
        Requires all 4 corroborating signals to avoid false positives:
        1. Last assistant message has a completion phrase.
        2. No active question exists.
        3. No target/supporting skill progress in last 10 turns (raised from 4).
        4. Minimum session elapsed time has passed (respects scheduler min_duration_mins,
           hard floor of 20 min) — prevents DFS cold-start and short-burst exits.
        """
        oboe_msgs = [m for m in messages if m["role"] == "assistant"]
        if not oboe_msgs:
            return False

        last_oboe = oboe_msgs[-1]["text"].lower()

        # 1. Completion phrase
        has_signal = any(sig in last_oboe for sig in OBOE_COMPLETION_SIGNALS)
        if not has_signal:
            return False

        # 2. No active question (check ? and starting question keywords)
        QUESTION_STARTERS = ["what ", "how ", "why ", "can you", "could you", "would you", "do you", "which ", "where "]
        has_question = ("?" in last_oboe or any(last_oboe.strip().startswith(q) for q in QUESTION_STARTERS))
        if has_question:
            return False

        # 3. No recent curriculum progress — raised to 10 turns to prevent DFS cold-start exits
        turns_without_progress = getattr(self.steering_controller, "turns_without_target_skill", 0) if getattr(self, "steering_controller", None) else 0
        if turns_without_progress < 10:
            print(f"[WRAP-UP GUARD] Completion signal detected but only {turns_without_progress}/10 turns without progress. Suppressing.")
            return False

        # 4. Minimum elapsed time guard — never wrap-up before min_duration_mins has elapsed
        if start_time is not None:
            elapsed = time.time() - start_time
            if elapsed < self._min_session_seconds:
                remaining = int((self._min_session_seconds - elapsed) / 60)
                print(f"[WRAP-UP GUARD] Completion signal suppressed — only {int(elapsed/60)}m elapsed, minimum is {int(self._min_session_seconds/60)}m ({remaining}m remaining).")
                return False

        return True

    def _save_current_state(self, status="RUNNING"):
        state_path = Path(__file__).resolve().parent.parent / "data" / "agent_state.json"
        elapsed = time.time() - self.start_time if getattr(self, "start_time", None) else 0
        
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
                    "topic": self.topic
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
            "topic": self.topic,
            "started_at": getattr(self, "start_time", None),
            "elapsed_seconds": int(elapsed),
            "mcqs_total": self.total_mcqs_count,
            "mcqs_wrong": self.wrong_mcqs_count,
            "achieved_skills": self.achieved_skills,
            "last_session": {
                "topic": self.topic,
                "elapsed_seconds": int(elapsed),
                "mcqs_total": self.total_mcqs_count,
                "mcqs_wrong": self.wrong_mcqs_count,
                "achieved_skills": self.achieved_skills,
                "total_24h_seconds": rolling_24h_sec,
                "total_today_ist_seconds": today_ist_sec
            }
        }
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception as e:
            print(f"[WARNING] Failed to write agent_state.json: {e}")

    def _finalize_session(self, start_time, state_path, pid_path):
        """Cleanup: close browser, save skills, update DAG, write final state."""
        # Guard: if the browser never actually started a chat session, skip tracking
        # to prevent writing a garbage 0s "random" entry into time_tracker.json
        session_started = self.active_chat_start_time is not None
        elapsed_time = time.time() - start_time if session_started else 0

        if session_started:
            rolling_24h_sec, today_ist_sec = update_time_tracker(elapsed_time, self.topic)
        else:
            rolling_24h_sec, today_ist_sec = 0, 0

        # Final observation of page to capture any last-second skill badges/level-ups
        if session_started:
            try:
                if self.browser.page and not self.browser.page.is_closed():
                    final_obs = self.browser.observe_page()
                    if final_obs.get("skills"):
                        for skill, lv_str in final_obs["skills"].items():
                            try:
                                new_lv = int(lv_str.replace("LV", "").strip())
                            except ValueError:
                                print(f"[WARNING] Could not parse skill level: '{lv_str}' for skill '{skill}'")
                                new_lv = 0
                            current_max = self.learned_skills.get(skill, 0)
                            if new_lv > current_max:
                                self.learned_skills[skill] = new_lv
                                self.achieved_skills[skill] = f"LV {new_lv}"
                                print(f"[FINAL CHECK] Captured Skill Level Up: {skill} -> LV {new_lv}!")
            except Exception as e:
                print(f"[INFO] Final skill observation status: {e}")

        try:
            self.browser.close()
        except Exception as close_err:
            print(f"[INFO] Browser close status: {close_err}")
        except KeyboardInterrupt:
            print("\n[INFO] Browser shutdown interrupted.")
            raise  # re-raise so OS gets a clean shutdown signal
            
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

        # Dynamic Skill Adaptation Check for Pinned Tracks
        if getattr(self, "active_track_name", None) is not None and getattr(self, "active_track_target_skills", None) is not None:
            from agent.skill_adapter import adapt_track_target_skills
            adapt_track_target_skills(
                self.active_track_name,
                self.active_track_target_skills,
                self.learned_skills,
                self.achieved_skills,
                self.dag_engine.get_track_path
            )

        # Mark pinned track topic as covered
        if getattr(self, "active_track_name", None) is not None and getattr(self, "active_track_topic_index", None) is not None:
            from curriculum import SkillDAGEngine
            # Parse numeric level from "LV N" strings before taking max
            def _parse_lv(lv_str):
                try:
                    return int(str(lv_str).replace("LV", "").replace("lv", "").strip())
                except (ValueError, AttributeError):
                    return 0
            max_achieved = max((_parse_lv(v) for v in self.achieved_skills.values()), default=0)
            SkillDAGEngine.mark_topic_covered(self.active_track_name, self.active_track_topic_index, max_achieved)

        if self.achieved_skills:
            print(f"[INFO] Skills leveled up: {self.achieved_skills}.")

        self.save_summary(status=self._final_status, start_time=start_time)

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
            # Do NOT call save_summary here — the finally block calls _finalize_session
            # which calls save_summary exactly once. Calling it here would double-count
            # the session's elapsed time in time_tracker.json.
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
        pid_path = Path(__file__).resolve().parent.parent / "agent.pid"
        try:
            pid_path.write_text(str(os.getpid()))
        except Exception as pe:
            print(f"[WARNING] Failed to write PID file: {pe}")

        # Write initial state
        state_path = Path(__file__).resolve().parent.parent / "data" / "agent_state.json"
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
                    self._setup_normal_session(state_data, state_path)
            
            # Initialize Steering Controller before loop starts
            from agent.steering_controller import SteeringController
            target_skills = self.active_track_target_skills or []
            if not target_skills and self.target_skill:
                target_skills = [self.target_skill]
            if not target_skills and self.pin:
                try:
                    track_data = self.dag_engine.load_track(self.pin)
                    target_skills = track_data.get("target_skills", [])
                except Exception:
                    pass

            self.steering_controller = SteeringController(
                track_name=self.active_track_name or self.pin or "maths",
                target_skills=target_skills,
                dag_engine=self.dag_engine
            )

            # Run the interaction loop
            self._run_interaction_loop(start_time)


        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
        except Exception as e:
            print(f"Error in agent execution: {e}")
            self.browser.take_screenshot("error_state.png")
        finally:
            self._finalize_session(start_time, state_path, pid_path)
