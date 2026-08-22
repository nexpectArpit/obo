import os
import requests
import json
import base64
from dotenv import load_dotenv

load_dotenv(".env.local")

GH_PAT = os.environ.get("GH_PAT")
GH_REPO = os.environ.get("GH_REPO", "nexpectArpit/obo")

url = f"https://api.github.com/repos/{GH_REPO}/contents/learned_skills.json"
headers = {
    "Authorization": f"Bearer {GH_PAT}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "test-script"
}

r = requests.get(url, headers=headers)
print("Status Code:", r.status_code)
if r.status_code == 200:
    data = r.json()
    content_b64 = data["content"]
    # Decode base64
    decoded = base64.b64decode(content_b64).decode("utf-8")
    skills = json.loads(decoded)
    print("Successfully fetched skills from GitHub! Sample keys:")
    print("Algorithms:", skills.get("Algorithms"))
    print("Dynamic Programming:", skills.get("Dynamic Programming"))
    print("Memory Systems:", skills.get("Memory Systems"))
else:
    print("Error response:", r.text)
