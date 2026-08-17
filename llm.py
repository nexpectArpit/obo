import os
import json
from pathlib import Path
from groq import Groq
from openai import OpenAI
import config

class OboeLLM:
    def __init__(self):
        # Build the unified provider pool
        self.providers = []
        
        # Load Groq keys
        for key in config.GROQ_API_KEYS:
            self.providers.append({
                "type": "groq",
                "api_key": key,
                "complex_model": "groq/compound-mini",
                "simple_model": "groq/compound-mini"
            })
            
        # Load Nvidia keys
        for key in config.NVIDIA_API_KEYS:
            self.providers.append({
                "type": "nvidia",
                "api_key": key,
                "complex_model": "nvidia/nemotron-3-super-120b-a12b",
                "simple_model": "meta/llama-3.1-8b-instruct"
            })
            
        self.current_provider_idx = 0
        if not self.providers:
            print("[WARNING] No Groq or Nvidia API Keys configured.")
            
        self.rules = self._load_rules()

    def _load_rules(self):
        """Load stealth and behavioral rules from agent_rules.txt."""
        rules_path = Path(__file__).resolve().parent / "agent_rules.txt"
        if rules_path.exists():
            with open(rules_path, "r") as f:
                return f.read()
        return "Always act like a human learner. Never reveal you are an AI/bot."

    def _get_client_for_provider(self, provider):
        """Returns the appropriate client instance for a given provider."""
        if provider["type"] == "groq":
            return Groq(api_key=provider["api_key"])
        elif provider["type"] == "nvidia":
            return OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=provider["api_key"]
            )
        return None

    def _parse_json_response(self, text):
        """Safely extracts and parses JSON block from plain text response."""
        text = text.strip()
        if "```json" in text:
            try:
                parts = text.split("```json", 1)[1].split("```", 1)
                text = parts[0].strip()
            except Exception:
                pass
        elif "```" in text:
            try:
                parts = text.split("```", 1)[1].split("```", 1)
                text = parts[0].strip()
            except Exception:
                pass
        return json.loads(text)

    def decide_action(self, state, messages, choices, learned_skills=None):
        """Phase 5: LLM Integration.
        Makes a structured decision on how to respond based on the conversation state.
        Supports automatic rotation across all configured Groq & Nvidia API keys on rate limit.
        """
        # Format the skill-level profile context
        skills_context = ""
        if learned_skills:
            skills_context = "\nLearner's current achieved skill levels:\n"
            for skill, level in learned_skills.items():
                skills_context += f"- {skill}: Level {level}\n"

        system_prompt = f"""You are a human user participating in an interactive learning course on the website Oboe.com.
Your goal is to learn the topic, answer questions correctly, and gain skill points.

CRITICAL IDENTITY RULES:
{self.rules}
{skills_context}
Current page state: {state}

INSTRUCTIONS FOR SELECTING THE CORRECT OPTION (suggested_replies):
1. **Analyze Every Option:** You must carefully read and evaluate each choice in `choices`.
2. **Match with Chat History & Skill Profile:** Look at the recent dialogue history and your current skill levels. The correct answer is almost always explicitly explained, defined, or heavily hinted at in the preceding messages. Find the option that directly matches the facts, terms, or mechanisms explained in the chat.
3. **Plausibility Check:** Reject options that contain scientific contradictions, physical impossibilities, or absurd claims (e.g., exceeding the Carnot efficiency limit, physical melting of solid carbon, etc.).
4. **Step-by-Step Reasoning:** In the "thought" field, write down your step-by-step reasoning explaining why you eliminated the incorrect choices and why your selected choice is the scientifically and contextually correct one.

INSTRUCTIONS FOR WRITING FREE TEXT RESPONSES (free_text):
1. **Demonstrate Comprehension via Rephrasing/Summary:** Look at Oboe's latest message in the dialogue history. Summarize/rephrase the core technical concept Oboe explained in simple, intuitive, human-like terms (using simplified analogies or conceptual terms). This triggers Oboe's understanding check and awards immediate skill points and levels.
2. **Encourage/Ask to Test:** After summarizing, add a natural, encouraging follow-up question or explicitly ask Oboe to test you on it to advance the lesson (e.g., "makes total sense! can you ask me a question on this to see if I got it?").
3. **Conversational Styling:** Maintain your student persona. Write informally with lowercase text, brief sentences, and occasional natural minor typos, matching your profile rules (e.g., "so basically we can say a parameter is just like a multiplier... right? that's so cool. can you ask me a question to test my understanding?").

You must respond in JSON format matching one of the following schemas:

If state is 'suggested_replies':
{{
  "thought": "Step-by-step analysis of each option, matching facts to the chat history, and eliminating incorrect choices.",
  "action": "click",
  "selection": "The exact string of the option button to click (MUST match one of the choices exactly)"
}}

If state is 'free_text':
{{
  "thought": "Your reasoning process behind what to write",
  "action": "type",
  "text": "Your human-like text response to send"
}}

Do NOT output any conversational text or explanation outside the JSON. Return only a valid JSON object."""

        # Prepare messages content for LLM
        prompt_messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add conversation history (sliding window of last 5 messages to optimize tokens)
        history_str = ""
        recent_messages = messages[-5:]
        if len(messages) > 5:
            history_str += "... (older messages truncated) ...\n\n"
        for msg in recent_messages:
            role = "Oboe Platform" if msg["role"] == "assistant" else "You (Learner)"
            history_str += f"{role}: {msg['text']}\n\n"

        prompt_messages.append({
            "role": "user",
            "content": f"Here is the recent dialogue history:\n\n{history_str}\nAvailable choices: {choices if choices else 'None'}"
        })

        attempts = 0
        max_attempts = len(self.providers)
        while attempts < max_attempts:
            provider = self.providers[self.current_provider_idx]
            client = self._get_client_for_provider(provider)
            if not client:
                break
                
            # Select model dynamically based on request type
            selected_model = provider["complex_model"] if state == "suggested_replies" else provider["simple_model"]
            print(f"[LLM] Selecting provider: '{provider['type']}' with model: '{selected_model}' for state: '{state}'")

            try:
                if provider["type"] == "groq":
                    response = client.chat.completions.create(
                        model=selected_model,
                        messages=prompt_messages,
                        response_format={"type": "json_object"},
                        temperature=0.7
                    )
                    raw_content = response.choices[0].message.content
                    result = json.loads(raw_content)
                elif provider["type"] == "nvidia":
                    # Pass thinking traces arguments only for the Nemotron 120B model
                    extra_kwargs = {}
                    if "nemotron-3-super" in selected_model:
                        extra_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
                        extra_kwargs["max_tokens"] = 4096
                    else:
                        extra_kwargs["max_tokens"] = 1024

                    response = client.chat.completions.create(
                        model=selected_model,
                        messages=prompt_messages,
                        temperature=0.7,
                        **extra_kwargs
                    )
                    raw_content = response.choices[0].message.content
                    
                    # Log thinking if present in response metadata/reasoning
                    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
                    if reasoning:
                        print(f"\n[NVIDIA Thinking Trace]\n{reasoning}\n")
                    result = self._parse_json_response(raw_content)
                
                print(f"\n[LLM Decision] {result.get('thought')}")
                return result
                
            except Exception as e:
                err_str = str(e)
                print(f"[WARNING] Provider '{provider['type']}' failed: {e}")
                
                # Check for rate limit or similar error to trigger rotation
                if "rate_limit" in err_str.lower() or "429" in err_str or "limit exceeded" in err_str.lower():
                    attempts += 1
                    if attempts < max_attempts:
                        self.current_provider_idx = (self.current_provider_idx + 1) % len(self.providers)
                        next_prov = self.providers[self.current_provider_idx]
                        masked_key = next_prov["api_key"][:8] + "..." + next_prov["api_key"][-4:] if len(next_prov["api_key"]) > 12 else "..."
                        print(f"[INFO] Rotating to provider: '{next_prov['type']}' with Key ({masked_key})...")
                        continue
                break

        # Safe fallback response
        if state == "suggested_replies" and choices:
            return {"action": "click", "selection": choices[0], "thought": "Fallback to first choice due to API error"}
        return {"action": "type", "text": "I'm interested to learn more about this.", "thought": "Fallback response"}

    def generate_related_topics(self, topic, skills):
        """Generates 3 new, related, advanced topics to add to topics.json."""
        if not self.providers:
            return []

        system_prompt = (
            "You are a strategic curriculum assistant for Oboe.com. Your goal is to design related topics that are guaranteed to map to Oboe's internal skill categories.\n"
            "Oboe maps topic titles to skills based on strong keyword associations. You must design the topic title text carefully:\n"
            "- If targeting the math 'Topology' skill, use pure math terms like: 'homotopies', 'cohomology groups', 'differential manifolds', or 'algebraic topology'. Do NOT use physics terms like 'insulator', 'semiconductor', or 'matter' as Oboe maps those to 'Topological Insulators' or 'Condensed Matter Physics' instead.\n"
            "- If targeting 'Memory Systems', use memory hardware terms: 'HBM3e cache hierarchies', 'SRAM register files', or 'scratchpad allocation'.\n"
            "- If targeting 'AI Hardware Acceleration', use silicon architecture terms: 'wafer-scale 2D mesh routing', 'systolic arrays', or 'LPU accelerators'.\n"
            "- If targeting 'Fault-Tolerant Systems', use resilience terms: 'byzantine fault tolerance', 'consensus protocols', or 'state machine replication'.\n\n"
            "Return only a valid JSON object matching this schema:\n"
            "{\n"
            "  \"topics\": [\n"
            "    {\n"
            "      \"topic\": \"The strategically crafted title of the topic\",\n"
            "      \"associated_skill\": \"Name of the target skill (must match the spelling of one of the learner's skills exactly)\",\n"
            "      \"level_target\": 4\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        # Convert skills to readable summary
        skills_str = ", ".join([f"{k} (current level: {v})" for k, v in skills.items()])
        user_prompt = f"""The student has successfully completed the course on '{topic}'.
Their current highest achieved levels for relevant skills are: {skills_str}.

Generate 3 new, highly related, advanced, but distinct topic titles for future Oboe.com courses that will test and advance the learner from their current levels.
Strategically align the topic titles with the target skills using keyword associations to trigger Oboe's correct categorizations.
Do NOT repeat the completed topic itself. Output only a JSON object containing the list of these 3 topic objects matching the specified schema."""

        prompt_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        attempts = 0
        max_attempts = len(self.providers)
        while attempts < max_attempts:
            provider = self.providers[self.current_provider_idx]
            client = self._get_client_for_provider(provider)
            if not client:
                break
                
            selected_model = provider["simple_model"]
            try:
                if provider["type"] == "groq":
                    response = client.chat.completions.create(
                        model=selected_model,
                        messages=prompt_messages,
                        response_format={"type": "json_object"},
                        temperature=0.7
                    )
                    raw_content = response.choices[0].message.content
                    result = json.loads(raw_content)
                elif provider["type"] == "nvidia":
                    response = client.chat.completions.create(
                        model=selected_model,
                        messages=prompt_messages,
                        temperature=0.7,
                        max_tokens=1024
                    )
                    raw_content = response.choices[0].message.content
                    result = self._parse_json_response(raw_content)
                    
                topics = result.get("topics", [])
                print(f"[LLM Related Topics] Generated: {topics}")
                return topics
            except Exception as e:
                err_str = str(e)
                print(f"[WARNING] Provider '{provider['type']}' failed in generating topics: {e}")
                if "rate_limit" in err_str.lower() or "429" in err_str or "limit exceeded" in err_str.lower():
                    attempts += 1
                    if attempts < max_attempts:
                        self.current_provider_idx = (self.current_provider_idx + 1) % len(self.providers)
                        continue
                break
        return []
