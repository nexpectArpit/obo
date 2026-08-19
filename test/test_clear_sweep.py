#!/usr/bin/env python3
"""
Regression Test: Bulk Telegram Chat History Cleanup (Clear Sweep)

Tests deleting up to 300 recent message IDs concurrently via Telegram API.
"""

import sys
import os
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv('.env.local')

token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('ALLOWED_TELEGRAM_USER_ID')

if not token or not chat_id:
    print("[ERROR] Credentials missing in .env.local")
    sys.exit(1)

def run_clear_sweep(depth=300):
    url_send = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url_send, json={"chat_id": chat_id, "text": "🧹 Test: Initiating bulk clear sweep..."})
    if r.status_code != 200:
        print(f"[ERROR] Failed to send test message: {r.text}")
        return False
        
    max_id = r.json()["result"]["message_id"]
    print(f"[INFO] Current max message_id: {max_id}")

    def del_msg(mid):
        u = f"https://api.telegram.org/bot{token}/deleteMessage"
        res = requests.post(u, json={"chat_id": chat_id, "message_id": mid})
        return res.status_code == 200 and res.json().get("ok")

    print(f"[INFO] Deleting up to {depth} previous message IDs concurrently...")
    with ThreadPoolExecutor(max_workers=30) as executor:
        results = list(executor.map(del_msg, range(max_id, max_id - depth, -1)))

    deleted_count = sum(results)
    print(f"[SUCCESS] Bulk clear sweep complete! Deleted {deleted_count} messages.")
    return True

if __name__ == "__main__":
    run_clear_sweep()
