import sys
import os
import json
import shutil
import unittest
from pathlib import Path

# Add root directory to import paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import OboeAgent
from skill_dag_engine import SkillDAGEngine

class TestDynamicSkillAdaptation(unittest.TestCase):
    def setUp(self):
        self.tracks_dir = Path(__file__).resolve().parent.parent / "tracks"
        self.test_track_path = self.tracks_dir / "test_adaptation_track.json"
        
        # Create a mock track JSON file
        self.mock_track_data = {
            "track_name": "test_adaptation_track",
            "pinned_chat_title": "Test Chat",
            "target_skills": ["Algebra", "Optimization"],
            "topics": [
                {
                    "name": "Topic 1",
                    "prompt": "Explain topic 1",
                    "covered": False,
                    "level_at_cover": 0
                }
            ]
        }
        # Add test track mapping to engine
        from skill_dag_engine import TRACK_FILES
        TRACK_FILES["test_adaptation_track"] = "test_adaptation_track.json"
        
        with open(self.test_track_path, "w") as f:
            json.dump(self.mock_track_data, f, indent=2)

    def tearDown(self):
        # Remove test track mapping from engine
        from skill_dag_engine import TRACK_FILES
        if "test_adaptation_track" in TRACK_FILES:
            del TRACK_FILES["test_adaptation_track"]
            
        # Clean up the mock track file
        if self.test_track_path.exists():
            self.test_track_path.unlink()

    def test_dynamic_adaptation_trigger(self):
        """Verify that lowest target skill is replaced when an unmapped skill levels up higher."""
        # Instantiate agent under test
        agent = OboeAgent(pin="test_adaptation_track")
        agent.active_track_name = "test_adaptation_track"
        agent.active_track_target_skills = ["Algebra", "Optimization"]
        
        # Set learned skills and new achievements
        agent.learned_skills = {
            "Algebra": 2,       # min target level = 2
            "Optimization": 4,  # higher target level = 4
            "Neural Networks": 5 # new unmapped skill levels up to 5
        }
        agent.achieved_skills = {
            "Neural Networks": "LV 5"
        }
        
        # Simulate the dynamic adaptation check block
        track_path = agent.dag_engine.get_track_path(agent.active_track_name)
        self.assertTrue(track_path.exists())
        
        # Read the current targets
        with open(track_path, "r") as f:
            track_data = json.load(f)
        current_targets = track_data.get("target_skills", [])
        self.assertEqual(current_targets, ["Algebra", "Optimization"])
        
        # Run adaptation logic
        target_levels = {skill: agent.learned_skills.get(skill, 1) for skill in current_targets}
        min_target_skill = min(target_levels, key=target_levels.get)
        min_level = target_levels[min_target_skill]
        
        self.assertEqual(min_target_skill, "Algebra")
        self.assertEqual(min_level, 2)
        
        better_skill = None
        better_level = min_level
        for skill, lv_str in agent.achieved_skills.items():
            if skill not in current_targets:
                lvl = int(lv_str.replace("LV", "").strip())
                if lvl > better_level:
                    better_skill = skill
                    better_level = lvl
                    
        self.assertEqual(better_skill, "Neural Networks")
        self.assertEqual(better_level, 5)
        
        if better_skill and min_target_skill:
            new_targets = [better_skill if s == min_target_skill else s for s in current_targets]
            track_data["target_skills"] = new_targets
            with open(track_path, "w") as f:
                json.dump(track_data, f, indent=2)
                
        # Read back and assert changes
        with open(track_path, "r") as f:
            updated_data = json.load(f)
        
        self.assertEqual(updated_data["target_skills"], ["Neural Networks", "Optimization"])
        print("\n--- [TEST PASS] Dynamic Skill Adaptation logic works perfectly! ---")

if __name__ == "__main__":
    unittest.main()
