import os
import requests
from dotenv import load_dotenv

load_dotenv(".env.local")
pat = os.environ.get("GH_PAT")
repo = os.environ.get("GH_REPO", "nexpectArpit/obo")

headers = {
    "Authorization": f"Bearer {pat}",
    "Accept": "application/vnd.github+json"
}

r = requests.get(f"https://api.github.com/repos/{repo}/actions/runs", headers=headers)
if r.status_code == 200:
    runs = r.json().get("workflow_runs", [])
    for run in runs[:5]:
        print(f"Run {run['run_number']}: ID {run['id']} - {run['name']} - {run['status']}")
        
        # fetch jobs for this run
        jobs_url = run["jobs_url"]
        jr = requests.get(jobs_url, headers=headers)
        if jr.status_code == 200:
            for job in jr.json().get("jobs", []):
                print(f"  -> Job ID: {job['id']} - Name: {job['name']} - Conclusion: {job['conclusion']}")
else:
    print(r.status_code, r.text)
