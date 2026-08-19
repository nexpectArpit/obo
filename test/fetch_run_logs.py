import os
import sys
import requests
from dotenv import load_dotenv

# Load env variables from root of project
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.local"))

pat = os.environ.get("GH_PAT")
repo = os.environ.get("GH_REPO", "nexpectArpit/obo")

if not pat:
    print("[ERROR] GH_PAT not found in .env.local")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {pat}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "obo-log-fetcher"
}

def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_run_logs.py <job_id>")
        sys.exit(1)
        
    job_id = sys.argv[1]
    log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    log_r = requests.get(log_url, headers=headers, allow_redirects=False)
    if log_r.status_code == 302:
        redirect_url = log_r.headers.get("Location")
        log_r = requests.get(redirect_url)
        
    if log_r.status_code == 200:
        print(log_r.text)
    else:
        print(f"[ERROR] Failed to download logs: {log_r.status_code} - {log_r.text}")

if __name__ == "__main__":
    main()
