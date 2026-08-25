"""
Topic Selection Module: Handles random/level-up/custom topic resolution and
removal from topics.json to prevent repeats.
Extracted from agent.py for modularity.
"""
import json
import random
from pathlib import Path


topics_path = Path(__file__).resolve().parent.parent / "data" / "topics.json"


def _load_topics() -> dict:
    """Always read from disk to avoid stale in-memory cache across processes/restarts."""
    try:
        with open(topics_path, "r") as f:
            return json.load(f)
    except Exception:
        return {"new_topics": [], "level_up_topics": []}


def _save_topics(data: dict):
    try:
        with open(topics_path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[WARNING] Failed to save updated topics.json: {e}")


def select_topic(level_up, dag_engine, learned_skills):
    """Select a topic from the random pool or DAG curriculum.

    Returns:
        dict with keys: topic, target_skill, target_level, active_pillar, active_node
    """
    result = {
        "topic": None,
        "target_skill": None,
        "target_level": None,
        "active_pillar": None,
        "active_node": None,
    }

    if level_up:
        # Use zero-LLM deterministic DAG Curriculum Manager
        resolved = dag_engine.resolve_next_topic()
        result["topic"] = resolved["topic"]
        result["target_skill"] = resolved.get("target_skill")
        result["target_level"] = resolved.get("target_level")
        result["active_pillar"] = resolved.get("pillar")
        result["active_node"] = resolved.get("node")
        print(f"[INFO] Selected DAG curriculum topic: '{result['topic']}' targeting '{result['target_skill']}' to LV {result['target_level']}")
        return result

    # Read fresh from disk every time — avoids stale cache in multi-process setups
    topics_data = _load_topics()
    new_list = topics_data.get("new_topics", [])
    lvl_list = topics_data.get("level_up_topics", [])

    combined = []
    for t in new_list:
        combined.append(("new", t))
    for entry in lvl_list:
        if isinstance(entry, dict) and "topic" in entry:
            combined.append(("level_up", entry))

    if combined:
        choice_type, entry = random.choice(combined)
        if choice_type == "level_up":
            result["topic"] = entry["topic"]
            result["target_skill"] = entry.get("associated_skill")
            result["target_level"] = entry.get("level_target")
        else:
            result["topic"] = entry
        print(f"[INFO] Selected random learning topic: '{result['topic']}' (type: {choice_type})")
    else:
        # Pool is empty — fall back to DAG curriculum instead of looping on same hardcoded topic
        print("[WARNING] topics.json pool is empty. Falling back to DAG curriculum topic.")
        try:
            resolved = dag_engine.resolve_next_topic()
            result["topic"] = resolved["topic"]
            result["target_skill"] = resolved.get("target_skill")
            result["target_level"] = resolved.get("target_level")
            result["active_pillar"] = resolved.get("pillar")
            result["active_node"] = resolved.get("node")
            print(f"[INFO] DAG fallback topic: '{result['topic']}'")
        except Exception as e:
            print(f"[WARNING] DAG fallback also failed: {e}. Using hardcoded default.")
            result["topic"] = "Quantum computing basics"

    return result


def remove_topic_from_pool(topic, target_skill=None, target_level=None):
    """Remove a topic from topics.json to prevent repeats."""
    # Always read fresh from disk before modifying
    topics_data = _load_topics()
    new_list = topics_data.get("new_topics", [])
    lvl_list = topics_data.get("level_up_topics", [])

    removed = False
    if topic in new_list:
        new_list.remove(topic)
        removed = True
    else:
        for entry in list(lvl_list):
            if isinstance(entry, dict):
                entry_top = entry.get("topic", "")
                if entry_top == topic or (
                    target_skill
                    and entry.get("associated_skill") == target_skill
                    and entry.get("level_target") == target_level
                ):
                    lvl_list.remove(entry)
                    removed = True

    topics_data["new_topics"] = new_list
    topics_data["level_up_topics"] = lvl_list
    _save_topics(topics_data)

    if removed:
        print(f"[INFO] Removed '{topic}' from topics.json to prevent repeats.")
