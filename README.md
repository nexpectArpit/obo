# Obo Agent - Automation & Verification Guide

This guide details how to setup, run, and reset the Obo learning agent.

---

## 1. Setup Instructions

Install dependencies and set up the virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## 2. Configuration (`.env.local`)
Create `.env.local` in the project root:
```env
GROQ_API_KEY=your-groq-api-key-here
OBOE_URL=https://oboe.com
```

---

## 3. Running the Agent

### Mode 1: Visible / Foreground (Watch the agent work)
A normal Chrome browser window opens on your screen, allowing you to watch the agent click buttons and type responses in real-time.
```bash
.venv/bin/python main.py learn
```
- *First Run:* If `.user_data` is empty, log in manually and press **Enter** in your terminal to save your session.
- *Specific Topic:* Pass the topic argument to target a specific course:
  ```bash
  .venv/bin/python main.py learn --topic "Quantum computing basics"
  ```
- *Resume Last Chat:* Pass the `--resume` flag to continue the most recent chat session from your sidebar history:
  ```bash
  .venv/bin/python main.py learn --resume
  ```

### Mode 2: Headless / Background (Hide the browser window)
Chrome runs invisibly in the background. The script prints progress logs to your terminal, but no physical browser window opens on your screen.
```bash
.venv/bin/python main.py learn --headless
```
- *Specific Topic (Headless):*
  ```bash
  .venv/bin/python main.py learn --topic "Quantum computing basics" --headless
  ```
- *Resume Last Chat (Headless):*
  ```bash
  .venv/bin/python main.py learn --resume --headless
  ```

### Mode 3: Persistent Daemon (Close your terminal and keep running)
The agent runs invisibly in the background, and will continue running even if you close your terminal or turn off your terminal window. Logs are written to `obo.log`.
```bash
nohup .venv/bin/python main.py learn --headless > obo.log 2>&1 &
```
- *Specific Topic (Daemon):*
  ```bash
  nohup .venv/bin/python main.py learn --topic "Quantum computing basics" --headless > obo.log 2>&1 &
  ```
- *Resume Last Chat (Daemon):*
  ```bash
  nohup .venv/bin/python main.py learn --resume --headless > obo.log 2>&1 &
  ```
- **Check live progress:** `tail -f obo.log` (Press `Ctrl+C` to exit logs viewer, this won't stop the agent).
- **Stop the agent manually:** `pkill -f main.py`

---

## 4. Reset Session / Switch Accounts
If you want to reset authentication to log in with a different account:
```bash
# Delete the stored session data
rm -rf .user_data

# Re-run setup to authenticate again
.venv/bin/python main.py setup
```
A browser will open. Log in manually, and press **Enter** in the terminal to save the new session.
