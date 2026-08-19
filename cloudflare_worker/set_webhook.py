#!/usr/bin/env python3
"""
Telegram Webhook Setup Script for Cloudflare Worker

Usage:
  python cloudflare_worker/set_webhook.py <WORKER_URL> <SECRET_TOKEN>
  
Example:
  python cloudflare_worker/set_webhook.py https://obo-telegram-bot.my-subdomain.workers.dev mysecret123
"""

import sys
import os
import requests
from dotenv import load_dotenv

# Load .env.local if present
load_dotenv('.env.local')

token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    print("[ERROR] TELEGRAM_BOT_TOKEN not found in environment or .env.local")
    sys.exit(1)

if len(sys.argv) < 3:
    print("Usage: python cloudflare_worker/set_webhook.py <WORKER_URL> <SECRET_TOKEN>")
    print("Example: python cloudflare_worker/set_webhook.py https://obo-bot.workers.dev mysecrettoken123")
    sys.exit(1)

worker_url = sys.argv[1].strip()
secret_token = sys.argv[2].strip()

print(f"[INFO] Registering Telegram Webhook to: {worker_url}")
set_url = f"https://api.telegram.org/bot{token}/setWebhook"
payload = {
    "url": worker_url,
    "secret_token": secret_token
}

r = requests.post(set_url, json=payload)
if r.status_code == 200 and r.json().get("ok"):
    print("[SUCCESS] Webhook registered successfully with Telegram!")
    print(r.json())
else:
    print(f"[ERROR] Failed to set webhook: {r.status_code} - {r.text}")
