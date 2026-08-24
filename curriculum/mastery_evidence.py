import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TREE_FILE = DATA_DIR / "skill_tree.json"

class MasteryEvidenceManager:
    @staticmethod
    def record_turn_evidence(node_id: str, message_text: str, correct_assessment: bool = False, duplicated_content: bool = False):
        """
        Updates the local node mastery evidence and checks for branch saturation.
        """
        if not TREE_FILE.exists():
            return

        try:
            tree = json.loads(TREE_FILE.read_text())
            nodes = tree.get("nodes", {})
            
            # Find the active node
            node = nodes.get(node_id)
            if not node:
                # If it's a root anchor node, update its anchor metadata
                anchors = tree.get("anchors", {})
                node = anchors.get(node_id)
                if not node:
                    return

            evidence = node.get("evidence", {})
            evidence["concepts_covered"] = evidence.get("concepts_covered", 0) + 1

            if correct_assessment:
                evidence["successful_assessments"] = evidence.get("successful_assessments", 0) + 1

            if duplicated_content:
                evidence["recent_repetition"] = evidence.get("recent_repetition", 0) + 1

            # Update unique concepts count
            unique_concepts = set(evidence.get("unique_concepts_list", []))
            # Scan text for unique technical words (simple split)
            words = [w.strip(".,?!()").lower() for w in message_text.split() if len(w) > 4]
            # Keep top nouns/technical descriptors
            technical_descriptors = [w for w in words if any(c in w for c in ["tensor", "grad", "back", "algo", "comput", "layer", "optim", "memory", "cuda", "thread"])]
            for desc in technical_descriptors:
                unique_concepts.add(desc)
            evidence["unique_concepts_list"] = list(unique_concepts)
            evidence["unique_concepts_count"] = len(unique_concepts)

            node["evidence"] = evidence
            
            # Check for structural mastery
            # If they completed at least 5 assessments successfully, level up the child node!
            if evidence.get("successful_assessments", 0) >= 5:
                node["mastery_level"] = max(node.get("mastery_level", 1), 10)
                node["status"] = "MASTERED"

            TREE_FILE.write_text(json.dumps(tree, indent=4))
            print(f"[EVIDENCE] Logged turn evidence for: {node_id} (Covered: {evidence['concepts_covered']}, Correct: {evidence.get('successful_assessments', 0)}, Reps: {evidence.get('recent_repetition', 0)})")

        except Exception as e:
            print(f"[EVIDENCE] Error recording evidence: {e}")

    @staticmethod
    def get_parent_mastery_level(anchor_id: str) -> int:
        """
        Phase 11: Mastery Bands Parent Mastery calculation logic based on child evidence.
        - LV 1–20: one branch shows depth (at least one child level >= 10).
        - LV 21–50: one deep branch (child level >= 35) + two supporting branches (level >= 15).
        - LV 51–75: two deep branches (level >= 60) + supporting breadth.
        - LV 76–100: multiple advanced branches (level >= 85) with zero gaps.
        """
        if not TREE_FILE.exists():
            return 1

        try:
            tree = json.loads(TREE_FILE.read_text())
            nodes = tree.get("nodes", {})

            # Gather all child nodes of this anchor
            child_nodes = [node for node in nodes.values() if node.get("parent") == anchor_id or node.get("id", "").startswith(anchor_id + ".")]
            if not child_nodes:
                return 1

            levels = [node.get("mastery_level", 1) for node in child_nodes]
            max_level = max(levels) if levels else 1
            sorted_levels = sorted(levels, reverse=True)

            print(f"[EVIDENCE] Anchor '{anchor_id}' children levels: {sorted_levels}")

            # Apply Mastery Bands rules
            if len(sorted_levels) >= 3 and sorted_levels[0] >= 85 and sorted_levels[1] >= 85 and sorted_levels[2] >= 85:
                return 90
            elif len(sorted_levels) >= 2 and sorted_levels[0] >= 60 and sorted_levels[1] >= 60:
                return 65
            elif len(sorted_levels) >= 3 and sorted_levels[0] >= 35 and sorted_levels[1] >= 15 and sorted_levels[2] >= 15:
                return 40
            elif sorted_levels[0] >= 10:
                return 15
            
            return min(20, max_level)

        except Exception as e:
            print(f"[EVIDENCE] Error calculating parent mastery: {e}")
            return 1
