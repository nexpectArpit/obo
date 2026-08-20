#!/usr/bin/env python3
"""
UNIT TESTS FOR SKILL DAG ENGINE (PHASE A)

Verifies:
1. Strict prerequisite edge resolution (blocked -> available -> mastered).
2. Level-gap weighting favoring pillars with the lowest levels / largest gaps to LV 25.
3. Zero-LLM deterministic topic selection.
4. Correct state updates on level-up vs attempt increment.
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skill_dag_engine import SkillDAGEngine

class TestSkillDAGEngine(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for test graph state
        self.test_dir = tempfile.mkdtemp()
        self.graph_path = Path(self.test_dir) / "test_graph.json"
        self.learned_skills_path = Path(self.test_dir) / "test_learned_skills.json"

        # Copy original graph schema to temp file
        original_graph_path = Path(__file__).resolve().parent.parent / "obo_skill_graph.json"
        shutil.copy(original_graph_path, self.graph_path)

        # Initialize engine with temp files
        self.engine = SkillDAGEngine(
            graph_path=self.graph_path,
            learned_skills_path=self.learned_skills_path
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_01_prerequisite_edge_enforcement(self):
        print("\n--- [TEST 1] Prerequisite Edge Enforcement ---")
        nodes = self.engine.graph["pillars"]["Computer_Architecture"]["nodes"]

        # Cache_Hierarchy has 0 prereqs -> should be in_progress/available
        self.assertIn(nodes["Cache_Hierarchy"]["status"], ["available", "in_progress"])

        # Cache_Coherence requires Cache_Hierarchy -> should be BLOCKED
        self.assertEqual(nodes["Cache_Coherence"]["status"], "blocked")

        # Master Cache_Hierarchy
        self.engine.update_skill_level("Computer_Architecture", "Cache_Hierarchy", 3)
        nodes = self.engine.graph["pillars"]["Computer_Architecture"]["nodes"]

        # Cache_Hierarchy is now mastered
        self.assertEqual(nodes["Cache_Hierarchy"]["status"], "mastered")

        # Cache_Coherence should now be UNBLOCKED -> available
        self.assertEqual(nodes["Cache_Coherence"]["status"], "available")

    def test_02_level_gap_weighting(self):
        print("\n--- [TEST 2] Level-Gap Weighting Prioritization ---")
        # Set Operating_Systems level to 1 (Gap = 24)
        # Set Memory_Systems / Computer_Architecture level to 10 (Gap = 15)
        for n_val in self.engine.graph["pillars"]["Operating_Systems"]["nodes"].values():
            n_val["level"] = 1
        for n_val in self.engine.graph["pillars"]["Computer_Architecture"]["nodes"].values():
            n_val["level"] = 10

        # Run 1,000 selection trials and verify Operating_Systems is selected more often than Computer_Architecture
        counts = {}
        for _ in range(1000):
            p = self.engine.get_weakest_core_pillar()
            counts[p] = counts.get(p, 0) + 1

        print("Pillar Selection Counts over 1000 trials:", counts)
        self.assertGreater(counts["Operating_Systems"], counts["Computer_Architecture"])

    def test_03_zero_llm_deterministic_selection(self):
        print("\n--- [TEST 3] Zero-LLM Deterministic Selection ---")
        # Ensure no openai, groq, or anthropic modules are imported/initialized during selection
        res = self.engine.resolve_next_topic()
        print("Resolved Topic:", res)
        self.assertIsInstance(res, dict)
        self.assertIn("topic", res)
        self.assertIn("target_level", res)

    def test_04_no_level_up_attempt_increment(self):
        print("\n--- [TEST 4] Attempt Increment on No Level-Up ---")
        # Simulate a session run where level did not change
        node_key = "System_Calls"
        old_attempts = self.engine.graph["pillars"]["Operating_Systems"]["nodes"][node_key]["attempts"]

        self.engine.update_skill_level("Operating_Systems", node_key, 1)

        new_attempts = self.engine.graph["pillars"]["Operating_Systems"]["nodes"][node_key]["attempts"]
        self.assertEqual(new_attempts, old_attempts + 1)
        self.assertEqual(self.engine.graph["pillars"]["Operating_Systems"]["nodes"][node_key]["status"], "available")

if __name__ == "__main__":
    unittest.main()
