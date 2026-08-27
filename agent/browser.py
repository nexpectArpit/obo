import os
import random
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import config

class OboeBrowser:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """Start the browser context."""
        # Check if portable state.json exists
        state_path = Path(__file__).resolve().parent.parent / "data" / "state.json"
        storage_state = str(state_path) if state_path.exists() else None
        
        self.playwright = sync_playwright().start()
        
        # On GitHub Actions, use pre-installed Chrome to avoid downloading browser binaries
        is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        
        if storage_state:
            print(f"[INFO] Seeding browser context with storage state from: {state_path.name}")
            launch_args = {
                "headless": self.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            }
            if is_github_actions:
                launch_args["channel"] = "chrome"
                
            self.browser = self.playwright.chromium.launch(**launch_args)
            self.context = self.browser.new_context(
                storage_state=storage_state,
                viewport={"width": 1280, "height": 800}
            )
        else:
            print(f"Launching persistent Chrome context from: {config.USER_DATA_DIR}")
            config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Note: launch_persistent_context takes launch options AND context options as flat kwargs
            # viewport must be passed directly, not inside a nested dict with launch args
            persistent_launch_kwargs = {
                "headless": self.headless,
                "slow_mo": 50,  # Reduced from 100ms — still human-like but saves ~2s/turn
                "viewport": {"width": 1280, "height": 800},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            }
            if is_github_actions:
                persistent_launch_kwargs["channel"] = "chrome"

            self.context = self.playwright.chromium.launch_persistent_context(
                str(config.USER_DATA_DIR),
                **persistent_launch_kwargs
            )
        
        # Get or create page
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        # Add human-like headers and evasions
        self.page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9"
        })

    def navigate_to_home(self):
        """Navigate to Oboe platform and wait for network idle."""
        print(f"Navigating to {config.OBOE_URL}...")
        self.page.goto(config.OBOE_URL, wait_until="load")
        self.page.wait_for_timeout(3000)

    def take_screenshot(self, name="screenshot.png"):
        """Save a debug screenshot to the brain directory or local root."""
        try:
            self.page.screenshot(path=name)
            print(f"Screenshot saved to {name}")
        except Exception as e:
            print(f"[INFO] Could not capture screenshot ({name}): {e}")

    def close(self):
        """Close browser resources."""
        if self.context:
            try: self.context.close()
            except Exception: pass
        if self.browser:
            try: self.browser.close()
            except Exception: pass
        if self.playwright:
            try: self.playwright.stop()
            except Exception: pass
        print("Browser stopped.")

    def get_interaction_state(self):
        """Phase 4: Interaction Classification.
        Uses a single atomic JS evaluation to avoid TOCTOU races where the page
        transitions between separate locator.count() calls and returns 'unknown'.
        """
        start_time = time.perf_counter()

        result = self.page.evaluate('''() => {
            // 1. Loading check
            const loader = document.querySelector('[data-test-id="loader"], .generating, .thinking');
            if (loader && loader.offsetParent !== null) return "loading";

            // 2. Suggested replies
            const btns = document.querySelectorAll('[data-test-id="suggested-replies"] button');
            if (btns.length > 0) {
                const allDisabled = Array.from(btns).every(b => b.disabled || b.getAttribute('disabled') !== null);
                if (allDisabled) return "loading";
                return "suggested_replies";
            }

            // 3. Free text textarea
            const ta = document.querySelector('textarea[name="prompt"]');
            if (ta && ta.offsetParent !== null && !ta.disabled) return "free_text";

            // 4. Fallback loading text scan
            const txt = (document.body.innerText || "").toLowerCase();
            if (txt.includes("reviewing") || txt.includes("generating") || txt.includes("loading"))
                return "loading";

            return "unknown";
        }''')

        latency = (time.perf_counter() - start_time) * 1000
        print(f"[DOM_CHECK] mode=atomic latency={latency:.2f}ms state={result}")
        return result

    def dismiss_overlays(self):
        """Finds and dismisses any blocking dialog modals/overlays (e.g. Oboe level-up/completion celebrate dialogs)."""
        try:
            # 1. Try sending Escape key to close standard Radix/React dialogs
            dialog_count = self.page.locator('[role="dialog"], [data-state="open"]').count()
            if dialog_count > 0:
                print(f"[OVERLAY] Detected {dialog_count} open dialog(s). Sending Escape key to dismiss...")
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(1000)
                
            # 2. Look for any explicit close/dismiss buttons and click them
            close_buttons = self.page.locator('button:has-text("Close"), button:has-text("Got it"), button:has-text("Dismiss"), [aria-label="Close"]').all()
            for btn in close_buttons:
                try:
                    if btn.is_visible():
                        print("[OVERLAY] Clicking visible dialog close/dismiss button...")
                        btn.click(timeout=2000)
                        self.page.wait_for_timeout(1000)
                except Exception:
                    pass
        except Exception as e:
            print(f"[OVERLAY] Notice during overlay dismissal: {e}")

    def observe_page(self):
        """Phase 3: Platform Observation.
        Extracts dialogue history and list of available options from the current page.
        """
        self.dismiss_overlays()
        state = self.get_interaction_state()
        
        # Extract chat messages
        messages = []
        # Look for messages containing turns
        turns = self.page.locator('[id^="chatMessage-"]').all()
        for turn in turns:
            text = (turn.text_content() or "").strip()
            # Determine role (user vs assistant) based on parent turn attributes
            # Or based on text alignment / test-ids
            parent = turn.locator("xpath=..")
            role_attr = parent.get_attribute("data-turn-role") or "unknown"
            if text:
                messages.append({
                    "role": role_attr,
                    "text": text
                })

        # Extract available choices (MCQ / Suggested replies)
        choices = []
        if state == "suggested_replies":
            buttons = self.page.locator('[data-test-id="suggested-replies"] button').all()
            for btn in buttons:
                # Target the actual option text span (which holds the text the user sees)
                inline_span = btn.locator('span.inline')
                if inline_span.count() > 0:
                    text = (inline_span.first.text_content() or "").strip()
                else:
                    text = (btn.text_content() or "").strip()
                if text:
                    choices.append(text)

        # Extract active skills and levels via in-page DOM evaluate
        skills = {}
        try:
            dom_skills = self.page.evaluate(r'''() => {
                const results = {};
                // Strategy 1: Look for exact LV badges and resolve their skill names
                const allElements = document.querySelectorAll('span, div, p, button, a');
                for (const el of allElements) {
                    if (el.children.length > 0) continue;
                    const text = (el.textContent || '').trim();
                    const match = text.match(/^(?:LV|Level)\.?\s*(\d+)$/i);
                    if (match) {
                        const levelNum = match[1];
                        // Walk up through parent rows/containers to find the skill name
                        let parent = el.parentElement;
                        for (let depth = 0; depth < 5 && parent; depth++) {
                            // Find leaf text nodes inside this container (excluding the badge itself and button labels)
                            const innerTexts = Array.from(parent.querySelectorAll('*'))
                                .filter(node => node.children.length === 0 && node !== el)
                                .map(node => (node.textContent || '').trim())
                                .filter(t => t && !t.match(/^(?:LV|Level)\.?\s*\d+$/i) && t !== 'Skills' && t.length > 2 && t.length < 60 && !t.includes('{') && !t.includes('}'));
                            
                            if (innerTexts.length > 0) {
                                // The closest non-badge text in this row is the skill title
                                const candidateTitle = innerTexts[0];
                                if (candidateTitle && !candidateTitle.toLowerCase().includes('http')) {
                                    results[candidateTitle] = `LV ${levelNum}`;
                                    break;
                                }
                            }
                            parent = parent.parentElement;
                        }
                    }
                }

                // Strategy 2: Check any skill bar elements with data attributes or classes
                const skillBars = document.querySelectorAll('[class*="skill"], [data-test-id*="skill"]');
                for (const bar of skillBars) {
                    const fullText = (bar.textContent || '').trim();
                    const barMatch = fullText.match(/([A-Za-z\s\+\-\#]{3,40})\s+(?:LV|Level)\.?\s*(\d+)/i);
                    if (barMatch) {
                        const name = barMatch[1].replace(/Skills/g, '').trim();
                        const lv = barMatch[2];
                        if (name && name.length > 2 && name.length < 50) {
                            results[name] = `LV ${lv}`;
                        }
                    }
                }

                return results;
            }''')
            if isinstance(dom_skills, dict):
                skills.update(dom_skills)
        except Exception as eval_err:
            print(f"[WARNING] Skill extraction notice: {eval_err}")

        return {
            "state": state,
            "messages": messages,
            "choices": choices,
            "skills": skills
        }

    def click_suggestion_by_text(self, text):
        """Execute action: Click an MCQ / suggestion choice by matching text."""
        self.dismiss_overlays()
        # Human-like thinking delay (2–5s — reduced from 3–9s to cut per-turn latency)
        delay = random.uniform(2.0, 5.0)
        print(f"Thinking for {delay:.2f} seconds...")
        self.page.wait_for_timeout(int(delay * 1000))

        print(f"Clicking suggestion: '{text}'")
        # Locator matching exact text inside the suggested replies (either in button or child span)
        button = self.page.locator('[data-test-id="suggested-replies"]').last.locator('button').filter(
            has=self.page.locator('span.inline').filter(has_text=text)
        ).first

        if button.count() == 0:
            # Fallback to direct button has-text filter
            button = self.page.locator('[data-test-id="suggested-replies"]').last.locator('button').filter(has_text=text).first

        if button.count() == 0:
            print(f"[WARNING] Could not find suggestion button for text: '{text}'. Skipping click.")
            return

        if button.is_disabled():
            print(f"[WARNING] Suggestion button for '{text}' is disabled (already clicked/waiting for response). Skipping click to prevent timeout.")
            return

        try:
            button.click(timeout=5000)
        except Exception as e:
            print(f"[WARNING] Failed to click button: {e}. Skipping.")
        
        # Wait for action to register
        self.page.wait_for_timeout(3000)

    def type_and_submit(self, text):
        """Execute action: Type text in the prompt input and submit."""
        self.dismiss_overlays()
        if not text:
            text = "I'm interested to learn more about this."
        text_str = str(text)

        # Human-like thinking delay (2–5s — reduced from 3–9s to cut per-turn latency)
        delay = random.uniform(2.0, 5.0)
        print(f"Thinking for {delay:.2f} seconds...")
        self.page.wait_for_timeout(int(delay * 1000))
        
        print(f"Typing free text response: '{text_str}'")
        textarea = self.page.locator('textarea[name="prompt"]')
        textarea.fill(text_str)
        self.page.wait_for_timeout(1000)  # Human-like delay after typing
        textarea.press("Enter")
        # Wait for action to register
        self.page.wait_for_timeout(3000)

