#!/usr/bin/env python3
"""
PART 4 & PART 5: Request Pacing & Rate-Limit Telemetry Experiment

Compares:
1. Baseline Pacing: MIN_DELAY = 1s, MAX_DELAY = 9s (Average 5s)
2. Experimental Pacing: MIN_DELAY = 7s, MAX_DELAY = 20s (Average 13.5s)

Executes 20 real requests per pacing configuration using model `openai/gpt-oss-20b`.
Captures actual timestamps, calls/min, tokens/min, avg tokens/req, peak tokens/min, 429 errors, and session duration.
"""

import os
import sys
import time
import json
import random
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Ensure root workspace in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from agent.llm import OboeLLM

load_dotenv('.env.local')

SAMPLE_MESSAGES = [
    {"role": "assistant", "text": "In chemical kinetics, reaction rate increases with concentration due to higher collision frequency."},
    {"role": "user", "text": "makes sense! can you test me on this topic?"}
]
SAMPLE_CHOICES = [
    "A) Higher concentration increases collision frequency and reaction rate",
    "B) Concentration has no impact on collision frequency",
    "C) Lowering concentration speeds up reactions",
    "D) Concentration only affects gases at absolute zero"
]

def run_pacing_test(min_delay, max_delay, num_calls=15):
    llm = OboeLLM()
    key = os.getenv("GROQ_API_KEY")
    client = Groq(api_key=key, timeout=15.0, max_retries=0)
    
    llm.providers[0]["complex_model"] = "openai/gpt-oss-20b"
    llm.providers[0]["simple_model"] = "openai/gpt-oss-20b"
    
    print(f"\n--- Testing Pacing Config: MIN={min_delay}s, MAX={max_delay}s ({num_calls} calls) ---")
    
    start_session_time = time.time()
    telemetry_logs = []
    errors_429 = 0
    total_tokens_session = 0
    
    for i in range(num_calls):
        # Simulate pacing delay before request (except first request)
        delay_sec = 0
        if i > 0:
            delay_sec = round(random.uniform(min_delay, max_delay), 2)
            time.sleep(delay_sec)
            
        req_start = time.time()
        status_code = 200
        error_msg = None
        toks = 0
        
        try:
            decision = llm.decide_action(
                state="suggested_replies",
                messages=SAMPLE_MESSAGES,
                choices=SAMPLE_CHOICES,
                learned_skills={"Chemistry": 1}
            )
            req_latency = int((time.time() - req_start) * 1000)
            
            # Telemetry token tracking
            tele = getattr(llm, "telemetry", {})
            toks = tele.get("total_tokens", 0) - total_tokens_session
            total_tokens_session = tele.get("total_tokens", 0)
            
        except Exception as e:
            req_latency = int((time.time() - req_start) * 1000)
            error_msg = str(e)
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                status_code = 429
                errors_429 += 1
            else:
                status_code = 500

        telemetry_logs.append({
            "call_index": i + 1,
            "timestamp": time.strftime("%H:%M:%S", time.localtime(req_start)),
            "delay_before_req_sec": delay_sec,
            "latency_ms": req_latency,
            "tokens": toks,
            "status_code": status_code,
            "error": error_msg
        })
        print(f"  Call [{i+1}/{num_calls}] Delay: {delay_sec}s | Latency: {req_latency}ms | Status: {status_code} | Toks: {toks}")

    total_session_duration = round(time.time() - start_session_time, 2)
    session_minutes = max(0.01, total_session_duration / 60.0)
    
    calls_per_min = round(num_calls / session_minutes, 2)
    tokens_per_min = round(total_tokens_session / session_minutes, 2)
    avg_tokens_per_req = round(total_tokens_session / max(1, num_calls), 2)
    
    results = {
        "pacing_config": f"{min_delay}-{max_delay}s",
        "num_calls": num_calls,
        "session_duration_sec": total_session_duration,
        "calls_per_minute": calls_per_min,
        "tokens_per_minute": tokens_per_min,
        "avg_tokens_per_req": avg_tokens_per_req,
        "total_tokens_session": total_tokens_session,
        "errors_429": errors_429,
        "telemetry_logs": telemetry_logs
    }
    return results

def run_pacing_experiment():
    print("=" * 80)
    print("  PART 4 & 5: PACING & TOKEN TELEMETRY EXPERIMENT")
    print("=" * 80)
    
    # Run Baseline (1-9s)
    baseline_res = run_pacing_test(min_delay=1, max_delay=9, num_calls=12)
    
    # Run Experiment (7-20s)
    exp_res = run_pacing_test(min_delay=7, max_delay=20, num_calls=12)
    
    print("\n" + "=" * 85)
    print("  PACING EXPERIMENT TELEMETRY COMPARISON")
    print("=" * 85)
    print(f"| {'Metric':<30} | {'Baseline (1-9s)':<22} | {'Experiment (7-20s)':<22} |")
    print("-" * 85)
    print(f"| {'Session Duration':<30} | {baseline_res['session_duration_sec']}s{'':<18} | {exp_res['session_duration_sec']}s{'':<18} |")
    print(f"| {'Actual Calls/Min':<30} | {baseline_res['calls_per_minute']}{'':<18} | {exp_res['calls_per_minute']}{'':<18} |")
    print(f"| {'Actual Tokens/Min':<30} | {baseline_res['tokens_per_minute']}{'':<18} | {exp_res['tokens_per_minute']}{'':<18} |")
    print(f"| {'Avg Tokens/Request':<30} | {baseline_res['avg_tokens_per_req']}{'':<18} | {exp_res['avg_tokens_per_req']}{'':<18} |")
    print(f"| {'Total Session Tokens':<30} | {baseline_res['total_tokens_session']}{'':<18} | {exp_res['total_tokens_session']}{'':<18} |")
    print(f"| {'429 Rate Limit Errors':<30} | {baseline_res['errors_429']}{'':<18} | {exp_res['errors_429']}{'':<18} |")
    print("=" * 85)

    # Save to scratch json
    out_path = Path(__file__).resolve().parent / "pacing_experiment_results.json"
    out_path.write_text(json.dumps({"baseline": baseline_res, "experiment": exp_res}, indent=2))

if __name__ == "__main__":
    run_pacing_experiment()
