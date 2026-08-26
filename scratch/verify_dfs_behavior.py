import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import time
from curriculum.depth_first_resolver import DepthFirstResolver, STATE_FILE, TREE_FILE
from curriculum.mastery_evidence import MasteryEvidenceManager

def run_behavior_tests():
    print("==================================================")
    print("     DFS BEHAVIORAL VERIFICATION TEST SUITE       ")
    print("==================================================")

    # Backup files
    state_backup = STATE_FILE.read_text() if STATE_FILE.exists() else None
    tree_backup = TREE_FILE.read_text() if TREE_FILE.exists() else None

    try:
        # TEST 1: 3-Level Forced DFS
        print("\n--- TEST 1: 3-Level Forced DFS ---")
        if STATE_FILE.exists(): STATE_FILE.unlink()
        if TREE_FILE.exists(): TREE_FILE.unlink()

        # Seed synthetic 5-level deep tree
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
                    "children": ["maths.algebra.linear"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.linear": {
                    "id": "maths.algebra.linear",
                    "name": "Linear Equations",
                    "parent": "maths.algebra",
                    "children": ["maths.algebra.linear.graphing"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.linear.graphing": {
                    "id": "maths.algebra.linear.graphing",
                    "name": "Graphing Linear Equations",
                    "parent": "maths.algebra.linear",
                    "children": ["maths.algebra.linear.graphing.slope"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.linear.graphing.slope": {
                    "id": "maths.algebra.linear.graphing.slope",
                    "name": "Slope Intercepts",
                    "parent": "maths.algebra.linear.graphing",
                    "children": [],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_mock, indent=4))

        resolver = DepthFirstResolver("maths")
        sequence = []
        
        # Resolve next step 4 times to traverse down the line
        for i in range(4):
            resolved = resolver.resolve_next_node()
            sequence.append(resolved["topic_name"])

        expected = [
            "Algebra",
            "Linear Equations",
            "Graphing Linear Equations",
            "Slope Intercepts"
        ]
        print(f"Traversed Sequence: {sequence}")
        assert sequence == expected, f"Failed: Expected {expected}, got {sequence}"
        print("TEST 1 PASSED: Strict 3-level depth path validated (no lateral jumping!).")


        # TEST 2: Stop / Restart Trajectory Persistence
        print("\n--- TEST 2: Stop / Restart Trajectory Persistence ---")
        # Simulator stops here. We instantiate a brand new resolver.
        # It should read the persisted state (active branch: ['maths', 'maths.algebra', 'maths.algebra.linear', ...])
        # and current_node: 'maths.algebra.linear.graphing.slope'
        resolver_restarted = DepthFirstResolver("maths")
        self_state = resolver_restarted.state
        print(f"Restored current node: {self_state['current_node']}")
        print(f"Restored active branch: {self_state['active_branch']}")
        assert self_state["current_node"] == "maths.algebra.linear.graphing.slope", "Failed: current_node was reset!"
        assert self_state["active_branch"] == ["maths", "maths.algebra", "maths.algebra.linear", "maths.algebra.linear.graphing", "maths.algebra.linear.graphing.slope"], "Failed: active branch path was reset!"
        print("TEST 2 PASSED: Path restored perfectly. restarting doesn't destroy depth trajectory.")


        # TEST 3: Branch Exhaustion and Backtracking
        print("\n--- TEST 3: Branch Exhaustion and Backtracking ---")
        if STATE_FILE.exists(): STATE_FILE.unlink()
        if TREE_FILE.exists(): TREE_FILE.unlink()

        # Seed branching tree:
        # maths -> maths.algebra, maths.geometry
        # maths.algebra -> maths.algebra.linear, maths.algebra.quadratic
        # maths.geometry -> maths.geometry.shapes
        tree_branching = {
            "anchors": {
                "maths": {
                    "id": "maths",
                    "name": "Mathematics",
                    "children": ["maths.algebra", "maths.geometry"],
                    "mastery_level": 1,
                    "evidence": {}
                }
            },
            "nodes": {
                "maths.algebra": {
                    "id": "maths.algebra",
                    "name": "Algebra",
                    "parent": "maths",
                    "children": ["maths.algebra.linear", "maths.algebra.quadratic"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.linear": {
                    "id": "maths.algebra.linear",
                    "name": "Linear",
                    "parent": "maths.algebra",
                    "children": [],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.quadratic": {
                    "id": "maths.algebra.quadratic",
                    "name": "Quadratic",
                    "parent": "maths.algebra",
                    "children": [],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.geometry": {
                    "id": "maths.geometry",
                    "name": "Geometry",
                    "parent": "maths",
                    "children": ["maths.geometry.shapes"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.geometry.shapes": {
                    "id": "maths.geometry.shapes",
                    "name": "Shapes",
                    "parent": "maths.geometry",
                    "children": [],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_branching, indent=4))

        resolver = DepthFirstResolver("maths")
        resolver._discover_dynamic_children = lambda parent_id: []
        
        # 1. First resolution should descend to Algebra
        res1 = resolver.resolve_next_node()
        assert res1["topic_name"] == "Algebra"
        
        # 2. Descend to Linear
        res2 = resolver.resolve_next_node()
        assert res2["topic_name"] == "Linear"
        
        # Now Linear has no children. It becomes exhausted.
        # Next resolution should backtrack to Algebra and select sibling Quadratic
        print("[TEST 3] Simulating Linear exhaustion...")
        res3 = resolver.resolve_next_node()
        assert res3["topic_name"] == "Quadratic", f"Expected Quadratic, got {res3['topic_name']}"

        # Now Quadratic has no children. It becomes exhausted.
        # Next resolution should backtrack to Algebra (exhausted) -> backtrack to maths -> descend to sibling Geometry
        print("[TEST 3] Simulating Quadratic exhaustion...")
        res4 = resolver.resolve_next_node()
        assert res4["topic_name"] == "Geometry", f"Expected Geometry, got {res4['topic_name']}"

        # Descend to Shapes
        res5 = resolver.resolve_next_node()
        assert res5["topic_name"] == "Shapes"

        print("TEST 3 PASSED: Sibling backtracking & parent traversal resolved perfectly.")


        # TEST 4: Topic Covered but Child Unresolved
        print("\n--- TEST 4: Topic Covered but Child Unresolved ---")
        if STATE_FILE.exists(): STATE_FILE.unlink()
        if TREE_FILE.exists(): TREE_FILE.unlink()

        tree_unresolved = {
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
                    "children": ["maths.algebra.linear"],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                },
                "maths.algebra.linear": {
                    "id": "maths.algebra.linear",
                    "name": "Linear",
                    "parent": "maths.algebra",
                    "children": [],
                    "mastery_level": 1,
                    "status": "AVAILABLE"
                }
            }
        }
        TREE_FILE.write_text(json.dumps(tree_unresolved, indent=4))

        resolver = DepthFirstResolver("maths")
        resolver._discover_dynamic_children = lambda parent_id: []
        
        # Start maths -> Algebra
        resolver.resolve_next_node()
        assert resolver.state["current_node"] == "maths.algebra"

        # Now simulate Oboe indicating completion (wrap-up triggers transition).
        # We record completion/success on "Algebra" but "Linear" is still unresolved.
        # The resolver MUST NOT jump horizontally to a different track topic; it must stay on maths.algebra and descend to Linear
        # Simulate topic marked MASTERED
        tree_state = json.loads(TREE_FILE.read_text())
        tree_state["nodes"]["maths.algebra"]["status"] = "MASTERED"
        TREE_FILE.write_text(json.dumps(tree_state, indent=4))
        
        # Verify node Algebra was marked MASTERED
        tree_state = json.loads(TREE_FILE.read_text())
        assert tree_state["nodes"]["maths.algebra"]["status"] == "MASTERED"

        # Resolve next step
        res_next = resolver.resolve_next_node()
        assert res_next["topic_name"] == "Linear", f"Expected Linear, got {res_next['topic_name']}"
        print("TEST 4 PASSED: Stay-on-branch (non-premature horizontal advancement) validated.")

        print("\n==================================================")
        print("     ALL BEHAVIORAL VERIFICATION TESTS PASSED!    ")
        print("==================================================")

    finally:
        # Restore backups
        if state_backup:
            STATE_FILE.write_text(state_backup)
        elif STATE_FILE.exists():
            STATE_FILE.unlink()

        if tree_backup:
            TREE_FILE.write_text(tree_backup)
        elif TREE_FILE.exists():
            TREE_FILE.unlink()

if __name__ == "__main__":
    run_behavior_tests()
