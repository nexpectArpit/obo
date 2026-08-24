import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import json
import time
from unittest.mock import patch, MagicMock
from curriculum.depth_first_resolver import DepthFirstResolver, STATE_FILE, TREE_FILE
from curriculum.mastery_evidence import MasteryEvidenceManager

class TestDepthFirstResolver(unittest.TestCase):
    def setUp(self):
        # Backup original state/tree if they exist
        self.state_backup = STATE_FILE.read_text() if STATE_FILE.exists() else None
        self.tree_backup = TREE_FILE.read_text() if TREE_FILE.exists() else None
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        if TREE_FILE.exists():
            TREE_FILE.unlink()

    def tearDown(self):
        # Restore backups
        if self.state_backup:
            STATE_FILE.write_text(self.state_backup)
        elif STATE_FILE.exists():
            STATE_FILE.unlink()

        if self.tree_backup:
            TREE_FILE.write_text(self.tree_backup)
        elif TREE_FILE.exists():
            TREE_FILE.unlink()

    def test_anchor_initialization(self):
        resolver = DepthFirstResolver("maths")
        self.assertEqual(resolver.state["active_anchor"], "maths")
        self.assertEqual(resolver.active_state["current_node"], "maths")
        self.assertEqual(resolver.active_state["active_branch"], ["maths"])

    def test_dfs_descent_path(self):
        # Seed a dummy child hierarchy
        tree_mock = {
            "anchors": {
                "maths": {
                    "id": "maths",
                    "name": "Mathematics",
                    "children": ["maths.algebra"],
                    "mastery_level": 1,
                    "evidence": {}
                }
            },
            "nodes": {
                "maths.algebra": {
                    "id": "maths.algebra",
                    "name": "Algebra",
                    "parent": "maths",
                    "children": [],
                    "mastery_level": 1,
                    "evidence": {},
                    "status": "AVAILABLE"
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_mock, indent=4))

        resolver = DepthFirstResolver("maths")
        # Run resolution step which should descend to maths.algebra
        resolved = resolver.resolve_next_node()
        self.assertEqual(resolved["topic_name"], "Algebra")
        self.assertEqual(resolver.active_state["current_node"], "maths.algebra")

    def test_dynamic_child_discovery_validation(self):
        tree_mock = {
            "anchors": {
                "maths": {
                    "id": "maths",
                    "name": "Mathematics",
                    "children": [],
                    "mastery_level": 1,
                    "evidence": {}
                }
            },
            "nodes": {}
        }
        TREE_FILE.write_text(json.dumps(tree_mock, indent=4))

        resolver = DepthFirstResolver("maths")

        # Mock LLM query response containing 3 child proposals:
        # 1 valid, 1 duplicate/already existing name, 1 invalid stats skill
        mock_proposals = '["Linear Algebra", "Abstract Algebra", "Hypothesis Testing"]'
        
        # Seed duplicate name internally in existing nodes
        resolver.tree["nodes"]["maths.dup"] = {
            "id": "maths.dup",
            "name": "Linear Algebra",
            "parent": "maths"
        }

        with patch("curriculum.depth_first_resolver.DepthFirstResolver._query_llm", return_value=mock_proposals):
            discovered = resolver._discover_dynamic_children("maths")
            
            # Hypothesis Testing is a math reject (SIDE skill) -> rejected
            # Linear Algebra name duplicate -> rejected
            # Abstract Algebra -> Valid, committed
            self.assertEqual(len(discovered), 1)
            self.assertIn("maths.abstract_algebra", resolver.tree["nodes"])
            self.assertNotIn("maths.hypothesis_testing", resolver.tree["nodes"])

    def test_stall_recovery_and_anti_oscillation(self):
        # Seed test node structures
        tree_mock = {
            "anchors": {
                "maths": {
                    "id": "maths",
                    "name": "Mathematics",
                    "children": ["maths.algebra"],
                    "mastery_level": 1,
                    "evidence": {}
                }
            },
            "nodes": {
                "maths.algebra": {
                    "id": "maths.algebra",
                    "name": "Algebra",
                    "parent": "maths",
                    "children": [],
                    "mastery_level": 1,
                    "evidence": {},
                    "status": "AVAILABLE"
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_mock, indent=4))

        resolver = DepthFirstResolver("maths")
        resolver.active_state["current_node"] = "maths.algebra"
        resolver.active_state["active_branch"] = ["maths", "maths.algebra"]
        resolver.active_state["consecutive_stalls"] = 4 # Exceeds recovery threshold
        resolver._save_state()

        # Triggering resolution should execute stall recovery, reverting current_node to anchor
        resolver.resolve_next_node()
        self.assertEqual(resolver.active_state["consecutive_stalls"], 0)
        self.assertEqual(resolver.active_state["current_node"], "maths.algebra") # descends back down to available child

    def test_mastery_bands_parent_aggregation(self):
        tree_mock = {
            "anchors": {
                "maths": {
                    "id": "maths",
                    "name": "Mathematics",
                    "children": ["maths.algebra", "maths.optimization", "maths.geometry"],
                    "mastery_level": 1,
                    "evidence": {}
                }
            },
            "nodes": {
                "maths.algebra": {
                    "id": "maths.algebra",
                    "name": "Algebra",
                    "parent": "maths",
                    "mastery_level": 35
                },
                "maths.optimization": {
                    "id": "maths.optimization",
                    "name": "Optimization",
                    "parent": "maths",
                    "mastery_level": 15
                },
                "maths.geometry": {
                    "id": "maths.geometry",
                    "name": "Geometry",
                    "parent": "maths",
                    "mastery_level": 15
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_mock, indent=4))

        # Under Mastery Band LV 21-50 rule:
        # 1 branch >= 35, 2 branches >= 15 -> should aggregate parent level to 40
        level = MasteryEvidenceManager.get_parent_mastery_level("maths")
        self.assertEqual(level, 40)

if __name__ == "__main__":
    unittest.main()
