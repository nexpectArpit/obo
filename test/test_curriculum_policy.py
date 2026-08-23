# test/test_curriculum_policy.py
import pytest
from agent.curriculum_policy import classify_choice, filter_choices, classify_skill
from curriculum import SkillDAGEngine

class DummyDAGEngine:
    def __init__(self):
        # Mocked structures matching actual formats
        self.TRACK_FILES = {"maths": "6_maths.json"}
        self.graph = {
            "pillars": {
                "Computer_Architecture": {
                    "nodes": {
                        "Cache_Hierarchy": {
                            "prerequisites": [],
                            "topic": "Cache Hierarchies"
                        },
                        "Cache_Coherence": {
                            "prerequisites": ["Cache_Hierarchy"],
                            "topic": "MESI MOESI Cache Coherence"
                        }
                    }
                }
            }
        }

    def load_track(self, track_name):
        return {
            "topics": [
                {"name": "Algebra: Number Systems", "covered": False},
                {"name": "Optimization: Prime Numbers", "covered": False},
                {"name": "Algebra: Linear Equations", "covered": False},
                {"name": "Algebra: Matrices", "covered": False},
                {"name": "Optimization: Lagrange Multipliers", "covered": False},
                {"name": "Optimization: Constrained Optimization", "covered": False}
            ]
        }

def test_classify_choice_conflict_resolution():
    # Target is Optimization
    # "Bayesian optimization" has "Bayesian" (reject) but is also Optimization (target) -> should be DIRECT
    assert classify_choice("maths", "Optimization", "Bayesian optimization") == "DIRECT"

    # Target is Algebra
    # "Bayesian optimization" has "Bayesian" (reject), target is Algebra -> should be REJECT since it doesn't resolve to target
    assert classify_choice("maths", "Algebra", "Bayesian optimization") == "REJECT"

    # "Bayesian inference" contains "Bayesian" (reject) -> should be REJECT
    assert classify_choice("maths", "Optimization", "Bayesian inference") == "REJECT"
    assert classify_choice("maths", "Algebra", "Bayesian inference") == "REJECT"

def test_classify_choice_levels():
    # DIRECT level
    assert classify_choice("maths", "Optimization", "convex optimization problems") == "DIRECT"
    assert classify_choice("maths", "Algebra", "abstract algebra ring theory") == "DIRECT"

    # CLOSE level (pure math / domain keywords)
    assert classify_choice("maths", "Optimization", "Explore Lie algebra and manifold structure") == "CLOSE"

    # ALLOW level (calculus, probability)
    assert classify_choice("maths", "Optimization", "epsilon-delta limit laws") == "ALLOW"
    assert classify_choice("maths", "Algebra", "real analysis continuity") == "ALLOW"

    # REJECT level (hypothesis testing, p-values)
    assert classify_choice("maths", "Optimization", "Bayesian hypothesis testing and p-values") == "REJECT"
    assert classify_choice("maths", "Algebra", "A/B testing and confidence intervals") == "REJECT"

def test_filter_choices():
    choices = [
        "Continue convex optimization problems",
        "Explore Bayesian hypothesis testing and p-values",
        "Study algebraic structures"
    ]
    res = filter_choices("maths", "Optimization", choices)

    assert "Continue convex optimization problems" in res["preferred"]
    assert "Study algebraic structures" in res["valid"]
    assert "Study algebraic structures" not in res["preferred"]
    assert "Explore Bayesian hypothesis testing and p-values" in res["rejected"]
    assert "Explore Bayesian hypothesis testing and p-values" not in res["valid"]

