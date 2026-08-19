#!/usr/bin/env python3
"""
Regression Test: Multi-Provider Quality & Latency Benchmark

Tests the exact Oboe system prompt, 5-message sliding window context, and JSON schema
against configured LLM providers (Groq, Cerebras, Nvidia) to verify:
1. JSON schema validity
2. Answer correctness / reasoning quality
3. Latency (ms)
4. Token usage
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure root workspace is in import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from llm import OboeLLM

# Sample real Oboe interaction context
SAMPLE_STATE = "suggested_replies"
SAMPLE_CHOICES = [
    "A) A higher temperature increases kinetic energy, causing more collisions per second.",
    "B) Temperature has no effect on molecular collision frequency.",
    "C) Lowering temperature speeds up gas particles.",
    "D) Gas particles stop moving entirely at 25 degrees Celsius."
]
SAMPLE_MESSAGES = [
    {"role": "assistant", "text": "Welcome to Chemical Kinetics! Today we are exploring reaction rates."},
    {"role": "user", "text": "sounds interesting! how does temperature affect how fast molecules react?"},
    {"role": "assistant", "text": "Great question! Temperature is directly related to the average kinetic energy of gas molecules. When temperature increases, molecules move faster, leading to significantly more frequent and higher-energy collisions per second."},
    {"role": "user", "text": "makes total sense! so heat basically speeds everything up. can you test me on this?"},
    {"role": "assistant", "text": "Let's check your understanding! Which statement correctly describes the relationship between temperature and molecular collisions?"}
]

def benchmark_providers():
    load_dotenv('.env.local')
    llm = OboeLLM()
    
    print("=" * 70)
    print("  OBOE MULTI-PROVIDER QUALITY & LATENCY BENCHMARK")
    print(f"  Configured Providers in Pool: {len(llm.providers)}")
    for idx, p in enumerate(llm.providers):
        print(f"    [{idx+1}] Type: {p['type']:<10} Model: {p['complex_model']}")
    print("=" * 70)
    print()

    results = []

    for idx, provider in enumerate(llm.providers):
        ptype = provider["type"]
        model = provider["complex_model"]
        masked_key = provider["api_key"][:8] + "..." if provider.get("api_key") else "N/A"
        
        print(f"Testing [{idx+1}/{len(llm.providers)}] Provider: {ptype.upper()} ({model}) Key: {masked_key}")
        
        llm.current_provider_idx = idx
        start_t = time.time()
        
        try:
            decision = llm.decide_action(
                state=SAMPLE_STATE,
                messages=SAMPLE_MESSAGES,
                choices=SAMPLE_CHOICES,
                learned_skills={"Chemistry": 1},
                target_skill="Reaction Kinetics",
                target_level=2
            )
            elapsed_ms = int((time.time() - start_t) * 1000)
            
            # Validate JSON Schema
            is_valid = isinstance(decision, dict) and decision.get("action") == "click" and decision.get("selection") in SAMPLE_CHOICES
            selected_option = decision.get("selection", "None")
            correct = selected_option.startswith("A)")
            
            status_icon = "✅ PASS" if (is_valid and correct) else "❌ FAIL"
            print(f"  {status_icon} Latency: {elapsed_ms}ms | Selection: '{selected_option[:40]}...'")
            print(f"  Thought: {decision.get('thought', '')[:80]}...\n")
            
            results.append({
                "provider": ptype,
                "model": model,
                "latency_ms": elapsed_ms,
                "valid": is_valid,
                "correct": correct,
                "decision": decision
            })
        except Exception as e:
            elapsed_ms = int((time.time() - start_t) * 1000)
            print(f"  ❌ FAIL (Error after {elapsed_ms}ms): {e}\n")
            results.append({
                "provider": ptype,
                "model": model,
                "latency_ms": elapsed_ms,
                "valid": False,
                "correct": False,
                "error": str(e)
            })

    print("=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)
    for r in results:
        status = "✅ PASS" if r["valid"] and r["correct"] else f"❌ FAIL ({r.get('error', 'Invalid Choice')})"
        print(f"  • {r['provider'].upper():<10} | Model: {r['model']:<30} | {r['latency_ms']}ms | {status}")
    print("=" * 70)

if __name__ == "__main__":
    benchmark_providers()
