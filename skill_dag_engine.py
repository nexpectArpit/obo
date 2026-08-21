#!/usr/bin/env python3
"""
SKILL DAG ENGINE (Curriculum Manager)

100% Deterministic, Zero-LLM State Machine.
Manages obo_skill_graph.json to resolve prerequisite edges,
adaptively prioritize weakest Core CS pillars based on level gap to LV 25,
and update graph state from external Oboe sidebar feedback.
"""

import os
import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GRAPH_PATH = BASE_DIR / "obo_skill_graph.json"
LEARNED_SKILLS_PATH = BASE_DIR / "learned_skills.json"

# Pinned Track Mastery: Maps short CLI names to track JSON filenames and pinned chat titles
TRACK_FILES = {
    "cpp":   "1_cpp.json",
    "arch":  "2_computer_architecture_and_networking.json",
    "os":    "3_os.json",
    "ds":    "4_data_science.json",
    "dl":    "5_dl.json",
    "maths": "6_maths.json",
}


class SkillDAGEngine:
    def __init__(self, graph_path=None, learned_skills_path=None):
        self.graph_path = Path(graph_path) if graph_path else GRAPH_PATH
        self.learned_skills_path = Path(learned_skills_path) if learned_skills_path else LEARNED_SKILLS_PATH
        self.graph = self.load_graph()
        self.sync_external_learned_skills()

    def load_graph(self):
        """Load persistent graph structure from JSON."""
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Skill graph not found at {self.graph_path}")
        with open(self.graph_path, "r") as f:
            return json.load(f)

    def save_graph(self):
        """Save updated graph state back to JSON."""
        with open(self.graph_path, "w") as f:
            json.dump(self.graph, f, indent=2)

    def sync_external_learned_skills(self):
        """Read external Oboe sidebar state (source of truth) and sync levels."""
        if not self.learned_skills_path.exists():
            return

        try:
            with open(self.learned_skills_path, "r") as f:
                learned_skills = json.load(f)
        except Exception:
            return

        # Map external skill names to internal DAG nodes
        updated = False
        for pillar_key, pillar in self.graph.get("pillars", {}).items():
            for node_key, node in pillar.get("nodes", {}).items():
                # Check for exact or partial skill name match in learned_skills
                node_name = node_key.replace("_", " ")
                for ext_skill, ext_level in learned_skills.items():
                    if ext_skill.lower() in node_name.lower() or node_name.lower() in ext_skill.lower():
                        if ext_level > node["level"]:
                            node["level"] = ext_level
                            updated = True
                            if ext_level >= node["target_level"]:
                                node["status"] = "mastered"
                                node["target_level"] = ext_level + 1

        self.update_prerequisite_statuses()
        if updated:
            self.save_graph()

    def update_prerequisite_statuses(self):
        """Enforce strict DAG edge rules: A node is 'available' only if all prerequisites are 'mastered'."""
        for pillar_key, pillar in self.graph.get("pillars", {}).items():
            nodes = pillar.get("nodes", {})
            for node_key, node in nodes.items():
                if node.get("status") == "mastered":
                    continue

                prereqs = node.get("prerequisites", [])
                all_prereqs_mastered = True
                for prereq_key in prereqs:
                    prereq_node = nodes.get(prereq_key)
                    if not prereq_node or prereq_node.get("status") != "mastered":
                        all_prereqs_mastered = False
                        break

                if all_prereqs_mastered:
                    if node.get("status") == "blocked":
                        node["status"] = "available"
                else:
                    node["status"] = "blocked"

    def get_pillar_average_level(self, pillar_key):
        """Calculate average level of all nodes in a pillar."""
        pillar = self.graph["pillars"].get(pillar_key, {})
        nodes = pillar.get("nodes", {})
        if not nodes:
            return 1.0
        total_lv = sum(n.get("level", 1) for n in nodes.values())
        return total_lv / len(nodes)

    def get_weakest_core_pillar(self):
        """
        Calculate selection probability based on level gap to target level (25):
        Gap = 25 - current_avg_level
        The pillar with the largest level gap gets the highest probability weight.
        """
        target = self.graph.get("target_mastery_level", 25)
        pillars = self.graph.get("pillars", {})

        gaps = {}
        for p_key in pillars.keys():
            avg_lv = self.get_pillar_average_level(p_key)
            gaps[p_key] = max(1.0, float(target - avg_lv))

        total_gap = sum(gaps.values())
        weights = {p_key: gaps[p_key] / total_gap for p_key in gaps.keys()}

        # Weighted random choice
        chosen_pillar = random.choices(
            list(weights.keys()),
            weights=list(weights.values()),
            k=1
        )[0]

        return chosen_pillar

    def get_available_nodes(self, pillar_key):
        """Get all nodes in a pillar that are 'available' or 'in_progress'."""
        nodes = self.graph["pillars"].get(pillar_key, {}).get("nodes", {})
        candidates = []
        for n_key, n_val in nodes.items():
            if n_val.get("status") in ["available", "in_progress"]:
                candidates.append((n_key, n_val))
        return candidates

    def resolve_next_topic(self):
        """
        Deterministic topic selector:
        1. Decide 70% Core CS vs 30% Breadth.
        2. If Core CS: select weakest pillar by level gap, resolve available node.
        3. Returns topic metadata object with ZERO LLM API calls.
        """
        self.update_prerequisite_statuses()

        # 70% Core CS / 30% Breadth
        is_core_cs = random.random() < 0.70

        if not is_core_cs:
            breadth_topics = self.graph.get("general_knowledge_topics", [])
            chosen_topic = random.choice(breadth_topics) if breadth_topics else "General Physics and Thermodynamics"
            return {
                "pillar": "General_Knowledge",
                "node": "Breadth_Module",
                "topic": chosen_topic,
                "target_skill": "General Knowledge",
                "target_level": 1,
                "is_core_cs": False
            }

        # Select weakest core pillar
        pillar_key = self.get_weakest_core_pillar()
        candidates = self.get_available_nodes(pillar_key)

        # Fallback to any pillar with available nodes if chosen pillar has 0 available nodes
        if not candidates:
            for p_key in self.graph["pillars"].keys():
                candidates = self.get_available_nodes(p_key)
                if candidates:
                    pillar_key = p_key
                    break

        if not candidates:
            # Fallback if all core nodes are blocked or completed
            return {
                "pillar": "Computer_Architecture",
                "node": "Cache_Hierarchy",
                "topic": "Cache Hierarchies and Line Allocation Mechanics",
                "target_skill": "Computer Architecture",
                "target_level": 3,
                "is_core_cs": True
            }

        # Pick node with lowest level / highest attempts
        candidates.sort(key=lambda x: (x[1]["level"], x[1]["attempts"]))
        node_key, node = candidates[0]

        # Update node status to in_progress
        node["status"] = "in_progress"
        self.save_graph()

        pillar_name = self.graph["pillars"][pillar_key].get("name", pillar_key)
        return {
            "pillar": pillar_key,
            "pillar_name": pillar_name,
            "node": node_key,
            "topic": node["topic"],
            "target_skill": node_key.replace("_", " "),
            "target_level": node["target_level"],
            "is_core_cs": True
        }

    def update_skill_level(self, pillar_key, node_key, new_level):
        """
        Update graph after session based on external Oboe feedback.
        If new_level >= target_level: mark node 'mastered', increment target_level, unblock children.
        If no level-up: increment attempts counter.
        """
        pillar = self.graph.get("pillars", {}).get(pillar_key)
        if not pillar:
            return

        node = pillar.get("nodes", {}).get(node_key)
        if not node:
            return

        old_level = node["level"]
        if new_level > old_level:
            node["level"] = new_level
            if new_level >= node["target_level"]:
                node["status"] = "mastered"
                node["target_level"] = new_level + 1
                node["attempts"] = 0
                print(f"[DAG ENGINE] Node '{node_key}' MASTERED at LV {new_level}! Next Target: LV {node['target_level']}")
            else:
                node["status"] = "in_progress"
        else:
            node["attempts"] += 1
            node["status"] = "available"
            print(f"[DAG ENGINE] Node '{node_key}' attempt #{node['attempts']} completed without level-up. Maintained at LV {old_level}.")

        self.update_prerequisite_statuses()
        self.save_graph()

    # ─── PINNED TRACK MASTERY METHODS ─────────────────────────────

    @staticmethod
    def get_track_path(track_name):
        """Resolve track JSON file path from short name."""
        filename = TRACK_FILES.get(track_name)
        if not filename:
            raise ValueError(f"Unknown track '{track_name}'. Valid: {list(TRACK_FILES.keys())}")
        return BASE_DIR / "tracks" / filename

    @staticmethod
    def load_track(track_name):
        """Load a track JSON file."""
        path = SkillDAGEngine.get_track_path(track_name)
        if not path.exists():
            raise FileNotFoundError(f"Track file not found: {path}")
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def save_track(track_name, data):
        """Save updated track JSON file."""
        path = SkillDAGEngine.get_track_path(track_name)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def resolve_next_track_topic(track_name):
        """
        Return the first uncovered sub-topic from the track.
        Returns dict with: track_name, pinned_chat_title, topic_index, topic_name, prompt, target_skills
        Returns None if all topics are covered.
        """
        data = SkillDAGEngine.load_track(track_name)
        pinned_chat_title = data.get("pinned_chat_title", "")
        target_skills = data.get("target_skills", [])

        for idx, topic in enumerate(data.get("topics", [])):
            if not topic.get("covered", False):
                return {
                    "track_name": track_name,
                    "pinned_chat_title": pinned_chat_title,
                    "topic_index": idx,
                    "topic_name": topic["name"],
                    "prompt": topic["prompt"],
                    "target_skills": target_skills,
                }

        # All topics covered — wrap around to first topic
        print(f"[DAG ENGINE] All {len(data.get('topics', []))} topics in track '{track_name}' covered! Wrapping around.")
        for topic in data.get("topics", []):
            topic["covered"] = False
        SkillDAGEngine.save_track(track_name, data)
        first = data["topics"][0]
        return {
            "track_name": track_name,
            "pinned_chat_title": pinned_chat_title,
            "topic_index": 0,
            "topic_name": first["name"],
            "prompt": first["prompt"],
            "target_skills": target_skills,
        }

    @staticmethod
    def mark_topic_covered(track_name, topic_index, achieved_level=0):
        """Mark a sub-topic as covered and record the level achieved."""
        data = SkillDAGEngine.load_track(track_name)
        topics = data.get("topics", [])
        if 0 <= topic_index < len(topics):
            topics[topic_index]["covered"] = True
            topics[topic_index]["level_at_cover"] = achieved_level
            SkillDAGEngine.save_track(track_name, data)
            print(f"[DAG ENGINE] Track '{track_name}' topic #{topic_index} '{topics[topic_index]['name']}' marked covered (LV {achieved_level}).")

    @staticmethod
    def get_track_progress(track_name):
        """Return progress stats for a track."""
        data = SkillDAGEngine.load_track(track_name)
        topics = data.get("topics", [])
        covered = sum(1 for t in topics if t.get("covered", False))
        return {
            "total": len(topics),
            "covered": covered,
            "remaining": len(topics) - covered,
            "percent": round(100 * covered / len(topics), 1) if topics else 0
        }

    @staticmethod
    def get_all_tracks_progress():
        """Return progress for all 6 tracks."""
        result = {}
        for track_name in TRACK_FILES:
            try:
                result[track_name] = SkillDAGEngine.get_track_progress(track_name)
            except Exception:
                result[track_name] = {"total": 0, "covered": 0, "remaining": 0, "percent": 0}
        return result

