import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from unittest.mock import patch, MagicMock
from llm import OboeLLM

class TestAdaptiveSteering(unittest.TestCase):
    def setUp(self):
        self.llm = OboeLLM()

    @patch('llm.Groq')
    def test_system_prompt_steering_injection(self, mock_groq):
        """Verify that system_prompt correctly injects the semantic focus directive for target_skills."""
        # Setup mock client and response
        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"thought": "test", "action": "type", "text": "implied dsa response"}'
        mock_client.chat.completions.create.return_value = mock_response

        messages = [{"role": "assistant", "text": "How do you optimize range minimum queries?"}]
        choices = []

        # We pass target_skills as ['Dynamic Programming', 'Algorithms']
        self.llm.decide_action(
            state="free_text",
            messages=messages,
            choices=choices,
            target_skills=["Dynamic Programming", "Algorithms"]
        )

        # Inspect the arguments passed to chat.completions.create
        called_args = mock_client.chat.completions.create.call_args[1]
        system_msg = called_args["messages"][0]["content"]

        # Assertions
        self.assertIn("SEMANTIC FOCUS DIRECTIVE", system_msg)
        self.assertIn("Dynamic Programming", system_msg)
        self.assertIn("Algorithms", system_msg)
        self.assertIn("Do NOT explicitly mention the names of these target skills", system_msg)

    def test_live_adaptive_response(self):
        """Execute a live LLM request with target_skills and verify that the response is valid and steered."""
        # Using live provider
        messages = [{"role": "assistant", "text": "Explain how you would solve range minimum query with updates."}]
        choices = []
        target_skills = ["Dynamic Programming", "Algorithms"]

        print("\n--- [TEST] Live LLM Response with Adaptive Steering ---")
        try:
            result = self.llm.decide_action(
                state="free_text",
                messages=messages,
                choices=choices,
                target_skills=target_skills
            )
            print(f"Steering Input: {target_skills}")
            print(f"LLM Response Thought: {result.get('thought')}")
            print(f"LLM Response Text: {result.get('text')}")

            self.assertIn("action", result)
            self.assertEqual(result["action"], "type")
            self.assertIn("text", result)
            self.assertTrue(len(result["text"]) > 10)
            
            # Ensure the response is styled like a human and doesn't explicitly name the skills
            self.assertNotIn("Dynamic Programming", result["text"])
            self.assertNotIn("Algorithms", result["text"])
            print("--- [TEST] Live LLM Response Pass ---\n")
        except Exception as e:
            self.fail(f"Live LLM request failed: {e}")

if __name__ == "__main__":
    unittest.main()
