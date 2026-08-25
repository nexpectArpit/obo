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

        # Save learned skills to disk
        if self.achieved_skills:
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

    def _run_interaction_loop(self, start_time):
        """Core observe-reason-act loop. Returns when session ends."""
        consecutive_loadings = 0
        while True:
            if self.max_duration and (time.time() - start_time) > (self.max_duration * 60):
                print(f"\n[DURATION LIMIT] Session has reached the maximum duration of {self.max_duration} minutes. Exiting loop cleanly.")
                break

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

            # Evaluate last action (MCQ or conceptual free-text answer)
            if (getattr(self, "last_action_was_mcq", False) or getattr(self, "last_action_was_q_answer", False)) and messages:
                assistant_msgs = [m for m in messages if m["role"] == "assistant"]
                if assistant_msgs:
                    oboe_reply = assistant_msgs[-1]["text"].lower()
                    wrong_indicators = ["actually", "incorrect", "wrong", "snag", "correct answer is", "close, but", "consequence of", "different", "not quite"]
                    correct_indicators = ["spot on", "correct", "perfect", "flawless", "exactly", "well done", "right", "great job", "accurate", "precisely"]
                    
                    if any(ind in oboe_reply for ind in correct_indicators) or not any(ind in oboe_reply for ind in wrong_indicators):
                        self.total_mcqs_count += 1
                        print(f"\n>>> [STATS Update] Question Answer: CORRECT! <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                    else:
                        self.total_mcqs_count += 1
                        self.wrong_mcqs_count += 1
                        print(f"\n>>> [STATS Update] Question Answer: INCORRECT <<< (Total: {self.total_mcqs_count}, Wrong: {self.wrong_mcqs_count})\n")
                self.last_action_was_mcq = False
                self.last_action_was_q_answer = False

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
                    current_max = self.learned_skills.get(skill, 0)
                    if new_lv > current_max:
                        self.learned_skills[skill] = new_lv
                        
                        from agent.curriculum_policy import classify_skill
                        track_name = self.active_track_name or self.pin or "maths"
                        cls = classify_skill(track_name, skill)
                        
                        if cls in ("TARGET", "SUPPORTING"):
                            self.achieved_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [ACHIEVEMENT] Skill Level Up: {skill} -> LV {new_lv}! [{cls}] <<<\n")
                            newly_achieved_this_turn = True
                            self.newly_leveled_target_this_turn = True
                        elif cls == "SIDE":
                            self.side_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [SIDE SKILL] {skill} -> LV {new_lv} [{cls}] (excluded from curriculum) <<<\n")
                        else:
                            self.side_skills[skill] = f"LV {new_lv}"
                            print(f"\n>>> [UNKNOWN SKILL] {skill} -> LV {new_lv} [{cls}] (excluded from curriculum) <<<\n")

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

            consecutive_loadings = 0

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
                
                # Check for wrap-up completion
                if self._is_oboe_indicating_completion(messages, start_time):
                    print("[WRAP-UP DETECTED] Oboe indicated completion with corroborating signals.")
                    print("[WRAP-UP] Forcing redirect to next target or track topic.")
                    if self.pin:
                        achieved_lv = 0
                        if self.topic:
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
                                    if "anchors" in traversal_state and active_track in traversal_state["anchors"]:
                                        active_node = traversal_state["anchors"][active_track].get("current_node")
                                    else:
                                        active_node = traversal_state.get("current_node")
                                    if active_node:
                                        from curriculum.mastery_evidence import MasteryEvidenceManager
                                        # Record transition-level success to force node status updates
                                        MasteryEvidenceManager.record_turn_evidence(active_node, "", correct_assessment=True)
                                
                                resolver = DepthFirstResolver(self.pin)
                                resolved = resolver.resolve_next_node()
                                print(f"[DFS] Transitioned to next node target: '{resolved['topic_name']}'")
                            except Exception as e:
                                print(f"[DFS_FALLBACK] Error transitioning DFS: {e}")
                                resolved = None

                        if not resolved:
                            SkillDAGEngine.mark_topic_covered(self.pin, self.active_track_topic_index, achieved_lv)
                            resolved = SkillDAGEngine.resolve_next_track_topic(self.pin)

                        self.active_track_topic_index = resolved["topic_index"]
                        self.topic = resolved["topic_name"]
                        self.active_track_target_skills = resolved.get("target_skills", [])
                        track_prompt = resolved["prompt"]
                        print(f"[WRAP-UP] Advancing track to topic #{self.active_track_topic_index}: '{self.topic}'")
                        self.steering_controller.request_redirect(reason="track topic completion transition")
                        text = track_prompt
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
                            print(f"[WRAP-UP] Advancing DAG to node '{self.active_node}': '{self.topic}'")
                            self.steering_controller.request_redirect(reason="DAG node completion transition")
                            text = f"I want to learn about {self.topic}."
                else:
                    # Evaluate steering override
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

    def _finalize_session(self, start_time, state_path, pid_path):

        """Cleanup: close browser, save skills, update DAG, write final state."""
        elapsed_time = time.time() - start_time
        rolling_24h_sec, today_ist_sec = update_time_tracker(elapsed_time, self.topic)
        # Final observation of page to capture any last-second skill badges/level-ups
        try:
            final_obs = self.browser.observe_page()
            if final_obs.get("skills"):
                for skill, lv_str in final_obs["skills"].items():
                    try:
                        new_lv = int(lv_str.replace("LV", "").strip())
                    except ValueError:
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
            # Find the highest achieved level across all skills this session
            max_achieved = max(self.achieved_skills.values()) if self.achieved_skills else 0
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
