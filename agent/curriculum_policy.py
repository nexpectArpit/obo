# agent/curriculum_policy.py
import json
from pathlib import Path
from curriculum.dag_engine import TRACK_FILES


# Track domain policies with exit keywords
TRACK_REJECT_KEYWORDS = {
    "maths": [
        "hypothesis testing", "p-value", "t-test", "z-test", "a/b testing",
        "frequentist", "statistical power", "confidence interval",
        "statistical inference", "regression analysis", "multiple testing",
        "anova", "multi-armed bandit", "bayesian", "statistics", "statistical",
        "inferential", "uncertainty", "hypothesis"
    ],
    "cpp": [
        "java", "python", "rust", "database", "sql", "html", "css", "javascript", "web framework"
    ],
    "os": [
        "web browser", "react", "database optimization", "sql"
    ],
    "dl": [
        "web development", "frontend", "sql", "data cleaning"
    ]
}

TARGET_SKILLS_KEYWORDS = {
    "optimization": {
        "direct": [
            "optimization", "convex optimization", "constrained optimization",
            "lagrange", "integer programming", "branch and bound",
            "convex analysis", "linear programming", "gradient descent",
            "manifold optimization", "discrete optimization"
        ],
        "close": [
            "diagonalization", "singular value decomposition", "svd",
            "matrix norms", "continuity", "lie algebra", "manifold",
            "differential geometry", "symplectic geometry", "calculus of variations",
            "extreme value theorem"
        ]
    },
    "algebra": {
        "direct": [
            "algebra", "abstract algebra", "group theory", "ring theory",
            "field theory", "number theory", "vector space", "linear equations",
            "matrix operations", "determinants", "least squares", "combinatorics"
        ],
        "close": [
            "matrix", "vector", "eigenvalues", "characteristic polynomial",
            "characteristic equation", "limits", "derivatives", "taylor series",
            "integration", "linear algebra"
        ]
    }
}

