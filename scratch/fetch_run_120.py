import os
import sys
import requests
from dotenv import load_dotenv

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
    run_number = 120
    if len(sys.argv) > 1:
        run_number = int(sys.argv[1])
        
    print(f"Fetching workflow runs to find run number {run_number}...")
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Error fetching runs: {r.status_code} - {r.text}")
        return
        
    runs = r.json().get("workflow_runs", [])
    target_run = None
    for run in runs:
        if run.get("run_number") == run_number:
            target_run = run
            break
            
    if not target_run:
        print(f"Run number {run_number} not found in the last 100 runs. Listing recent runs:")
        for run in runs[:10]:
            print(f"Run #{run.get('run_number')} - Status: {run.get('status')}, Conclusion: {run.get('conclusion')}")
        return
        
    print(f"Found Run #{run_number} (ID: {target_run['id']}). Status: {target_run['status']}, Conclusion: {target_run['conclusion']}")
    
    # Get jobs for this run
    jobs_url = target_run["jobs_url"]
    jobs_r = requests.get(jobs_url, headers=headers)
    if jobs_r.status_code != 200:
        print(f"Error fetching jobs: {jobs_r.status_code}")
        return
        
    jobs = jobs_r.json().get("jobs", [])
    if not jobs:
        print("No jobs found for this run.")
        return
        
    for job in jobs:
        print(f"Job: {job['name']} (ID: {job['id']})")
        log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs"
        log_r = requests.get(log_url, headers=headers, allow_redirects=False)
        if log_r.status_code == 302:
            redirect_url = log_r.headers.get("Location")
            log_r = requests.get(redirect_url)
            
        if log_r.status_code == 200:
            log_filename = f"scratch/run_{run_number}_job_{job['id']}.log"
            with open(log_filename, "w") as f:
                f.write(log_r.text)
            print(f"Saved logs to {log_filename}")
        else:
            print(f"Failed to fetch logs for job {job['id']}: {log_r.status_code}")

if __name__ == "__main__":
    main()