def test_classify_skill():
    # TARGET skills
    assert classify_skill("maths", "Linear Algebra") == "SUPPORTING"
    assert classify_skill("maths", "Abstract Algebra") == "TARGET"
    assert classify_skill("maths", "Convex Optimization") == "TARGET"

    # SUPPORTING skills
    assert classify_skill("maths", "Real Analysis") == "SUPPORTING"
    assert classify_skill("maths", "Differential Geometry") == "SUPPORTING"
    assert classify_skill("maths", "Lie Algebra") == "SUPPORTING"

    # SIDE skills
    assert classify_skill("maths", "Hypothesis Testing") == "SIDE"
    assert classify_skill("maths", "Bayesian Inference") == "SIDE"
    assert classify_skill("maths", "A/B Testing") == "SIDE"
    assert classify_skill("maths", "General Relativity") == "SIDE"

    # UNKNOWN skills
    assert classify_skill("maths", "Cooking Basics") == "UNKNOWN"

def test_track_proximity_logic():
    dag = DummyDAGEngine()
    # At active topic index 1 ("Optimization: Prime Numbers"), topic 4 ("Lagrange Multipliers") is outside sequence
    # But topic 2 ("Algebra: Linear Equations") is close (+/-3) -> should be CLOSE or ALLOW
    assert classify_choice("maths", "Optimization", "Algebra: Linear Equations", dag_engine=dag, active_track_topic_index=1) == "CLOSE"

def test_run_66_regression():
    # Test 1: Exact Run #66 regression
    choices = [
        "Yes, let's explore statistical hypothesis testing and p-values!",
        "Can we look at how hypothesis testing relates to continuous probability distributions?",
        "I want to study a different area of pure mathematics instead."
    ]
    res = filter_choices("maths", "Optimization", choices)
    
    assert "Yes, let's explore statistical hypothesis testing and p-values!" in res["rejected"]
    assert "Can we look at how hypothesis testing relates to continuous probability distributions?" in res["rejected"]
    assert "I want to study a different area of pure mathematics instead." in res["valid"]
    assert len(res["valid"]) == 1

def test_bayesian_optimization_false_positive():
    # Test 2: False-positive test (Bayesian optimization must not be rejected when targeting optimization)
    choices = [
        "Let's explore Bayesian optimization to minimize the loss function.",
        "Let's learn about Bayesian inference in neural networks."
    ]
    res = filter_choices("maths", "Optimization", choices)
    
    assert "Let's explore Bayesian optimization to minimize the loss function." in res["valid"]
    assert "Let's learn about Bayesian inference in neural networks." in res["rejected"]

def test_zero_valid_choices():
    # Test 3: Zero-valid test
    choices = [
        "Explore hypothesis testing.",
        "Learn about Bayesian inference.",
        "Study statistical power analysis."
    ]
    res = filter_choices("maths", "Optimization", choices)
    assert len(res["valid"]) == 0
    assert len(res["rejected"]) == 3

def test_mcq_answer_detection():
    # Test MCQ answer detection: numeric options should bypass filtering
    choices = [
        "s = 5",
        "s = 2",
        "s = 6",
        "s = 3"
    ]
    res = filter_choices("maths", "Optimization", choices)
    assert len(res["valid"]) == 4
    assert len(res["rejected"]) == 0

def test_adversarial_wordings():
    # Test B: Adversarial wording checks
    choices = [
        "Let's study inferential methods for comparing populations.",
        "Let's explore uncertainty and statistical decision procedures.",
        "Let's investigate Bayesian inference.",
        "Let's study probability distributions for hypothesis decisions."
    ]
    res = filter_choices("maths", "Optimization", choices)
    for c in choices:
        assert c in res["rejected"]
    assert len(res["valid"]) == 0

def test_legitimate_overlap():
    # Test C: Legitimate mathematical overlap checks
    choices = [
        "Let's explore Bayesian optimization.",
        "Let's study differential geometry.",
        "Let's learn about Lie algebra.",
        "Let's study symplectic geometry.",
        "Let's practice convex optimization."
    ]
    res = filter_choices("maths", "Optimization", choices)
    for c in choices:
        assert c in res["valid"]
    assert len(res["rejected"]) == 0

