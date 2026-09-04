import re

class OboeStatsTracker:
    def __init__(self):
        self.total_mcqs_count = 0
        self.wrong_mcqs_count = 0
        self.last_action_was_mcq = False
        self.last_action_was_q_answer = False
        self.target_skill_leveled_up_this_turn = False
        self.consecutive_mcqs_without_target_growth = 0
        self.mcq_drift_detected = False

    def evaluate_turn_outcome(self, messages):
        """Scans assistant messages for indicators of correctness."""
        if not messages:
            return

        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        if not assistant_msgs:
            return

        oboe_reply = assistant_msgs[-1]["text"].lower()
        # Cleaned up wrong indicators (removed 'different' and 'consequence of')
        wrong_indicators = ["actually", "incorrect", "wrong", "snag", "correct answer is", "close, but", "not quite"]
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

    def evaluate_consecutive_mcq_drift(self):
        """Tracks consecutive MCQ turns without target skill growth."""
        if self.last_action_was_mcq:
            if self.target_skill_leveled_up_this_turn:
                self.consecutive_mcqs_without_target_growth = 0
            else:
                self.consecutive_mcqs_without_target_growth += 1
                print(f"[DRIFT MONITOR] Consecutive MCQs without target growth: {self.consecutive_mcqs_without_target_growth}")
                if self.consecutive_mcqs_without_target_growth >= 2:
                    print(f"[DRIFT MONITOR] Threshold reached ({self.consecutive_mcqs_without_target_growth}>=2). Flagging drift redirect.")
                    self.mcq_drift_detected = True
            
            # Reset the level-up flag for next turn
            self.target_skill_leveled_up_this_turn = False
