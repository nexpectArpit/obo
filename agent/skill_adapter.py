import json
from pathlib import Path

def adapt_track_target_skills(active_track_name, current_targets, learned_skills, achieved_skills, get_track_path_fn):
    """
    Data Analysis & Dynamic Steering:
    Compares all recorded and newly achieved skills for the active track,
    identifies the top highest-level skills, updates the track's target_skills in JSON,
    and inclines the next chat sessions directly in that direction to compound mastery to LV 100+.
    """
    if not active_track_name:
        return

    try:
        track_path = get_track_path_fn(active_track_name)
        if track_path and track_path.exists():
            with open(track_path, "r") as f:
                track_data = json.load(f)
            
            # Combine learned_skills and achieved_skills
            all_skills = dict(learned_skills or {})
            for sk, lv_val in (achieved_skills or {}).items():
                try:
                    lvl_num = int(str(lv_val).replace("LV", "").strip())
                    if lvl_num > all_skills.get(sk, 0):
                        all_skills[sk] = lvl_num
                except ValueError:
                    pass

            if not all_skills:
                return

            # Track-specific relevant keyword filter to keep steering focused on track domain
            track_keywords = {
                "cpp": ["cpp", "c++", "algorithm", "data structure", "tree", "graph", "dynamic programming", "stack", "queue", "pointer", "array", "string", "hash", "sorting"],
                "arch": ["architecture", "memory", "cache", "pipeline", "network", "tcp", "ip", "socket", "cpu", "bus", "assembly"],
                "os": ["operating system", "os", "thread", "process", "syscall", "system call", "mutex", "semaphore", "virtual memory", "paging", "file system", "concurrency"],
                "ds": ["data science", "machine learning", "statistics", "hypothesis", "regression", "probability", "pandas", "numpy", "eda", "clustering"],
                "dl": ["deep learning", "neural network", "machine learning", "gradient descent", "sgd", "convolution", "cnn", "transformer", "attention", "loss", "backprop", "activation", "optimization"],
                "maths": ["algebra", "linear algebra", "calculus", "matrix", "vector", "optimization", "probability", "eigen"]
            }
            
            keywords = track_keywords.get(active_track_name.lower(), [])
            
            # Filter skills relevant to this track
            relevant_skills = []
            for skill_name, lvl in all_skills.items():
                sk_lower = skill_name.lower()
                is_relevant = any(kw in sk_lower for kw in keywords) or (active_track_name.lower() in sk_lower)
                if is_relevant:
                    relevant_skills.append((skill_name, lvl))
                    
            if not relevant_skills:
                # If no keyword matched, use all available skills
                relevant_skills = list(all_skills.items())

            # Sort by highest skill level descending
            relevant_skills.sort(key=lambda x: x[1], reverse=True)
            
            # Pick the top 2 highest leveled skills to steer the chat
            top_targets = [sk for sk, _ in relevant_skills[:2]]
            
            if top_targets:
                print(f"\n>>> [DYNAMIC STEERING] Top Mastery Skills in Track '{active_track_name}': {relevant_skills[:3]} <<<")
                print(f">>> [DYNAMIC STEERING] Updating target focus to: {top_targets} to incline conversation towards highest growth! <<<\n")
                track_data["target_skills"] = top_targets
                with open(track_path, "w") as f:
                    json.dump(track_data, f, indent=2)
    except Exception as ex:
        print(f"[WARNING] Failed dynamic skill adaptation: {ex}")