def classify_choice(track_name: str, target_skill: str, choice_text: str, dag_engine=None, active_track_topic_index=None) -> str:
    """
    Classify Oboe choice into one of 5 relevance levels:
    - DIRECT: Directly matches or names the current target skill/topic.
    - CLOSE: Prerequisite/successor node or nearby topic in track sequence.
    - ALLOW: Stays in the broader domain (e.g. mathematics) but not directly related to the target.
    - REJECT: Exits the domain (e.g. statistical methodology when target is pure math).
    - UNKNOWN: Fallback.

    Priority order:
    1. Reject keywords (with conflict resolution).
    2. Direct match to target skill.
    3. DAG prerequisite/successor or Track sequence proximity.
    4. General domain keywords.
    """
    text = choice_text.lower()
    track_lower = (track_name or "").lower()
    target_lower = (target_skill or "").lower()

    # Step 1: Reject keywords check — collect all matched reject keywords first,
    # then apply conflict resolution in one pass (order-independent)
    reject_kws = TRACK_REJECT_KEYWORDS.get(track_lower, [])
    matched_rejects = [kw for kw in reject_kws if kw in text]
    if matched_rejects:
        if target_lower and target_lower in text:
            # Conflict resolution: target skill is present in the text.
            # Check if ALL matched reject keywords can be explained by the target's presence.
            # If any reject keyword is unrelated to the target, still reject.
            unresolvable = [kw for kw in matched_rejects if target_lower not in kw and kw not in target_lower]
            if not unresolvable:
                pass  # All rejects resolved by target presence — fall through to positive checks
            else:
                return "REJECT"
        else:
            return "REJECT"

    # Step 2: Direct match
    if target_lower and target_lower in text:
        return "DIRECT"

    # Step 3: DAG or Track proximity
    if dag_engine:
        # A. Core CS DAG Check
        if track_lower in [p.lower() for p in dag_engine.graph.get("pillars", {}).keys()]:
            # Find the active pillar
            pillar_key = next((k for k in dag_engine.graph["pillars"].keys() if k.lower() == track_lower), None)
            if pillar_key:
                nodes = dag_engine.graph["pillars"][pillar_key].get("nodes", {})
                # Find current target node
                target_node_key = next((k for k in nodes.keys() if k.replace("_", " ").lower() == target_lower), None)
                if target_node_key:
                    node = nodes[target_node_key]
                    prereqs = [p.replace("_", " ").lower() for p in node.get("prerequisites", [])]
                    # Find successors (nodes that have target_node_key in prerequisites)
                    successors = []
                    for nk, nv in nodes.items():
                        if target_node_key in nv.get("prerequisites", []):
                            successors.append(nk.replace("_", " ").lower())

                    # If choice text matches a prerequisite or successor, it is CLOSE
                    if any(p in text for p in prereqs) or any(s in text for s in successors):
                        return "CLOSE"
                    
                    # If choice text matches any other node in the same pillar, it is ALLOW
                    for nk in nodes.keys():
                        node_name = nk.replace("_", " ").lower()
                        if node_name in text:
                            return "ALLOW"

        # B. Pinned Track Check
        elif track_lower in TRACK_FILES:
            try:
                track_data = dag_engine.load_track(track_lower)
                topics = track_data.get("topics", [])
                
                # If active index is known, check proximity
                if active_track_topic_index is not None:
                    # Direct match to active topic
                    active_topic = topics[active_track_topic_index]
                    if active_topic["name"].lower() in text:
                        return "DIRECT"
                    
                    # Proximity check: +/- 3 topics in the sequence are CLOSE
                    start = max(0, active_track_topic_index - 3)
                    end = min(len(topics), active_track_topic_index + 4)
                    nearby_topics = topics[start:end]
                    for idx, topic in enumerate(nearby_topics):
                        actual_idx = start + idx
                        if actual_idx == active_track_topic_index:
                            continue
                        if topic["name"].lower() in text or any(word in text for word in topic["name"].lower().split()):
                            return "CLOSE"

                # Check general overlap with any topic in this track
                for topic in topics:
                    if topic["name"].lower() in text:
                        return "ALLOW"
            except Exception as e:
                print(f"[CURRICULUM POLICY] Error resolving track proximity: {e}")

    # Fallback checks based on domain keywords when dag_engine/index is not present
    if track_lower == "maths":
        direct_kws = get_domain_keywords(track_name, tier="direct", target_skill=target_skill)
        close_kws = get_domain_keywords(track_name, tier="close", target_skill=target_skill)
        if any(kw in text for kw in direct_kws):
            return "DIRECT"
        if any(kw in text for kw in close_kws):
            return "CLOSE"
        math_kws = ["algebra", "optimization", "matrix", "vector", "calculus", "limit", "derivative", "integral", "geometry", "group", "ring", "field", "analysis", "continuity", "function", "topology", "combinatorics"]
        if any(kw in text for kw in math_kws):
            return "ALLOW"

    return "UNKNOWN"


def is_curriculum_choice(choices: list[str]) -> bool:
    """
    Determine if a list of suggested replies represents curriculum direction
    decisions rather than MCQ/concept answers.
    """
    curriculum_indicators = [
        "explore", "study", "continue", "learn about", "tell me about",
        "explain", "move into", "delve into", "look at", "different area",
        "yes, let's", "mathematics instead", "transition to"
    ]
    # If any choice contains a curriculum indicator, treat the choices as curriculum directions
    for choice in choices:
        text = choice.lower()
        if any(ind in text for ind in curriculum_indicators):
            return True
    return False


def filter_choices(track_name: str, target_skill: str, choices: list[str], dag_engine=None, active_track_topic_index=None) -> dict:
    """
    Filter list of options into valid, preferred, and rejected lists.
    """
    valid = []
    preferred = []
    rejected = []

    # If this is not a curriculum topic choice (it is an MCQ answer like numbers or formulas),
    # do NOT filter or reject anything. Everything is valid.
    if not is_curriculum_choice(choices):
        # Structured log for MCQ choices
        print(f"\n[CURRICULUM] MCQ Answer Choices detected (No filtration applied)")
        print(f"Track: {track_name} | Target: {target_skill}")
        print(f"Oboe choices: {choices}\n")
        return {
            "valid": choices,
            "preferred": [],
            "rejected": []
        }

    for choice in choices:
        classification = classify_choice(track_name, target_skill, choice, dag_engine, active_track_topic_index)
        if classification == "REJECT":
            rejected.append(choice)
        else:
            valid.append(choice)
            if classification in ("DIRECT", "CLOSE"):
                preferred.append(choice)

    # Print structured [CURRICULUM] log
    print(f"\n[CURRICULUM]")
    print(f"Track: {track_name} | Target: {target_skill}")
    print(f"Oboe choices: {len(choices)}")
    print(f"  DIRECT/CLOSE (Preferred): {preferred}")
    print(f"  ALLOW/UNKNOWN (Valid): {[c for c in valid if c not in preferred]}")
    print(f"  REJECTED: {rejected}")
    print(f"LLM-visible choices: {valid}\n")

    return {
        "valid": valid,
        "preferred": preferred,
        "rejected": rejected
    }


