import os
import json
import time
from pathlib import Path
from agent.curriculum_policy import classify_skill, get_domain_keywords
from curriculum.dag_engine import SkillDAGEngine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = DATA_DIR / "depth_traversal_state.json"
TREE_FILE = DATA_DIR / "skill_tree.json"

class DepthFirstResolver:
    def __init__(self, track_name: str):
        self.track_name = track_name.lower().strip()
        self.state = self._load_state()
        self.tree = self._load_tree()
        self._initialize_anchor()

    @property
    def active_state(self) -> dict:
        return self.state["anchors"][self.track_name]

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                full_state = json.loads(STATE_FILE.read_text())
                if "anchors" in full_state:
                    return full_state
                elif "active_anchor" in full_state:
                    # Migrate legacy flat format
                    anchor = full_state["active_anchor"]
                    return {
                        "anchors": {
                            anchor: {
                                "active_branch": full_state.get("active_branch", [anchor]),
                                "current_node": full_state.get("current_node", anchor),
                                "last_good_node": full_state.get("last_good_node", anchor),
                                "branch_attempts": full_state.get("branch_attempts", 0),
                                "consecutive_stalls": full_state.get("consecutive_stalls", 0),
                                "last_backtrack_at": full_state.get("last_backtrack_at", {}),
                                "branch_status": full_state.get("branch_status", "IN_PROGRESS")
                            }
                        },
                        "active_anchor": anchor
                    }
            except Exception:
                pass
        return {"anchors": {}, "active_anchor": ""}

    def _save_state(self):
        try:
            STATE_FILE.write_text(json.dumps(self.state, indent=4))
        except Exception as e:
            print(f"[DFS] Error saving state: {e}")

    def _load_tree(self) -> dict:
        if TREE_FILE.exists():
            try:
                return json.loads(TREE_FILE.read_text())
            except Exception:
                pass
        return {"anchors": {}, "nodes": {}}

    def _save_tree(self):
        try:
            TREE_FILE.write_text(json.dumps(self.tree, indent=4))
        except Exception as e:
            print(f"[DFS] Error saving tree: {e}")

    def _initialize_anchor(self):
        if "anchors" not in self.state:
            self.state = {"anchors": {}, "active_anchor": ""}
        
        self.state["active_anchor"] = self.track_name
        if self.track_name not in self.state["anchors"]:
            self.state["anchors"][self.track_name] = {
                "active_branch": [self.track_name],
                "current_node": self.track_name,
                "last_good_node": self.track_name,
                "branch_attempts": 0,
                "consecutive_stalls": 0,
                "last_backtrack_at": {},
                "branch_status": "IN_PROGRESS"
            }
            self._save_state()

    def resolve_next_node(self) -> dict:
        """
        DFS Traversal to resolve next learning node/topic.
        Returns Oboe-compatible resolved dictionary.
        """
        current_node_id = self.active_state.get("current_node", self.track_name)
        print(f"[DFS] Resolving from active node: {current_node_id}")

        # 1. Check for stall recovery
        if self.active_state.get("consecutive_stalls", 0) > 3:
            print(f"[DFS] Active node {current_node_id} has stalled. Recovery triggered.")
            self._recover_from_stall(current_node_id)
            current_node_id = self.active_state.get("current_node", self.track_name)

        # 2. Retrieve node metadata
        node = self._get_node(current_node_id)
        if not node:
            print(f"[DFS] Node {current_node_id} not found in tree. Resetting to anchor.")
            current_node_id = self.track_name
            node = self._get_node(current_node_id)

        # 3. Find unresolved children in tree
        unresolved_child_id = self._find_unresolved_child(node)
        if unresolved_child_id:
            # Descend
            print(f"[DFS] Unresolved child found. Descending to: {unresolved_child_id}")
            self._descend_to(unresolved_child_id)
            return self._build_resolved_topic(unresolved_child_id)

        # 4. If no children, attempt dynamic child discovery (proposals validation)
        discovered = self._discover_dynamic_children(current_node_id)
        if discovered:
            # We got new children! Descend to the first new one
            new_child_id = discovered[0]
            print(f"[DFS] Dynamic child discovered and validated. Descending to: {new_child_id}")
            self._descend_to(new_child_id)
            return self._build_resolved_topic(new_child_id)

        # 5. If branch is exhausted, backtrack recursively up the active path
        while True:
            print(f"[DFS] Node {current_node_id} is exhausted. Backtracking...")
            self._backtrack(current_node_id)
            
            parent_id = self.active_state.get("current_node", self.track_name)
            parent_node = self._get_node(parent_id)
            
            next_sibling_id = self._find_unresolved_child(parent_node)
            if next_sibling_id:
                print(f"[DFS] Sibling resolved. Descending to: {next_sibling_id}")
                self._descend_to(next_sibling_id)
                return self._build_resolved_topic(next_sibling_id)
            
            if parent_id == self.track_name:
                break
                
            current_node_id = parent_id

        # Ultimate fallback if entire track anchor branch is exhausted
        print(f"[DFS] Entire anchor branch exhausted or unresolved. Using anchor directly.")
        return self._build_resolved_topic(self.track_name)

    def _get_node(self, node_id: str) -> dict:
        if node_id in self.tree.get("anchors", {}):
            return self.tree["anchors"][node_id]
        return self.tree.get("nodes", {}).get(node_id)

    def _find_unresolved_child(self, node: dict) -> str:
        for child_id in node.get("children", []):
            child_node = self._get_node(child_id)
            if child_node and child_node.get("status", "AVAILABLE") not in ("EXHAUSTED", "MASTERED"):
                return child_id
        return None

    def _descend_to(self, node_id: str):
        self.active_state["current_node"] = node_id
        if node_id not in self.active_state["active_branch"]:
            self.active_state["active_branch"].append(node_id)
        self.active_state["branch_status"] = "IN_PROGRESS"
        self._save_state()

    def _backtrack(self, node_id: str):
        # Update node status in tree to EXHAUSTED
        if node_id in self.tree.get("nodes", {}):
            self.tree["nodes"][node_id]["status"] = "EXHAUSTED"
            self._save_tree()

        # Update last backtrack timestamps to detect oscillation
        backtracks = self.active_state.get("last_backtrack_at", {})
        now = time.time()
        backtracks[node_id] = now
        self.active_state["last_backtrack_at"] = backtracks

        # Remove from active branch path and move to parent
        branch = self.active_state.get("active_branch", [])
        if len(branch) > 1:
            branch.pop()
            parent_id = branch[-1]
            self.active_state["current_node"] = parent_id
            self.active_state["active_branch"] = branch
        else:
            self.active_state["current_node"] = self.track_name
            self.active_state["active_branch"] = [self.track_name]
        
        self.active_state["consecutive_stalls"] = 0
        self._save_state()

    def _recover_from_stall(self, node_id: str):
        print(f"[DFS_RECOVERY] Resetting stalled node: {node_id}")
        # Move back to last good node
        last_good = self.active_state.get("last_good_node", self.track_name)
        
        # Oscillation protection check
        backtracks = self.active_state.get("last_backtrack_at", {})
        last_backtrack = backtracks.get(node_id, 0)
        if time.time() - last_backtrack < 300: # 5 minutes
            print(f"[DFS_RECOVERY] Oscillation detected for node {node_id}. Skipping sibling branch.")
            # Mark it low yield
            if node_id in self.tree.get("nodes", {}):
                self.tree["nodes"][node_id]["status"] = "EXHAUSTED"
                self._save_tree()

        self.active_state["current_node"] = last_good
        # Reset active branch back to last_good
        branch = self.active_state.get("active_branch", [])
        if last_good in branch:
            idx = branch.index(last_good)
            self.active_state["active_branch"] = branch[:idx+1]
        else:
            self.active_state["active_branch"] = [self.track_name]
        self.active_state["consecutive_stalls"] = 0
        self._save_state()

    def _discover_dynamic_children(self, parent_id: str) -> list[str]:
        """
        Phase 10.5: Dynamic Child Discovery. Propose child candidates via LLM
        and validate them deterministically before adding them to tree.
        """
        node = self._get_node(parent_id)
        if not node:
            return []

        # Only discover children down to max depth 5 to avoid infinite paths
        branch_path = self.active_state.get("active_branch", [])
        if len(branch_path) >= 5:
            print(f"[DFS] Max depth reached. Skipping child discovery for {parent_id}")
            return []

        print(f"[DFS] Running Dynamic Child Discovery for: {node['name']}")
        try:
            prompt = (
                f"You are a curriculum design assistant.\n"
                f"For the concept '{node['name']}' (under parent anchor domain '{self.track_name}'), "
                f"list 3 highly specific, narrow child sub-concepts that a student should study next to gain deep mastery.\n"
                f"Return the output strictly as a JSON list of strings (no other text or formatting).\n"
                f"Example: [\"Autograd Memory Mechanics\", \"Higher-order Gradients in Autograd\", \"Custom autograd.Function double backward\"]"
            )
            
            response = self._query_llm(prompt)

            # Parse JSON
            raw_candidates = []
            if response:
                content = response.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                raw_candidates = json.loads(content)
            
            if not isinstance(raw_candidates, list):
                print(f"[DFS] LLM child proposals invalid structure: {response}")
                return []

            # Proposal Validation
            validated_ids = []
            for candidate in raw_candidates:
                candidate_name = str(candidate).strip()
                if not candidate_name:
                    continue

                # Generate clean ID (stable identifier)
                clean_id = f"{parent_id}.{candidate_name.lower().replace(' ', '_').replace('.', '_')}"

                # 1. Parent scope & duplicate checks
                if clean_id in self.tree.get("nodes", {}):
                    continue

                # 2. Check for duplicate name
                duplicate = False
                for existing_node in self.tree.get("nodes", {}).values():
                    if existing_node.get("name", "").lower() == candidate_name.lower():
                        duplicate = True
                        break
                if duplicate:
                    continue

                # 3. Validate against Curriculum policy (e.g. reject math stats mixups)
                policy_classification = classify_skill(self.track_name, candidate_name)
                if policy_classification == "SIDE":
                    print(f"[DFS] Proposed candidate '{candidate_name}' rejected by curriculum policy (SIDE skill).")
                    continue

                # Valid child! Commit to tree
                self.tree["nodes"][clean_id] = {
                    "id": clean_id,
                    "name": candidate_name,
                    "parent": parent_id,
                    "children": [],
                    "mastery_level": 1,
                    "evidence": {
                        "concepts_covered": 0,
                        "successful_assessments": 0,
                        "recent_repetition": 0
                    },
                    "status": "AVAILABLE"
                }
                validated_ids.append(clean_id)

            if validated_ids:
                # Add child links to parent node
                node["children"].extend(validated_ids)
                self._save_tree()
                print(f"[DFS] Committed {len(validated_ids)} dynamic child nodes: {validated_ids}")
                return validated_ids

        except Exception as e:
            print(f"[DFS] Dynamic child discovery error: {e}")
        
        return []

    def _build_resolved_topic(self, node_id: str) -> dict:
        """Build Oboe-compatible target topic dictionary."""
        import random
        node = self._get_node(node_id)
        display_name = node["name"]
        
        # Pinned chat title from track root or default
        pinned_chat_title = self.track_name
        track_data = SkillDAGEngine.load_track(self.track_name)
        if track_data:
            pinned_chat_title = track_data.get("pinned_chat_title", self.track_name)

        # Depth-aware steering query construction (Phase 12)
        # Randomized prompt pool — avoids repetitive opener pattern that flags bot behavior
        prompt_templates = [
            f"hey i want to get into {display_name}, can we go through the key ideas and then you quiz me on the tricky parts?",
            f"so i've been reading about {display_name} and i think i get the basics... wanna test me on the harder edge cases?",
            f"let's do {display_name} today. walk me through how it actually works under the hood, then hit me with a tough question",
            f"can we cover {display_name}? i want to understand the core mechanics, not just the surface stuff",
            f"i want to really understand {display_name}. can you build up from the intuition and then challenge me?",
            f"been curious about {display_name} for a while. what's the most important thing to get right about it?",
            f"let's dig into {display_name}. especially the parts where people usually get confused or make mistakes",
            f"ok so {display_name} — i want to actually understand it, not just memorize. can we work through it properly?",
            f"i want to level up on {display_name}. start with the core concept and then test me on something non-trivial",
            f"teach me {display_name} and then give me a problem that actually requires understanding it deeply",
        ]
        prompt = random.choice(prompt_templates)

        return {
            "track_name": self.track_name,
            "pinned_chat_title": pinned_chat_title,
            "topic_index": 999, # Sentinel ID to denote Depth-First routing mode
            "topic_name": display_name,
            "prompt": prompt,
            "target_skills": [display_name]
        }

    def _query_llm(self, prompt_text: str) -> str:
        """Query LLM providers with automatic rotation and failover support."""
        try:
            from agent.llm import OboeLLM
            llm = OboeLLM()
            if not llm.providers:
                return ""
            
            prompt_messages = [
                {"role": "system", "content": "You are a curriculum design assistant."},
                {"role": "user", "content": prompt_text}
            ]
            
            for provider in llm.providers:
                client = llm._get_client_for_provider(provider)
                if not client:
                    continue
                selected_model = provider.get("complex_model")
                try:
                    kwargs = {
                        "model": selected_model,
                        "messages": prompt_messages,
                        "temperature": 0.7
                    }
                    if provider["type"] == "groq":
                        kwargs["response_format"] = {"type": "json_object"}
                    response = client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content
                except Exception as ex:
                    print(f"[DFS] Provider '{provider['type']}' failed dynamic proposals query: {ex}")
        except Exception as e:
            print(f"[DFS] Error instantiating OboeLLM: {e}")
        return ""
