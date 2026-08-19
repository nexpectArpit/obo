import os
import sys
import time
import requests
from dotenv import load_dotenv

# Load env variables from root of project
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.local"))

pat = os.environ.get("GH_PAT")
repo = os.environ.get("GH_REPO", "nexpectArpit/obo")
workflow = os.environ.get("GH_WORKFLOW", "run_agent.yml")

if not pat:
    print("[ERROR] GH_PAT not found in .env.local")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {pat}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "obo-workflow-tester"
}

def trigger_run(topic="random", level_up="false"):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    payload = {"ref": "main", "inputs": {"topic": topic, "resume": "false", "level_up": level_up}}
    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 204:
        print("[INFO] Workflow triggered successfully!")
        return True
    print(f"[ERROR] Failed to trigger workflow: {r.status_code} - {r.text}")
    return False

def get_latest_running_run():
    url = f"https://api.github.com/repos/{repo}/actions/runs?status=in_progress&per_page=5"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        runs = r.json().get("workflow_runs", [])
        if runs:
            # Return the newest run
            return runs[0]["id"], runs[0]["run_number"]
    return None, None

def cancel_run(run_id):
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/cancel"
    r = requests.post(url, headers=headers)
    if r.status_code == 202:
        print(f"[INFO] Sent cancellation request for Run ID {run_id}.")
        return True
    print(f"[ERROR] Failed to cancel run: {r.status_code} - {r.text}")
    return False

def wait_for_completion(run_id):
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    for _ in range(30):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            status = r.json().get("status")
            conclusion = r.json().get("conclusion")
            print(f"[POLL] Status: {status}, Conclusion: {conclusion}")
            if status == "completed":
                return conclusion
        time.sleep(10)
    return "timeout"

def fetch_job_logs(run_id):
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=headers)
    if r.status_code != 200 or not r.json().get("jobs"):
        print("[ERROR] Could not fetch jobs for this run.")
        return
    
    job_id = r.json()["jobs"][0]["id"]
    print(f"[INFO] Fetching logs for Job ID {job_id}...")
    log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    log_r = requests.get(log_url, headers=headers, allow_redirects=False)
    if log_r.status_code == 302:
        redirect_url = log_r.headers.get("Location")
        log_r = requests.get(redirect_url)
    if log_r.status_code == 200:
        return log_r.text
    print(f"[ERROR] Failed to download logs: {log_r.status_code}")
    return ""

def main():
    level_up = "true" if "--level-up" in sys.argv else "false"
    topic = "random" if level_up == "true" else "Multi Word Space Test Topic"
    if not trigger_run(topic=topic, level_up=level_up):
        return
    
    # Wait for GitHub Actions to register the run
    print("[INFO] Waiting for GitHub to register the run...")
    run_id, run_num = None, None
    for _ in range(10):
        time.sleep(3)
        run_id, run_num = get_latest_running_run()
        if run_id:
            break
            
    if not run_id:
        print("[ERROR] Run not registered in time. Exiting.")
        return
        
    print(f"[SUCCESS] Tracking Run #{run_num} (ID: {run_id})")
    
    # Let it run for 1.5 minutes so it completes setup and does agent execution
    sleep_time = 90
    print(f"[INFO] Allowing agent to execute for {sleep_time} seconds...")
    time.sleep(sleep_time)
    
    # Cancel the run
    print("[INFO] Cancelling run to test summary execution under signal context...")
    if not cancel_run(run_id):
        return
        
    # Wait for cancellation to conclude
    print("[INFO] Waiting for run cancellation to conclude...")
    conclusion = wait_for_completion(run_id)
    print(f"[INFO] Run finished with conclusion: {conclusion}")
    
    # Fetch logs to verify the fix
    logs = fetch_job_logs(run_id)
    if not logs:
        return
        
    # Check argument parsing crash (spaces in topic)
    if "unrecognized arguments" in logs or "Process completed with exit code 2" in logs:
        print("[FAIL] Unrecognized arguments / multi-word topic string quote parsing crash!")
    else:
        print("[PASS] Multi-word topic string with spaces was parsed successfully.")

    # Check setup crash fix (should not contain headed crash error)
    if "Looks like you launched a headed browser without having a XServer running." in logs:
        print("[FAIL] Headed Setup Crash occurred in the logs!")
    else:
        print("[PASS] Setup was bypassed correctly (No Headed Crash error found).")
        
    # Check signal handler execution
    if "Interrupted/Cancelled. Saving session state..." in logs or "Oboe Session Stopped!" in logs:
        print("[PASS] Signal handler caught SIGTERM and state was updated successfully.")
    else:
        # Since we cancelled it during execution, check if signal handler got triggered
        print("[WARNING] Did not find cancellation logging in run output. Check Telegram.")
        
    # Check telegram notification success
    if "Telegram notification sent successfully" in logs:
        print("[PASS] Telegram notification step ran and sent successfully.")
    else:
        print("[FAIL] Telegram notification step was not found or failed.")

if __name__ == "__main__":
    main()
