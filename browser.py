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
        state_path = Path(__file__).resolve().parent / "state.json"
        storage_state = str(state_path) if state_path.exists() else None
        
        self.playwright = sync_playwright().start()
        
        if storage_state:
            print(f"[INFO] Seeding browser context with storage state from: {state_path.name}")
            # Launch standard browser + context for storage_state compatibility
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
            )
            self.context = self.browser.new_context(
                storage_state=storage_state,
                viewport={"width": 1280, "height": 800}
            )
        else:
            print(f"Launching persistent Chrome context from: {config.USER_DATA_DIR}")
            config.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Launch persistent context
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(config.USER_DATA_DIR),
                headless=self.headless,
                slow_mo=100,  # Slight delay to look more human-like
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                ]
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
        Detects whether the page has suggested replies, is waiting for free text input,
        is loading, or finished.
        """
        # 1. Check for suggested replies (MCQ / Yes-No / Choices) first
        suggested_replies_locator = self.page.locator('[data-test-id="suggested-replies"] button')
        if suggested_replies_locator.count() > 0:
            return "suggested_replies"

        # 2. Check for free text input second
        textarea_locator = self.page.locator('textarea[name="prompt"]')
        if textarea_locator.count() > 0 and textarea_locator.is_visible() and textarea_locator.is_enabled():
            return "free_text"

        # 3. Check if generating/loading course materials
        body_text = self.page.locator("body").text_content() or ""
        content_lower = body_text.lower()
        if "reviewing" in content_lower or "generating" in content_lower or "loading" in content_lower:
            return "loading"

        return "unknown"

    def observe_page(self):
        """Phase 3: Platform Observation.
        Extracts dialogue history and list of available options from the current page.
        """
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

        # Extract active skills and levels
        skills = {}
        lv_elements = self.page.locator("span, div, p").filter(has_text="LV ").all()
        for lv_el in lv_elements:
            try:
                lv_text = (lv_el.text_content() or "").strip()
                # Match e.g. "LV 1" or "LV 2" (keep it simple and short)
                if len(lv_text) < 10 and "LV" in lv_text:
                    parent = lv_el.locator("xpath=..")
                    parent_text = (parent.text_content() or "").strip()
                    # Clean up parent text to isolate the skill name
                    # In Oboe, parent text is e.g. "Sorting Algorithms  LV 1  Skills"
                    skill_name = parent_text.replace(lv_text, "").replace("Skills", "").strip()
                    # Remove multiple spaces/newlines
                    skill_name = " ".join(skill_name.split())
                    if skill_name and len(skill_name) < 60:
                        skills[skill_name] = lv_text
            except Exception:
                continue

        return {
            "state": state,
            "messages": messages,
            "choices": choices,
            "skills": skills
        }

    def click_suggestion_by_text(self, text):
        """Execute action: Click an MCQ / suggestion choice by matching text."""
        # Human-like thinking delay (randomly between 3.0 and 9.0 seconds)
        delay = random.uniform(3.0, 9.0)
        print(f"Thinking for {delay:.2f} seconds...")
        self.page.wait_for_timeout(int(delay * 1000))
        
        print(f"Clicking suggestion: '{text}'")
        # Locator matching exact text inside the suggested replies (either in button or child span)
        button = self.page.locator('[data-test-id="suggested-replies"] button').filter(
            has=self.page.locator('span.inline').filter(has_text=text)
        ).first
        
        if button.count() == 0:
            # Fallback to direct button has-text filter
            button = self.page.locator('[data-test-id="suggested-replies"] button').filter(has_text=text).first

        button.click()
        # Wait for action to register
        self.page.wait_for_timeout(3000)

    def type_and_submit(self, text):
        """Execute action: Type text in the prompt input and submit."""
        if not text:
            text = "I'm interested to learn more about this."
        text_str = str(text)

        # Human-like thinking delay (randomly between 3.0 and 9.0 seconds)
        delay = random.uniform(3.0, 9.0)
        print(f"Thinking for {delay:.2f} seconds...")
        self.page.wait_for_timeout(int(delay * 1000))
        
        print(f"Typing free text response: '{text_str}'")
        textarea = self.page.locator('textarea[name="prompt"]')
        textarea.fill(text_str)
        self.page.wait_for_timeout(1000)  # Human-like delay after typing
        textarea.press("Enter")
        # Wait for action to register
        self.page.wait_for_timeout(3000)