def classify_skill(track_name: str, skill_name: str) -> str:
    """
    Classify Oboe achieved skill into:
    - TARGET: Directly aligns with the track targets.
    - SUPPORTING: Mathematically or conceptually relevant prerequisite/extension.
    - SIDE: Off-track / exit domain.
    - UNKNOWN: Fallback.
    """
    skill_lower = skill_name.lower()
    track_lower = (track_name or "").lower()

    if track_lower == "maths":
        # Check supporting skills first
        supporting_patterns = [
            "linear algebra", "convex analysis", "real analysis", "complex analysis",
            "ring theory", "group theory", "lie algebra", "calculus", "matrix theory",
            "graph theory", "topology", "combinatorics", "proof writing", "mathematical logic",
            "propositional logic", "differential geometry", "symplectic geometry"
        ]
        if any(pattern in skill_lower for pattern in supporting_patterns):
            # Special override: abstract algebra is TARGET, but linear algebra/lie algebra is SUPPORTING
            if "abstract algebra" in skill_lower:
                return "TARGET"
            return "SUPPORTING"
            
        # Target skills
        if any(target in skill_lower for target in ["algebra", "optimization"]):
            # Make sure it's not a side skill like "bayesian optimization"
            if "bayesian" in skill_lower or "statistical" in skill_lower:
                return "SIDE"
            return "TARGET"

        # Side skills (statistics, physics/mechanics, etc.)
        side_patterns = [
            "statistics", "hypothesis testing", "bayesian", "p-value", "t-test",
            "z-test", "a/b testing", "frequentist", "confidence interval",
            "statistical", "regression", "multi-armed bandit", "robotics",
            "physics", "general relativity", "gauge theory", "quantum"
        ]
        if any(pattern in skill_lower for pattern in side_patterns):
            return "SIDE"

    # Core CS Tracks
    elif track_lower in ("cpp", "os", "dl", "arch", "ds"):
        if track_lower in TRACK_FILES:
            try:
                from curriculum.dag_engine import SkillDAGEngine
                track_data = SkillDAGEngine.load_track(track_lower)
                target_skills = [s.lower().strip() for s in track_data.get("target_skills", [])]
                if skill_lower in target_skills:
                    return "TARGET"
                return "SUPPORTING"
            except Exception as e:
                print(f"[WARNING] Failed to load track '{track_lower}' for skill classification: {e}")
                return "UNKNOWN"
        return "TARGET"

    return "UNKNOWN"


def get_domain_keywords(track_name: str, tier: str = "all", target_skill: str = None) -> list[str]:
    """
    Return lists of keywords for steering alignment checks.
    """
    track_lower = (track_name or "").lower()
    if track_lower == "maths":
        if target_skill:
            target_clean = target_skill.lower().strip()
            kws = TARGET_SKILLS_KEYWORDS.get(target_clean)
            if not kws:
                # partial match fallback
                matched_key = next((k for k in TARGET_SKILLS_KEYWORDS.keys() if k in target_clean or target_clean in k), None)
                if matched_key:
                    kws = TARGET_SKILLS_KEYWORDS[matched_key]
            if kws:
                if tier == "direct":
                    return kws["direct"]
                if tier == "close":
                    return kws["close"]
                return kws["direct"] + kws["close"]

        direct = [
            "optimization", "convex optimization", "constrained optimization",
            "lagrange multiplier", "integer programming", "branch and bound",
            "algebra", "abstract algebra", "group theory", "ring theory",
            "field theory", "number theory", "graph algorithm", "combinatorics",
            "discrete optimization"
        ]
        close = [
            "lie algebra", "symplectic geometry", "differential geometry",
            "manifold", "linear algebra", "matrix", "eigenvalue",
            "calculus of variations", "convex analysis", "mathematical logic",
            "propositional logic", "proof writing", "graph theory", "topology"
        ]
        if tier == "direct":
            return direct
        if tier == "close":
            return close
        return direct + close
    return []
