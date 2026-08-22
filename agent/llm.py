import os
import json
from pathlib import Path
from groq import Groq
from openai import OpenAI
import config

class OboeLLM:
    def __init__(self):
        # Build the unified provider pool with failover: Groq -> NVIDIA -> Mistral
        self.providers = []
        
        # 1. Primary: Groq (GPT-OSS-20B)
        for key in config.GROQ_API_KEYS:
            self.providers.append({
                "type": "groq",
                "api_key": key,
                "complex_model": "openai/gpt-oss-20b",
                "simple_model": "openai/gpt-oss-20b"
            })

        # 2. Secondary: Nvidia
        for key in config.NVIDIA_API_KEYS:
            self.providers.append({
                "type": "nvidia",
                "api_key": key,
                "complex_model": "meta/llama-3.1-8b-instruct",
                "simple_model": "meta/llama-3.1-8b-instruct"
            })

        # 3. Fallback: Mistral (mistral-small-latest)
        for key in config.MISTRAL_API_KEYS:
            self.providers.append({
                "type": "mistral",
                "api_key": key,
                "complex_model": "mistral-small-latest",
                "simple_model": "mistral-small-latest"
            })
            
        self.current_provider_idx = 0
        if not self.providers:
            print("[WARNING] No Groq, Nvidia, or Mistral API Keys configured.")
            
        # Telemetry tracking (compact aggregate counters)
        self.telemetry = {
            "total_api_calls": 0,
            "total_tokens": 0,
            "providers": {}
        }
        self.rules = self._load_rules()

    def _load_rules(self):
        """Load stealth and behavioral rules from agent_rules.txt."""
        rules_path = Path(__file__).resolve().parent.parent / "agent_rules.txt"
        if rules_path.exists():
            with open(rules_path, "r") as f:
                return f.read()
        return "Always act like a human learner. Never reveal you are an AI/bot."

    def _get_client_for_provider(self, provider):
        """Returns the appropriate client instance for a given provider with configurable timeout."""
        ptype = provider["type"]
        timeout_val = config.PROVIDER_TIMEOUTS.get(ptype, 15.0)
        
        if ptype == "groq":
            return Groq(api_key=provider["api_key"], timeout=timeout_val)
        elif ptype == "mistral":
            return OpenAI(
                base_url="https://api.mistral.ai/v1",
                api_key=provider["api_key"],
                timeout=timeout_val
            )
        elif ptype == "nvidia":
            return OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=provider["api_key"],
                timeout=timeout_val
            )
        return None

    def _sanitize_human_text(self, text):
        if not isinstance(text, str):
            return text
        # Replace em-dashes, en-dashes, and double hyphens with simple natural commas/periods
        return text.replace("—", ", ").replace("–", ", ").replace("--", ", ")

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
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "text" in parsed and isinstance(parsed["text"], str):
            parsed["text"] = self._sanitize_human_text(parsed["text"])
        return parsed


    def decide_action(self, state, messages, choices, learned_skills=None, target_skill=None, target_level=None, target_skills=None):
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
                
        target_context = ""
        if target_skill and target_level:
            target_context = f"\nPRIMARY DIRECTIVE: Your objective for this session is to demonstrate mastery of the '{target_skill}' skill at Level {target_level}.\nSteer the conversation and formulate responses that show your depth of knowledge in this area. If writing free_text, make sure to request/prompt for advanced concepts or complex math related to this topic in a natural, curious human way.\n"

        if target_skills:
            target_context += f"\nSEMANTIC FOCUS DIRECTIVE: Shape the vocabulary, mathematical concepts, and reasoning style of your response to implicitly demonstrate depth in the following target areas: {', '.join(target_skills)}.\nDo NOT explicitly mention the names of these target skills in your response. Instead, naturally steer explanations to cover domains, trade-offs, and complexities characteristic of these skills.\n"

        system_prompt = f"""You are a human user participating in an interactive learning course on the website Oboe.com.
Your goal is to learn the topic, answer questions correctly, and gain skill points.

CRITICAL IDENTITY RULES:
{self.rules}
{skills_context}
{target_context}
Current page state: {state}

INSTRUCTIONS FOR SELECTING THE CORRECT OPTION (suggested_replies):
1. **Analyze Every Option:** You must carefully read and evaluate each choice in `choices`.
2. **Match with Chat History & Skill Profile:** Look at the recent dialogue history and your current skill levels. The correct answer is almost always explicitly explained, defined, or heavily hinted at in the preceding messages. Find the option that directly matches the facts, terms, or mechanisms explained in the chat.
3. **Plausibility Check:** Reject options that contain scientific contradictions, physical impossibilities, or absurd claims (e.g., exceeding the Carnot efficiency limit, physical melting of solid carbon, etc.).
4. **Step-by-Step Reasoning:** In the "thought" field, write down your step-by-step reasoning explaining why you eliminated the incorrect choices and why your selected choice is the scientifically and contextually correct one.

INSTRUCTIONS FOR WRITING FREE TEXT RESPONSES (free_text):
1. **Deep Conceptual Summary (Triggers Oboe's High-Value Points)**:
   Do NOT give a superficial summary. Briefly demonstrate deep understanding by touching upon:
   - Creator Motivation / Problem Intuition (Why was this approach invented? What original flaw did it solve?)
   - Edge Cases & Failure Modes (Where does it break or run into edge test cases?)
   - Alternative Trade-offs (Why choose this over competing approaches?)
2. **Context-Aware Follow-Up**: 
   - If Oboe's latest message ALREADY ends with a question or test prompt, answer/rephrase it directly with technical precision. Do NOT append "can you ask me a question to test me?" when Oboe has already asked one.
   - If Oboe's latest message did NOT ask a question, ask Oboe to test you on a specific edge case or trade-off (e.g., "makes total sense... can you test me on how this handles edge test cases?").
3. **Conversational Styling, Pauses & Typos:** Maintain your student persona. Write informally with casual lowercase/plain text, brief sentences, natural pauses (`...`), and occasional realistic minor typos (e.g., "realy", "so basicly...", "got it..."). NEVER use em-dashes (`—` or `--`), bullet points, or AI-style formal punctuation. Write like a real student quickly typing in a chat window.




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
                if provider["type"] in ["groq", "mistral"]:
                    kwargs = {
                        "model": selected_model,
                        "messages": prompt_messages,
                        "temperature": 0.7
                    }
                    if provider["type"] == "groq":
                        kwargs["response_format"] = {"type": "json_object"}
                    
                    response = client.chat.completions.create(**kwargs)
                    raw_content = response.choices[0].message.content
                    result = self._parse_json_response(raw_content)
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

                # Record compact aggregate telemetry
                usage = getattr(response, "usage", None)
                tot_toks = getattr(usage, "total_tokens", 0) if usage else 0
                ptype = provider["type"]
                self.telemetry["total_api_calls"] += 1
                self.telemetry["total_tokens"] += tot_toks
                if ptype not in self.telemetry["providers"]:
                    self.telemetry["providers"][ptype] = {"calls": 0, "tokens": 0}
                self.telemetry["providers"][ptype]["calls"] += 1
                self.telemetry["providers"][ptype]["tokens"] += tot_toks
                
                print(f"\n[LLM Decision] {result.get('thought')}")
                return result
                
            except Exception as e:
                err_str = str(e)
                print(f"[WARNING] Provider '{provider['type']}' failed: {e}")
                
                # Trigger failover on ANY exception to guarantee session continuation
                attempts += 1
                if attempts < max_attempts:
                    self.current_provider_idx = (self.current_provider_idx + 1) % len(self.providers)
                    next_prov = self.providers[self.current_provider_idx]
                    masked_key = next_prov["api_key"][:8] + "..." + next_prov["api_key"][-4:] if len(next_prov["api_key"]) > 12 else "..."
                    print(f"[INFO] Failover triggered! Rotating to provider: '{next_prov['type']}' ({next_prov['complex_model']}) with Key ({masked_key})...")
                    continue
                break


        # If all attempts are exhausted, raise an exception to stop the agent
        raise RuntimeError("All configured API keys / providers are exhausted or rate-limited.")

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
