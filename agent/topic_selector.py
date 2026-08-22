"""
Topic Selection Module: Handles random/level-up/custom topic resolution and
removal from topics.json to prevent repeats.
Extracted from agent.py for modularity.
"""
import json
import random
from pathlib import Path


# Load topics from topics.json
topics_path = Path(__file__).resolve().parent.parent / "data" / "topics.json"
try:
    with open(topics_path, "r") as f:
        RANDOM_TOPICS = json.load(f)
except Exception:
    RANDOM_TOPICS = {"new_topics": ["Quantum computing basics"], "level_up_topics": []}


def select_topic(level_up, dag_engine, learned_skills):
    """Select a topic from the random pool or DAG curriculum.
    
    Args:
        level_up: Whether to use DAG curriculum level-up mode.
        dag_engine: SkillDAGEngine instance for curriculum resolution.
        learned_skills: Dict of current skill levels.
    
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
    
    new_list = RANDOM_TOPICS.get("new_topics", [])
    lvl_list = RANDOM_TOPICS.get("level_up_topics", [])
    
    if level_up:
        # Use zero-LLM deterministic DAG Curriculum Manager
        resolved = dag_engine.resolve_next_topic()
        result["topic"] = resolved["topic"]
        result["target_skill"] = resolved.get("target_skill")
        result["target_level"] = resolved.get("target_level")
        result["active_pillar"] = resolved.get("pillar")
        result["active_node"] = resolved.get("node")
        print(f"[INFO] Selected DAG curriculum topic: '{result['topic']}' (Pillar: '{resolved.get('pillar_name', result['active_pillar'])}') targeting '{result['target_skill']}' to LV {result['target_level']}")
    else:
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
            result["topic"] = "Quantum computing basics"
            print("[WARNING] topics.json is empty! Defaulting to 'Quantum computing basics'")
    
    return result


def remove_topic_from_pool(topic, target_skill=None, target_level=None):
    """Remove a topic from topics.json to prevent repeats.
    
    Args:
        topic: The topic string to remove.
        target_skill: Optional associated skill name for level_up entries.
        target_level: Optional target level for level_up entries.
    """
    new_list = RANDOM_TOPICS.get("new_topics", [])
    lvl_list = RANDOM_TOPICS.get("level_up_topics", [])
    
    removed = False
    if topic in new_list:
        new_list.remove(topic)
        removed = True
    else:
        for entry in list(lvl_list):
            if isinstance(entry, dict):
                entry_top = entry.get("topic", "")
                # Remove exact topic match or any duplicate entry targeting the same skill level
                if entry_top == topic or (target_skill and entry.get("associated_skill") == target_skill and entry.get("level_target") == target_level):
                    lvl_list.remove(entry)
                    removed = True

                    
    RANDOM_TOPICS["new_topics"] = new_list
    RANDOM_TOPICS["level_up_topics"] = lvl_list

    # Save updated list back to topics.json
    try:
        with open(topics_path, "w") as f:
            json.dump(RANDOM_TOPICS, f, indent=4)
        if removed:
            print(f"[INFO] Removed '{topic}' from topics.json to prevent repeats.")
    except Exception as e:
        print(f"[WARNING] Failed to save updated topics.json: {e}")
