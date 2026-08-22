import json

def adapt_track_target_skills(active_track_name, current_targets, learned_skills, achieved_skills, get_track_path_fn):
    """
    Check if a non-target skill achieved a higher level during session
    than the lowest target skill in the track, and dynamically replace it.
    """
    if not active_track_name or not current_targets:
        return

    try:
        track_path = get_track_path_fn(active_track_name)
        if track_path.exists():
            with open(track_path, "r") as f:
                track_data = json.load(f)
            
            current_targets = track_data.get("target_skills", [])
            target_levels = {skill: learned_skills.get(skill, 1) for skill in current_targets}
            
            min_target_skill = min(target_levels, key=target_levels.get) if target_levels else None
            min_level = target_levels[min_target_skill] if min_target_skill else 0
            
            better_skill = None
            better_level = min_level
            for skill, lv_str in achieved_skills.items():
                if skill not in current_targets:
                    try:
                        lvl = int(str(lv_str).replace("LV", "").strip())
                        if lvl > better_level:
                            better_skill = skill
                            better_level = lvl
                    except ValueError:
                        pass
                        
            if better_skill and min_target_skill:
                print(f"\n>>> [DYNAMIC SKILL ADAPTATION] Replacing target skill '{min_target_skill}' (LV {min_level}) with '{better_skill}' (LV {better_level}) in track '{active_track_name}' <<<\n")
                new_targets = [better_skill if s == min_target_skill else s for s in current_targets]
                track_data["target_skills"] = new_targets
                with open(track_path, "w") as f:
                    json.dump(track_data, f, indent=2)
    except Exception as ex:
        print(f"[WARNING] Failed dynamic skill adaptation: {ex}")
