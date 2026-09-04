import unittest
import json
from pathlib import Path
from agent.skill_adapter import adapt_track_target_skills

class TestSkillExtractionAndSteering(unittest.TestCase):

    def test_c_track_domain_filtering(self):
        """Verify that only skills matching the active track domain are selected for target focus."""
        learned_skills = {
            "System Calls": 10,       # High OS skill (should NOT be picked for DL)
            "Virtual Memory": 8,      # High OS skill (should NOT be picked for DL)
            "Machine Learning": 6,    # DL relevant
            "Neural Networks": 5,     # DL relevant
            "Gradient Descent": 2,    # DL relevant
            "Dynamic Programming": 9  # High CP/DSA skill (should NOT be picked for DL)
        }

        # Mock track file path
        test_track_path = Path(__file__).resolve().parent / "mock_dl_track.json"
        test_track_path.write_text(json.dumps({
            "track_name": "dl",
            "target_skills": ["Deep Learning", "Neural Networks"]
        }, indent=2))

        def mock_get_track_path(track_name):
            return test_track_path

        try:
            adapt_track_target_skills(
                active_track_name="dl",
                current_targets=["Deep Learning", "Neural Networks"],
                learned_skills=learned_skills,
                achieved_skills={"Gradient Descent": "LV 2"},
                get_track_path_fn=mock_get_track_path
            )

            with open(test_track_path) as f:
                data = json.load(f)

            targets = data.get("target_skills", [])
            print(f"\n[TEST C RESULT] Selected Target Skills for DL Track: {targets}")
            
            # Must pick Neural Networks (LV 5) and Gradient Descent (LV 2)
            self.assertEqual(targets, ["Neural Networks", "Gradient Descent"])
            # Must NOT pick System Calls or Dynamic Programming despite higher levels
            self.assertNotIn("System Calls", targets)
            self.assertNotIn("Dynamic Programming", targets)
        finally:
            if test_track_path.exists():
                test_track_path.unlink()

    def test_b_notification_payload_formatting(self):
        """Verify that last_session payload translates into accurate duration, stats, and skills."""
        s = {
            "status": "COMPLETED",
            "last_session": {
                "topic": "Loss Functions in Deep Learning",
                "elapsed_seconds": 245,
                "today_ist_hours": 1,
                "today_ist_minutes": 15,
                "mcqs_total": 2,
                "mcqs_correct": 2,
                "mcqs_wrong": 0,
                "achieved_skills": {
                    "Gradient Descent": "LV 1",
                    "Stochastic Gradient Descent": "LV 1"
                },
                "telemetry": {
                    "total_api_calls": 2,
                    "total_tokens": 5800,
                    "providers": {"groq": {"calls": 2, "tokens": 5800}}
                }
            }
        }

        last_s = s.get("last_session", s)
        elapsed = last_s.get("elapsed_seconds", 0)
        mins, secs = elapsed // 60, elapsed % 60
        today_h = last_s.get("today_ist_hours", 0)
        today_m = last_s.get("today_ist_minutes", 0)
        skills = last_s.get("achieved_skills", {})

        self.assertEqual(f"{mins}m {secs}s", "4m 5s")
        self.assertEqual(f"{today_h}h {today_m}m", "1h 15m")
        self.assertIn("Gradient Descent", skills)
        self.assertIn("Stochastic Gradient Descent", skills)
        self.assertEqual(skills["Gradient Descent"], "LV 1")

if __name__ == "__main__":
    unittest.main()
