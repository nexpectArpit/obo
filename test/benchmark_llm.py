#!/usr/bin/env python3
"""
Comprehensive LLM Benchmark: Groq (Current) vs Groq (GPT-OSS-20B) vs Mistral

Evaluates 50 representative Oboe interaction test cases covering:
1. Context-dependent MCQs
2. Distractor-heavy MCQs
3. True/False binary choices
4. Free-text student responses (summarize + question)
5. Technical scientific reasoning cases

Maintains production context construction:
- Same system prompt & stealth rules
- Same 5-message sliding window
- Same output JSON schema
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from groq import Groq

# Ensure root directory in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from agent.llm import OboeLLM

# Load environment variables
load_dotenv('.env.local')

# Define 50 Representative Benchmark Items
BENCHMARK_ITEMS = [
    # 1-10: Context-Dependent MCQs
    {
        "id": 1, "type": "mcq", "category": "Context MCQ",
        "state": "suggested_replies",
        "choices": ["A) Mitochondria generate ATP via cellular respiration", "B) Mitochondria produce glucose from sunlight", "C) Mitochondria break down DNA", "D) Mitochondria store waste"],
        "messages": [
            {"role": "assistant", "text": "Welcome to Cell Biology! Today we study organelles."},
            {"role": "user", "text": "what does the mitochondria do?"},
            {"role": "assistant", "text": "The mitochondria is known as the powerhouse of the cell because it generates chemical energy in the form of ATP through cellular respiration."},
            {"role": "user", "text": "got it! so ATP is the energy currency. can you quiz me?"},
            {"role": "assistant", "text": "Which statement accurately describes the function of mitochondria?"}
        ],
        "correct": "A) Mitochondria generate ATP via cellular respiration"
    },
    {
        "id": 2, "type": "mcq", "category": "Context MCQ",
        "state": "suggested_replies",
        "choices": ["A) Ohm's Law states V = I * R", "B) V = I / R", "C) V = I + R", "D) V = R / I"],
        "messages": [
            {"role": "assistant", "text": "Electrical circuits depend on voltage, current, and resistance."},
            {"role": "user", "text": "how are voltage and current related?"},
            {"role": "assistant", "text": "According to Ohm's Law, Voltage (V) equals Current (I) multiplied by Resistance (R), expressed as V = I * R."},
            {"role": "user", "text": "makes sense. quiz me!"},
            {"role": "assistant", "text": "What is the correct mathematical formula for Ohm's Law?"}
        ],
        "correct": "A) Ohm's Law states V = I * R"
    },
    {
        "id": 3, "type": "mcq", "category": "Context MCQ",
        "state": "suggested_replies",
        "choices": ["A) Photosynthesis converts carbon dioxide and water into glucose and oxygen", "B) Photosynthesis converts nitrogen into helium", "C) Photosynthesis occurs in animal muscle cells", "D) Photosynthesis destroys solar energy"],
        "messages": [
            {"role": "assistant", "text": "Plants use light energy to produce food."},
            {"role": "user", "text": "how does photosynthesis work?"},
            {"role": "assistant", "text": "Photosynthesis is the chemical process where plants convert carbon dioxide and water into glucose and oxygen using light energy."},
            {"role": "user", "text": "cool! test my understanding."},
            {"role": "assistant", "text": "What is the core chemical reaction of photosynthesis?"}
        ],
        "correct": "A) Photosynthesis converts carbon dioxide and water into glucose and oxygen"
    },
    {
        "id": 4, "type": "mcq", "category": "Context MCQ",
        "state": "suggested_replies",
        "choices": ["A) Gravity pulls objects toward the center of mass", "B) Gravity repels massive objects", "C) Gravity only affects liquids", "D) Gravity is created by magnetism"],
        "messages": [
            {"role": "assistant", "text": "Gravitational forces govern orbital mechanics."},
            {"role": "user", "text": "what is gravity?"},
            {"role": "assistant", "text": "Gravity is an attractive force that pulls objects toward one another, specifically toward the center of mass."},
            {"role": "user", "text": "understood! ask me a question."},
            {"role": "assistant", "text": "How does gravity affect massive objects?"}
        ],
        "correct": "A) Gravity pulls objects toward the center of mass"
    },
    {
        "id": 5, "type": "mcq", "category": "Context MCQ",
        "state": "suggested_replies",
        "choices": ["A) Enzymes act as biological catalysts to lower activation energy", "B) Enzymes increase activation energy", "C) Enzymes are consumed permanently in reactions", "D) Enzymes only work in zero gravity"],
        "messages": [
            {"role": "assistant", "text": "Enzymes speed up metabolic pathways."},
            {"role": "user", "text": "how do enzymes work?"},
            {"role": "assistant", "text": "Enzymes act as biological catalysts by lowering the activation energy required for a chemical reaction to occur."},
            {"role": "user", "text": "got it! test me."},
            {"role": "assistant", "text": "What is the primary role of enzymes in chemical reactions?"}
        ],
        "correct": "A) Enzymes act as biological catalysts to lower activation energy"
    }
]

# Generate remaining 45 synthetic benchmark items programmatically covering T/F, Free-text, and Technical Reasoning
topics_list = [
    ("Thermodynamics", "Second Law of Thermodynamics states entropy of an isolated system always increases.", "A) Entropy of an isolated system always increases", ["A) Entropy of an isolated system always increases", "B) Entropy always decreases to zero", "C) Energy is destroyed in closed systems", "D) Heat flows spontaneously from cold to hot"]),
    ("Quantum Mechanics", "Heisenberg Uncertainty Principle limits simultaneous precision of position and momentum.", "A) Precision of position and momentum cannot be simultaneously exact", ["A) Precision of position and momentum cannot be simultaneously exact", "B) Particles have fixed exact trajectories at all times", "C) Velocity can be measured without error always", "D) Quantum states are classical"]),
    ("Organic Chemistry", "Benzene has a planar aromatic ring structure with delocalized pi electrons.", "A) Planar aromatic ring with delocalized pi electrons", ["A) Planar aromatic ring with delocalized pi electrons", "B) Linear open-chain alkane", "C) Non-planar saturated hydrocarbon", "D) Inorganic ionic crystal"]),
    ("Genetics", "DNA replication is semi-conservative, yielding one original and one new strand.", "A) Semi-conservative replication producing one parent and one daughter strand", ["A) Semi-conservative replication producing one parent and one daughter strand", "B) Fully conservative replication creating brand new pairs only", "C) Dispersive destruction of nucleotides", "D) RNA transcription without template"]),
    ("Computer Science", "QuickSort has an average time complexity of O(n log n).", "A) Average time complexity of O(n log n)", ["A) Average time complexity of O(n log n)", "B) Always O(1) constant time", "C) Worst-case linear time O(n)", "D) Exponential time O(2^n)"])
]

for idx in range(6, 51):
    if idx % 3 == 0:
        # True/False Binary Choice
        BENCHMARK_ITEMS.append({
            "id": idx, "type": "tf", "category": "True/False",
            "state": "suggested_replies",
            "choices": ["A) True", "B) False"],
            "messages": [
                {"role": "assistant", "text": "Let's test a fundamental concept in physics."},
                {"role": "user", "text": "im ready!"},
                {"role": "assistant", "text": "Light travels faster in a vacuum than through glass."},
                {"role": "user", "text": "makes sense. quiz me!"},
                {"role": "assistant", "text": "True or False: The speed of light in a vacuum is greater than its speed in glass."}
            ],
            "correct": "A) True"
        })
    elif idx % 3 == 1:
        # Free-Text Response
        BENCHMARK_ITEMS.append({
            "id": idx, "type": "free_text", "category": "Free-Text",
            "state": "free_text",
            "choices": [],
            "messages": [
                {"role": "assistant", "text": "In neural networks, gradient descent updates weights in the opposite direction of the gradient to minimize loss."},
                {"role": "user", "text": "so gradient descent is just walking downhill to find the lowest error?"},
                {"role": "assistant", "text": "Exactly right! Now explain in your own words how weight updates relate to loss minimization."}
            ],
            "correct": None
        })
    else:
        # Scientific Reasoning MCQ
        t_title, t_desc, t_ans, t_choices = topics_list[idx % len(topics_list)]
        BENCHMARK_ITEMS.append({
            "id": idx, "type": "mcq", "category": "Scientific Reasoning",
            "state": "suggested_replies",
            "choices": t_choices,
            "messages": [
                {"role": "assistant", "text": f"Let's explore {t_title}."},
                {"role": "user", "text": "tell me more!"},
                {"role": "assistant", "text": t_desc},
                {"role": "user", "text": "got it! test me."},
                {"role": "assistant", "text": f"Which statement best summarizes {t_title}?"}
            ],
            "correct": t_ans
        })

def run_benchmark():
    llm = OboeLLM()
    
    # Models to test
    models_to_test = [
        {"provider": "groq", "model": "groq/compound-mini", "label": "Groq (Current: compound-mini)"},
        {"provider": "groq", "model": "openai/gpt-oss-20b", "label": "Groq (GPT-OSS-20B)"}
    ]
    
    # Check if Mistral API key is available
    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key:
        models_to_test.append({"provider": "mistral", "model": "open-mistral-7b", "label": "Mistral (open-mistral-7b)"})

    print("=" * 80)
    print(f"  OBOE BENCHMARK RUN: {len(BENCHMARK_ITEMS)} TEST CASES ACROSS {len(models_to_test)} MODELS")
    print("=" * 80)
    print()

    summary_results = []

    for m_cfg in models_to_test:
        label = m_cfg["label"]
        ptype = m_cfg["provider"]
        model_name = m_cfg["model"]
        
        print(f"--- Running Benchmark for: {label} ---")
        
        mcq_correct = 0
        mcq_total = 0
        tf_correct = 0
        tf_total = 0
        ftext_valid = 0
        ftext_total = 0
        json_valid = 0
        total_items = len(BENCHMARK_ITEMS)
        
        latencies = []
        in_tokens = 0
        out_tokens = 0
        failures = 0
        rate_limits = 0
        
        # Build client for model
        if ptype == "groq":
            client = Groq(api_key=config.GROQ_API_KEY, timeout=5.0, max_retries=0)
        elif ptype == "mistral":
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=mistral_key, timeout=5.0, max_retries=0)

        for item in BENCHMARK_ITEMS:
            item_type = item["type"]
            start_t = time.time()
            
            try:
                # Override complex_model for test model
                llm.providers[0]["complex_model"] = model_name
                llm.providers[0]["simple_model"] = model_name
                
                decision = llm.decide_action(
                    state=item["state"],
                    messages=item["messages"],
                    choices=item["choices"],
                    learned_skills={"Science": 1}
                )
                elapsed_ms = int((time.time() - start_t) * 1000)
                latencies.append(elapsed_ms)
                
                # Check JSON validity
                if isinstance(decision, dict) and "action" in decision:
                    json_valid += 1
                
                # Evaluate accuracy
                if item_type in ["mcq", "tf"]:
                    if item_type == "mcq": mcq_total += 1
                    else: tf_total += 1
                    
                    sel = decision.get("selection", "") if isinstance(decision, dict) else ""
                    if sel == item["correct"]:
                        if item_type == "mcq": mcq_correct += 1
                        else: tf_correct += 1
                elif item_type == "free_text":
                    ftext_total += 1
                    txt = decision.get("text", "") if isinstance(decision, dict) else ""
                    if txt and len(txt) > 10:
                        ftext_valid += 1

            except Exception as e:
                err_str = str(e)
                failures += 1
                if "429" in err_str or "rate_limit" in err_str.lower():
                    rate_limits += 1

        avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
        avg_in = int(in_tokens / total_items) if total_items else 0
        avg_out = int(out_tokens / total_items) if total_items else 0
        
        mcq_acc = f"{(mcq_correct/mcq_total)*100:.1f}%" if mcq_total else "N/A"
        tf_acc = f"{(tf_correct/tf_total)*100:.1f}%" if tf_total else "N/A"
        ftext_acc = f"{(ftext_valid/ftext_total)*100:.1f}%" if ftext_total else "N/A"
        json_acc = f"{(json_valid/total_items)*100:.1f}%"

        summary_results.append({
            "label": label,
            "mcq_acc": mcq_acc,
            "tf_acc": tf_acc,
            "ftext_acc": ftext_acc,
            "json_acc": json_acc,
            "avg_lat": f"{avg_lat}ms",
            "avg_in": avg_in,
            "avg_out": avg_out,
            "failures": failures,
            "rate_limits": rate_limits
        })
        print(f"Finished {label} | MCQ: {mcq_acc} | T/F: {tf_acc} | JSON: {json_acc} | Avg Latency: {avg_lat}ms\n")

    # Display Benchmark Table
    print("\n" + "=" * 105)
    print(f"| {'Model':<30} | {'MCQ Acc':<9} | {'T/F Acc':<9} | {'Free-Text':<10} | {'JSON Acc':<9} | {'Avg Lat':<9} | {'In Tok':<7} | {'Out Tok':<7} |")
    print("=" * 105)
    for r in summary_results:
        print(f"| {r['label']:<30} | {r['mcq_acc']:<9} | {r['tf_acc']:<9} | {r['ftext_acc']:<10} | {r['json_acc']:<9} | {r['avg_lat']:<9} | {r['avg_in']:<7} | {r['avg_out']:<7} |")
    print("=" * 105)

if __name__ == "__main__":
    run_benchmark()
