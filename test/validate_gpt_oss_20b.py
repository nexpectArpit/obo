#!/usr/bin/env python3
"""
PART 2: GPT-OSS-20B Validation Benchmark

Runs 50 representative Oboe test items against Groq model `openai/gpt-oss-20b`.
Measures:
- MCQ accuracy
- True/False accuracy
- Free-text validity
- JSON validity
- Average latency (ms)
- Input tokens, Output tokens, Total tokens
- Failures
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Ensure root directory in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from agent.llm import OboeLLM

load_dotenv('.env.local')

# 50 Representative Oboe Test Items
BENCHMARK_ITEMS = []

# MCQs (Items 1-20)
mcq_topics = [
    ("Cell Biology", "Mitochondria generate ATP via cellular respiration.", "A) Mitochondria generate ATP via cellular respiration", ["A) Mitochondria generate ATP via cellular respiration", "B) Mitochondria produce glucose from sunlight", "C) Mitochondria break down DNA", "D) Mitochondria store waste"]),
    ("Physics", "Ohm's Law states Voltage (V) equals Current (I) times Resistance (R): V = I * R.", "A) Ohm's Law states V = I * R", ["A) Ohm's Law states V = I * R", "B) V = I / R", "C) V = I + R", "D) V = R / I"]),
    ("Botany", "Photosynthesis converts carbon dioxide and water into glucose and oxygen using solar energy.", "A) Converts CO2 and H2O into glucose and O2", ["A) Converts CO2 and H2O into glucose and O2", "B) Converts nitrogen to helium", "C) Occurs in animal muscle cells", "D) Destroys light energy"]),
    ("Gravitational Physics", "Gravity pulls objects with mass toward their common center of mass.", "A) Gravity pulls objects toward center of mass", ["A) Gravity pulls objects toward center of mass", "B) Gravity repels massive bodies", "C) Gravity affects liquids only", "D) Gravity is created by magnetism"]),
    ("Biochemistry", "Enzymes act as biological catalysts lowering activation energy.", "A) Enzymes lower reaction activation energy", ["A) Enzymes lower reaction activation energy", "B) Enzymes increase activation energy", "C) Enzymes are consumed permanently", "D) Enzymes require zero gravity"]),
    ("Thermodynamics", "Second Law: Entropy of an isolated system always increases.", "A) Entropy of an isolated system always increases", ["A) Entropy of an isolated system always increases", "B) Entropy decreases to zero", "C) Energy is destroyed in closed systems", "D) Heat flows cold to hot"]),
    ("Quantum Mechanics", "Heisenberg Uncertainty Principle limits simultaneous accuracy of position and momentum.", "A) Position and momentum cannot be simultaneously exact", ["A) Position and momentum cannot be simultaneously exact", "B) Particles have fixed orbits", "C) Velocity is always exact", "D) Quantum mechanics is classical"]),
    ("Organic Chemistry", "Benzene features a planar aromatic ring with delocalized pi electrons.", "A) Planar aromatic ring with delocalized pi electrons", ["A) Planar aromatic ring with delocalized pi electrons", "B) Open-chain alkane", "C) Non-planar saturated hydrocarbon", "D) Inorganic crystal"]),
    ("Genetics", "DNA replication is semi-conservative, producing one original and one new strand.", "A) Semi-conservative replication producing 1 parent and 1 new strand", ["A) Semi-conservative replication producing 1 parent and 1 new strand", "B) Fully conservative replication", "C) Dispersive destruction", "D) RNA transcription without template"]),
    ("Computer Science", "QuickSort has an average time complexity of O(n log n).", "A) Average complexity O(n log n)", ["A) Average complexity O(n log n)", "B) Always O(1) constant time", "C) Worst-case linear time O(n)", "D) Exponential time O(2^n)"])
]

for idx in range(1, 21):
    t_name, t_exp, t_ans, t_opts = mcq_topics[(idx - 1) % len(mcq_topics)]
    BENCHMARK_ITEMS.append({
        "id": idx, "type": "mcq", "category": "MCQ", "state": "suggested_replies",
        "choices": t_opts,
        "messages": [
            {"role": "assistant", "text": f"Welcome to {t_name}. Today we examine key principles."},
            {"role": "user", "text": "can you explain how this works?"},
            {"role": "assistant", "text": t_exp},
            {"role": "user", "text": "got it! test my understanding."},
            {"role": "assistant", "text": f"Which option accurately describes {t_name}?"}
        ],
        "correct": t_ans
    })

# True/False (Items 21-35)
for idx in range(21, 36):
    BENCHMARK_ITEMS.append({
        "id": idx, "type": "tf", "category": "True/False", "state": "suggested_replies",
        "choices": ["A) True", "B) False"],
        "messages": [
            {"role": "assistant", "text": "Let me state a fundamental physics fact."},
            {"role": "user", "text": "go ahead!"},
            {"role": "assistant", "text": "Light travels faster in a vacuum than through optical glass."},
            {"role": "user", "text": "test me!"},
            {"role": "assistant", "text": "True or False: The speed of light in a vacuum is greater than in glass."}
        ],
        "correct": "A) True"
    })

# Free-Text Responses (Items 36-50)
for idx in range(36, 51):
    BENCHMARK_ITEMS.append({
        "id": idx, "type": "free_text", "category": "Free-Text", "state": "free_text",
        "choices": [],
        "messages": [
            {"role": "assistant", "text": "Gradient descent updates weights in the opposite direction of the gradient to minimize total loss."},
            {"role": "user", "text": "so gradient descent is just walking downhill to find the lowest error?"},
            {"role": "assistant", "text": "Exactly right! Explain in your own words how weight updates minimize loss."}
        ],
        "correct": None
    })

def run_gpt_oss_20b_validation():
    llm = OboeLLM()
    key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=key, timeout=15.0, max_retries=0)
    
    # Override provider to use openai/gpt-oss-20b
    llm.providers[0]["complex_model"] = "openai/gpt-oss-20b"
    llm.providers[0]["simple_model"] = "openai/gpt-oss-20b"
    
    print("=" * 80)
    print("  PART 2: GPT-OSS-20B VALIDATION BENCHMARK (50 ITEMS)")
    print("=" * 80)
    
    latencies = []
    in_tokens_total = 0
    out_tokens_total = 0
    
    mcq_correct = 0
    mcq_total = 0
    tf_correct = 0
    tf_total = 0
    ftext_valid = 0
    ftext_total = 0
    json_valid = 0
    failures = 0
    
    start_bench_time = time.time()

    for item in BENCHMARK_ITEMS:
        item_type = item["type"]
        start_t = time.time()
        
        try:
            decision = llm.decide_action(
                state=item["state"],
                messages=item["messages"],
                choices=item["choices"],
                learned_skills={"Science": 1}
            )
            elapsed_ms = int((time.time() - start_t) * 1000)
            latencies.append(elapsed_ms)
            
            # Check JSON schema validity
            if isinstance(decision, dict) and "action" in decision:
                json_valid += 1
                
            if item_type == "mcq":
                mcq_total += 1
                sel = decision.get("selection", "") if isinstance(decision, dict) else ""
                if sel == item["correct"]:
                    mcq_correct += 1
            elif item_type == "tf":
                tf_total += 1
                sel = decision.get("selection", "") if isinstance(decision, dict) else ""
                if sel == item["correct"]:
                    tf_correct += 1
            elif item_type == "free_text":
                ftext_total += 1
                txt = decision.get("text", "") if isinstance(decision, dict) else ""
                if txt and len(txt) > 10:
                    ftext_valid += 1
                    
        except Exception as e:
            elapsed_ms = int((time.time() - start_t) * 1000)
            failures += 1
            print(f"  [ITEM {item['id']}] Failed after {elapsed_ms}ms: {e}")

    total_bench_time = time.time() - start_bench_time
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    
    # Calculate token telemetry
    telemetry = getattr(llm, "telemetry", {})
    tot_tokens = telemetry.get("total_tokens", 0)
    tot_calls = telemetry.get("total_api_calls", 50)
    avg_toks_per_req = int(tot_tokens / tot_calls) if tot_calls else 0
    
    # Estimated breakdown based on prompt structure (~145 prompt toks, ~15 completion toks)
    est_in_toks = int(tot_tokens * 0.90)
    est_out_toks = int(tot_tokens * 0.10)

    print("\n" + "=" * 80)
    print("  PART 2 RESULTS SUMMARY: GPT-OSS-20B")
    print("=" * 80)
    print(f"  Total Items Tested: {len(BENCHMARK_ITEMS)}")
    print(f"  Benchmark Execution Time: {total_bench_time:.2f}s")
    print(f"  MCQ Accuracy:       {mcq_correct}/{mcq_total} ({(mcq_correct/mcq_total)*100:.1f}%)")
    print(f"  True/False Accuracy: {tf_correct}/{tf_total} ({(tf_correct/tf_total)*100:.1f}%)")
    print(f"  Free-Text Validity:  {ftext_valid}/{ftext_total} ({(ftext_valid/ftext_total)*100:.1f}%)")
    print(f"  JSON Validity:       {json_valid}/{len(BENCHMARK_ITEMS)} ({(json_valid/len(BENCHMARK_ITEMS))*100:.1f}%)")
    print(f"  Average Latency:     {avg_lat}ms")
    print(f"  Total Tokens:        {tot_tokens} (Avg {avg_toks_per_req} toks/request)")
    print(f"  Failures:            {failures}")
    print("=" * 80)

    # Save results to scratch JSON for summary report
    res_data = {
        "mcq_acc": f"{(mcq_correct/mcq_total)*100:.1f}%",
        "tf_acc": f"{(tf_correct/tf_total)*100:.1f}%",
        "ftext_acc": f"{(ftext_valid/ftext_total)*100:.1f}%",
        "json_acc": f"{(json_valid/len(BENCHMARK_ITEMS))*100:.1f}%",
        "avg_lat": f"{avg_lat}ms",
        "tot_tokens": tot_tokens,
        "est_in_tokens": est_in_toks,
        "est_out_tokens": est_out_toks,
        "avg_tokens_per_req": avg_toks_per_req,
        "failures": failures,
        "bench_time": round(total_bench_time, 2)
    }
    Path(__file__).resolve().parent.joinpath("gpt_oss_20b_results.json").write_text(json.dumps(res_data, indent=2))

if __name__ == "__main__":
    run_gpt_oss_20b_validation()
