# agent/steering_controller.py
from agent.curriculum_policy import get_domain_keywords

class SteeringController:
    def __init__(self, track_name: str, target_skills: list[str], dag_engine=None):
        self.track_name = track_name
        self.target_skills = target_skills
        self.dag_engine = dag_engine
        self.alignment_history = []
        self.turns_without_target_skill = 0
        self.turns_since_last_steering = 0
        self.turns_since_last_escalation = 0
        self.recent_target_gain = False
        
        # Explicit forced state triggers
        self.forced_mode = None
        self.forced_reason = None

    def request_redirect(self, reason: str = "forced"):
        """Explicitly request a redirection on the next turn."""
        self.forced_mode = "redirect"
        self.forced_reason = reason

    def update(self, messages: list, newly_leveled_target: bool):
        """Call once per turn before evaluating steering."""
        # Clean messages history to a text block
        recent_text = " ".join(m["text"].lower() for m in messages[-5:])
        score = self._compute_alignment_score(recent_text)
        self.alignment_history.append(score)
        if len(self.alignment_history) > 10:
            self.alignment_history.pop(0)

        if newly_leveled_target:
            self.turns_without_target_skill = 0
            self.recent_target_gain = True
        else:
            self.turns_without_target_skill += 1
            self.recent_target_gain = False

        self.turns_since_last_steering += 1
        self.turns_since_last_escalation += 1

    @property
    def consecutive_low_alignment(self) -> int:
        count = 0
        for score in reversed(self.alignment_history):
            if score < 0.05:
                count += 1
            else:
                break
        return count

    def _compute_alignment_score(self, recent_text: str) -> float:
        """
        Compute target alignment score between 0.0 and 1.0 based on proportion
        of domain-specific keywords found in the text.
        """
        direct_kws = get_domain_keywords(self.track_name, tier="direct")
        close_kws = get_domain_keywords(self.track_name, tier="close")

        if not direct_kws and not close_kws:
            return 1.0

        direct_hits = sum(1 for kw in direct_kws if kw in recent_text)
        close_hits = sum(1 for kw in close_kws if kw in recent_text)

        # Direct keywords weighted 2x vs close keywords
        total_possible = len(direct_kws) * 2 + len(close_kws)
        score = (direct_hits * 2 + close_hits) / max(1, total_possible)
        return min(score, 1.0)

    def _is_progress_stalled(self) -> bool:
        """
        Composite stall detection. Progress is stalled only if all conditions met:
        1. No target/supporting skill leveled up for 10+ turns
        2. Score below threshold for last 5 turns
        3. No recent steering in last 8 turns (avoid redundancy)
        """
        return (
            self.turns_without_target_skill >= 10 and
            self.consecutive_low_alignment >= 5 and
            self.turns_since_last_steering >= 8
        )

    def evaluate(self) -> dict | None:
        """
        Evaluate current state and return override response dict if steering is needed.
        """
        # Step 1: Forced triggers
        if self.forced_mode:
            mode = self.forced_mode
            reason = self.forced_reason or "forced trigger"
            self.forced_mode = None
            self.forced_reason = None
            return self._emit(mode, reason)

        # Step 2: Severe domain drift check
        if self.consecutive_low_alignment >= 5:
            return self._emit("redirect", f"{self.consecutive_low_alignment} consecutive turns below alignment threshold")

        # Step 3: Target stall check
        if self._is_progress_stalled():
            return self._emit("assess", "stall detected: no progress + low alignment + no recent steering")

        # Step 4: Occasional escalation upon target gain
        if (self.recent_target_gain and 
                self.turns_since_last_escalation >= 6 and 
                self.turns_since_last_steering >= 4):
            return self._emit("escalate", "recent target level-up + escalation interval met")

        return None

    def force_redirect(self) -> str:
        """Get redirect prompt text directly when choice filtering has zero valid choices."""
        self.turns_since_last_steering = 0
        primary = self.target_skills[0] if self.target_skills else "the core topic"
        return f"actually, let's bring this back to {primary}. how does this connect? can you challenge me with a tough problem specifically on {primary}?"

    def _emit(self, mode: str, reason: str) -> dict:
        self.turns_since_last_steering = 0
        if mode == "escalate":
            self.turns_since_last_escalation = 0

        primary = self.target_skills[0] if self.target_skills else "the core topic"
        
        # When constructing steering prompts, we want it to be target-aware
        templates = {
            "redirect":  f"actually, let's bring this back to {primary}. how does this connect? can you challenge me with a tough problem specifically on {primary}?",
            "assess":    f"can you test me directly on {primary}? give me a difficult problem with an edge case I have to compute through.",
            "escalate":  f"got it — what's the next advanced concept within {primary} from here? can you challenge me with a non-trivial example?",
        }
        text = templates[mode]

        # Structured [STEERING] log
        print(f"\n[STEERING]")
        print(f"Track: {self.track_name} | Target: {primary}")
        print(f"Trigger Reason: {reason}")
        print(f"Mode: {mode.upper()}")
        print(f"Steering Response: '{text}'\n")

        return {
            "mode": mode,
            "text": text
        }
