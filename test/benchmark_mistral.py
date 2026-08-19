#!/usr/bin/env python3
"""
MISTRAL-SMALL-LATEST BENCHMARK (50 TEST CASES)

Tests model `mistral-small-latest` on the same 50 Oboe benchmark test items.
Measures:
- MCQ accuracy
- True/False accuracy
- Free-text validity
- JSON schema validity
- Average latency
- Token consumption
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from llm import OboeLLM
from validate_gpt_oss_20b import BENCHMARK_ITEMS

load_dotenv('.env.local')

def run_mistral_benchmark():
    llm = OboeLLM()
    
    # Force provider pool to use Mistral mistral-small-latest
    mistral_keys = config.MISTRAL_API_KEYS if config.MISTRAL_API_KEYS else [os.getenv("MISTRAL_API_KEY")]
    llm.providers = [{
        "type": "mistral",
        "api_key": k,
        "complex_model": "mistral-small-latest",
        "simple_model": "mistral-small-latest"
    } for k in mistral_keys]
    
    print("=" * 80)
    print("  MISTRAL BENCHMARK RUN: mistral-small-latest (50 TEST CASES)")
    print("=" * 80)
    
    latencies = []
    mcq_correct = 0
    mcq_total = 0
    tf_correct = 0
    tf_total = 0
    ftext_valid = 0
    ftext_total = 0
    json_valid = 0
    failures = 0
    
    start_bench = time.time()
    
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

    total_bench_time = time.time() - start_bench
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    
    telemetry = getattr(llm, "telemetry", {})
    tot_tokens = telemetry.get("total_tokens", 0)
    
    print("\n" + "=" * 80)
    print("  MISTRAL-SMALL-LATEST BENCHMARK RESULTS")
    print("=" * 80)
    print(f"  Total Items Tested:  {len(BENCHMARK_ITEMS)}")
    print(f"  Execution Time:      {total_bench_time:.2f}s")
    print(f"  MCQ Accuracy:        {mcq_correct}/{mcq_total} ({(mcq_correct/mcq_total)*100:.1f}%)")
    print(f"  True/False Accuracy:  {tf_correct}/{tf_total} ({(tf_correct/tf_total)*100:.1f}%)")
    print(f"  Free-Text Validity:   {ftext_valid}/{ftext_total} ({(ftext_valid/ftext_total)*100:.1f}%)")
    print(f"  JSON Schema Validity: {json_valid}/{len(BENCHMARK_ITEMS)} ({(json_valid/len(BENCHMARK_ITEMS))*100:.1f}%)")
    print(f"  Average Latency:      {avg_lat}ms")
    print(f"  Total Tokens:         {tot_tokens}")
    print(f"  Failures:             {failures}")
    print("=" * 80)
    
    out_path = Path(__file__).resolve().parent / "mistral_benchmark_results.json"
    out_path.write_text(json.dumps({
        "model": "mistral-small-latest",
        "mcq_acc": f"{(mcq_correct/mcq_total)*100:.1f}%",
        "tf_acc": f"{(tf_correct/tf_total)*100:.1f}%",
        "ftext_acc": f"{(ftext_valid/ftext_total)*100:.1f}%",
        "json_acc": f"{(json_valid/len(BENCHMARK_ITEMS))*100:.1f}%",
        "avg_latency": f"{avg_lat}ms",
        "failures": failures
    }, indent=2))

if __name__ == "__main__":
    run_mistral_benchmark()
