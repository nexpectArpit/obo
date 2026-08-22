import unittest
import json
import os
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curriculum.dag_engine import SkillDAGEngine, TRACK_FILES

class TestTrackCurriculum(unittest.TestCase):
    def setUp(self):
        self.engine = SkillDAGEngine()

    def test_track_files_exist(self):
        """Verify all 6 track files are present and contain valid JSON."""
        for name, filename in TRACK_FILES.items():
            path = Path(__file__).resolve().parent.parent / "tracks" / filename
            self.assertTrue(path.exists(), f"Track file {filename} does not exist")
            
            with open(path, "r") as f:
                data = json.load(f)
                self.assertIn("track_name", data)
                self.assertEqual(data["track_name"], name)
                self.assertIn("pinned_chat_title", data)
                self.assertIn("topics", data)
                self.assertGreater(len(data["topics"]), 10, f"Track {name} should have a substantial number of topics")
                
                # Check structure of topics
                for topic in data["topics"]:
                    self.assertIn("name", topic)
                    self.assertIn("prompt", topic)
                    self.assertIn("covered", topic)
                    self.assertIn("level_at_cover", topic)

    def test_resolve_next_track_topic(self):
        """Verify resolving next uncovered topic returns the first uncovered one."""
        # Using 'cpp' track as example
        track_name = "cpp"
        resolved = SkillDAGEngine.resolve_next_track_topic(track_name)
        
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["track_name"], track_name)
        self.assertIn("pinned_chat_title", resolved)
        self.assertIn("topic_index", resolved)
        self.assertIn("topic_name", resolved)
        self.assertIn("prompt", resolved)

    def test_mark_topic_covered(self):
        """Verify marking a topic as covered updates the state correctly."""
        track_name = "cpp"
        # Load current state
        data_before = SkillDAGEngine.load_track(track_name)
        topics_before = data_before["topics"]
        
        # Find first uncovered index
        target_idx = None
        for idx, t in enumerate(topics_before):
            if not t.get("covered", False):
                target_idx = idx
                break
                
        if target_idx is not None:
            SkillDAGEngine.mark_topic_covered(track_name, target_idx, achieved_level=5)
            
            # Reload and check
            data_after = SkillDAGEngine.load_track(track_name)
            self.assertTrue(data_after["topics"][target_idx]["covered"])
            self.assertEqual(data_after["topics"][target_idx]["level_at_cover"], 5)
            
            # Revert to keep clean state
            data_after["topics"][target_idx]["covered"] = False
            data_after["topics"][target_idx]["level_at_cover"] = 0
            SkillDAGEngine.save_track(track_name, data_after)

    def test_get_all_tracks_progress(self):
        """Verify progress reporting returns stats for all 6 tracks."""
        progress = SkillDAGEngine.get_all_tracks_progress()
        self.assertEqual(len(progress), 6)
        for name in TRACK_FILES:
            self.assertIn(name, progress)
            self.assertIn("total", progress[name])
            self.assertIn("covered", progress[name])
            self.assertIn("remaining", progress[name])
            self.assertIn("percent", progress[name])

if __name__ == "__main__":
    unittest.main()
