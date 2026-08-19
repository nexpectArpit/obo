#!/usr/bin/env python3
"""
PHASE 9 LOCAL VERIFICATION TEST SUITE

Executes:
- Test A: Simple LLM request (Groq -> GPT-OSS-20B -> valid JSON)
- Test B: Real Oboe-style MCQ (5-message context + question + choices -> correct JSON)
- Test C: Free-text interaction
- Test D: Force/mock Groq failure (verifies failover to NVIDIA/Mistral)
- Test E: Force/mock Groq + NVIDIA failure (verifies failover to Mistral mistral-small-latest)
"""

import os
import sys
import json
import unittest
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from llm import OboeLLM

load_dotenv('.env.local')

class TestPhase9ProviderSuite(unittest.TestCase):

    def setUp(self):
        self.llm = OboeLLM()

    def test_A_simple_request(self):
        print("\n--- [TEST A] Simple LLM Request (Groq -> GPT-OSS-20B) ---")
        messages = [{"role": "user", "text": "What is 2 + 2?"}]
        choices = ["A) 4", "B) 5"]
        decision = self.llm.decide_action(
            state="suggested_replies",
            messages=messages,
            choices=choices
        )
        print("Test A Output:", decision)
        self.assertIsInstance(decision, dict)
        self.assertIn("action", decision)
        self.assertEqual(decision.get("selection"), "A) 4")

    def test_B_real_mcq(self):
        print("\n--- [TEST B] Real Oboe-Style MCQ ---")
        messages = [
            {"role": "assistant", "text": "Cell biology studies the cell as the fundamental unit of life."},
            {"role": "user", "text": "can you explain ATP production?"},
            {"role": "assistant", "text": "Mitochondria produce ATP via cellular respiration."},
            {"role": "user", "text": "got it! test me."},
            {"role": "assistant", "text": "Which organelle generates ATP?"}
        ]
        choices = [
            "A) Mitochondria produce ATP via cellular respiration",
            "B) Ribosomes manufacture lipids",
            "C) Nucleus destroys energy",
            "D) Lysosome converts light"
        ]
        decision = self.llm.decide_action(
            state="suggested_replies",
            messages=messages,
            choices=choices,
            learned_skills={"Biology": 1}
        )
        print("Test B Output:", decision)
        self.assertIsInstance(decision, dict)
        self.assertEqual(decision.get("selection"), "A) Mitochondria produce ATP via cellular respiration")

    def test_C_free_text(self):
        print("\n--- [TEST C] Free-Text Interaction ---")
        messages = [
            {"role": "assistant", "text": "Gradient descent updates weights in the opposite direction of the gradient to minimize total loss."},
            {"role": "user", "text": "so gradient descent is just walking downhill to find the lowest error?"},
            {"role": "assistant", "text": "Exactly right! Explain in your own words how weight updates minimize loss."}
        ]
        decision = self.llm.decide_action(
            state="free_text",
            messages=messages,
            choices=[]
        )
        print("Test C Output:", decision)
        self.assertIsInstance(decision, dict)
        self.assertEqual(decision.get("action"), "type")
        self.assertTrue(len(decision.get("text", "")) > 10)

    def test_D_mock_groq_failure_triggers_nvidia_or_mistral(self):
        print("\n--- [TEST D] Force Groq Failure -> Verify Failover to Secondary/Fallback ---")
        llm_failover = OboeLLM()
        for p in llm_failover.providers:
            if p["type"] == "groq":
                p["api_key"] = "gsk_invalid_mock_key_for_testing"

        messages = [{"role": "user", "text": "Test failover from Groq"}]
        choices = ["A) True", "B) False"]
        
        decision = llm_failover.decide_action(
            state="suggested_replies",
            messages=messages,
            choices=choices
        )
        print("Test D Output:", decision)
        print("Telemetry after Test D:", llm_failover.telemetry)
        self.assertIsInstance(decision, dict)
        provs = llm_failover.telemetry["providers"]
        self.assertTrue("nvidia" in provs or "mistral" in provs)

    def test_E_mock_groq_and_nvidia_failure_triggers_mistral(self):
        print("\n--- [TEST E] Force Groq + NVIDIA Failure -> Verify Mistral Selection ---")
        llm_failover = OboeLLM()
        for p in llm_failover.providers:
            if p["type"] in ["groq", "nvidia"]:
                p["api_key"] = "invalid_mock_key_for_testing"

        messages = [{"role": "user", "text": "Test failover to Mistral"}]
        choices = ["A) True", "B) False"]
        
        decision = llm_failover.decide_action(
            state="suggested_replies",
            messages=messages,
            choices=choices
        )
        print("Test E Output:", decision)
        print("Telemetry after Test E:", llm_failover.telemetry)
        self.assertIsInstance(decision, dict)
        self.assertIn("mistral", llm_failover.telemetry["providers"])

if __name__ == "__main__":
    unittest.main()
