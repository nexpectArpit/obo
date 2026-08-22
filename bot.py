import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv(".env.local")
# ─── Configuration ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_TELEGRAM_USER_ID"])
GH_PAT = os.environ["GH_PAT"]
GH_REPO = os.environ.get("GH_REPO", "nexpectArpit/obo")
GH_WORKFLOW = os.environ.get("GH_WORKFLOW", "run_agent.yml")
GH_API = f"https://api.github.com/repos/{GH_REPO}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("obo-bot")

# ─── Auth Guard ──────────────────────────────────────────────────
def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"\n[BOT DIAGNOSTIC] Incoming update from user: {update.effective_user.id if update.effective_user else 'None'}")
        user_id = update.effective_user.id if update.effective_user else None
        if user_id != ALLOWED_USER_ID:
            print(f"[BOT DIAGNOSTIC] Access DENIED: user_id={user_id} != allowed={ALLOWED_USER_ID}")
            await update.effective_message.reply_text("⛔ Unauthorized.")
            return
        print(f"[BOT DIAGNOSTIC] Access GRANTED to user: {user_id}")
        return await func(update, context)
    return wrapper

# ─── GitHub API Helpers ──────────────────────────────────────────
def gh_headers():
    return {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def trigger_workflow(topic="random", resume=False, level_up=False, pin="none"):
    """Trigger the GitHub Actions workflow."""
    url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "topic": topic,
            "resume": str(resume).lower(),
            "level_up": str(level_up).lower(),
            "pin": str(pin)
        }
    }
    r = requests.post(url, headers=gh_headers(), json=payload)
    return r.status_code == 204

def get_running_runs():
    """Get currently running or queued workflow runs."""
    runs = []
    for status in ["in_progress", "queued"]:
        url = f"{GH_API}/actions/runs?status={status}&per_page=5"
        r = requests.get(url, headers=gh_headers())
        if r.status_code == 200:
            runs.extend(r.json().get("workflow_runs", []))
    return runs

def get_latest_run():
    """Get the most recent workflow run."""
    url = f"{GH_API}/actions/runs?per_page=1"
    r = requests.get(url, headers=gh_headers())
    if r.status_code == 200:
        runs = r.json().get("workflow_runs", [])
        return runs[0] if runs else None
    return None

def get_run_jobs(run_id):
    """Get the jobs and their steps for a specific run."""
    url = f"{GH_API}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=gh_headers())
    if r.status_code == 200:
        return r.json().get("jobs", [])
    return []

def cancel_run(run_id):
    """Cancel a running workflow."""
    url = f"{GH_API}/actions/runs/{run_id}/cancel"
    r = requests.post(url, headers=gh_headers())
    return r.status_code == 202

def format_elapsed(started_at_str):
    """Calculate elapsed time from ISO timestamp."""
    try:
        started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - started
        mins = int(elapsed.total_seconds()) // 60
        secs = int(elapsed.total_seconds()) % 60
        return f"{mins}m {secs}s"
    except Exception:
        return "unknown"

def format_run_status(run):
    """Build a detailed status message for a run, including step-by-step progress."""
    run_id = run["id"]
    run_num = run["run_number"]

    # Get step-level details
    jobs = get_run_jobs(run_id)
    
    run_agent_started = None
    if jobs:
        steps = jobs[0].get("steps", [])
        for step in steps:
            if step["name"] == "Run Agent" and step.get("started_at"):
                run_agent_started = step["started_at"]
                break

    if run_agent_started:
        elapsed = format_elapsed(run_agent_started)
        msg = f"🟢 *Run #{run_num}* — Learning for {elapsed}\n\n"
    else:
        msg = f"⚙️ *Run #{run_num}* — Setting up environment...\n\n"
    
    if jobs:
        job = jobs[0]  # We only have one job
        steps = job.get("steps", [])
        for step in steps:
            name = step["name"]
            if name.startswith("Post ") or name in ["Get Playwright Version", "Cache Playwright Browsers"]:
                continue
            status = step["status"]
            conclusion = step.get("conclusion")
            
            if status == "completed":
                if conclusion == "success":
                    icon = "✅"
                elif conclusion == "skipped":
                    icon = "⏭️"
                elif conclusion == "cancelled":
                    icon = "🟡"
                else:
                    icon = "❌"
            elif status == "in_progress":
                icon = "⏳"
            else:
                icon = "⬜"
            
            msg += f"{icon} {name}\n"
    
    return msg

# ─── Main Menu ───────────────────────────────────────────────────
from pathlib import Path

TRACK_SKILL_MAP = {
    "cpp": [("DP", "Dynamic Programming"), ("Algo", "Algorithms")],
    "arch": [("Mem", "Memory Systems"), ("Arch", "Computer Architecture")],
    "os": [("SysCall", "System Calls"), ("OS", "Operating Systems")],
    "ds": [("ML", "Machine Learning"), ("Hyp", "Hypothesis Testing")],
    "dl": [("DL", "Deep Learning"), ("NN", "Neural Networks")],
    "maths": [("Alg", "Algebra"), ("Opt", "Optimization")]
}

def main_menu_keyboard():
    enabled = False
    state_path = Path(__file__).resolve().parent / "data" / "scheduler_state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            enabled = state.get("enabled", False)
        except Exception:
            pass
    loop_text = "⏰ Auto-Loop: ACTIVE" if enabled else "⏰ Auto-Loop: INACTIVE"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Random", callback_data="start_random"),
         InlineKeyboardButton("📈 Focus Pinned Track", callback_data="level_up")],
        [InlineKeyboardButton("📚 Start Topic", callback_data="start_topic"),
         InlineKeyboardButton("🔄 Resume Last", callback_data="resume")],
        [InlineKeyboardButton("🛑 Stop Agent", callback_data="stop"),
         InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton(loop_text, callback_data="toggle_auto_loop")]
    ])

def tracks_menu_keyboard():
    # Load current skill levels
    skills = {}
    skills_path = Path(__file__).resolve().parent / "data" / "learned_skills.json"
    if skills_path.exists():
        try:
            with open(skills_path, "r") as f:
                skills = json.load(f)
        except Exception:
            pass

    def btn_text(label, track_key):
        mappings = TRACK_SKILL_MAP.get(track_key, [])
        levels = []
        for short_name, long_name in mappings:
            lvl = skills.get(long_name, 1)
            levels.append(str(lvl))
        if levels:
            return f"{label} ({', '.join(levels)})"
        return label

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text("1. CP / DSA", "cpp"), callback_data="pin_cpp"),
         InlineKeyboardButton(btn_text("2. Arch & Net", "arch"), callback_data="pin_arch")],
        [InlineKeyboardButton(btn_text("3. OS", "os"), callback_data="pin_os"),
         InlineKeyboardButton(btn_text("4. Data Science", "ds"), callback_data="pin_ds")],
        [InlineKeyboardButton(btn_text("5. DL", "dl"), callback_data="pin_dl"),
         InlineKeyboardButton(btn_text("6. Maths for DS", "maths"), callback_data="pin_maths")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_to_menu")]
    ])

# ─── Handlers ────────────────────────────────────────────────────
@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *Oboe Learning Agent*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

@authorized
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "back_to_menu":
        await query.message.edit_text(
            "🎵 *Oboe Learning Agent*\n\nChoose an action:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

    elif action == "start_random":
        success = trigger_workflow(topic="random", resume=False)
        if success:
            await query.message.reply_text(
                "🚀 *Random topic started!*\n\n"
                "The agent is booting up on GitHub Actions.\n"
                "It will take ~2 minutes to set up, then begin learning.\n\n"
                "Tap 📊 Status to track progress.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.message.reply_text("❌ Failed to trigger workflow. Check your GH\\_PAT permissions.",
                                           reply_markup=main_menu_keyboard())

    elif action == "level_up":
        await query.message.edit_text(
            "📈 *Select Pinned Track to Focus:*\n\nChoose one of the 6 pinned tracks to run and progress in Oboe continuous chats:",
            parse_mode="Markdown",
            reply_markup=tracks_menu_keyboard()
        )

    elif action.startswith("pin_"):
        track_name = action.replace("pin_", "")
        track_display = {
            "cpp": "1. CP / DSA",
            "arch": "2. Computer Arch & Net",
            "os": "3. OS",
            "ds": "4. Data Science",
            "dl": "5. DL",
            "maths": "6. Maths for DS"
        }.get(track_name, track_name.upper())

        success = trigger_workflow(topic="random", resume=False, pin=track_name)
        if success:
            await query.message.reply_text(
                f"🎯 *Focus Mode active on Pinned Track: {track_display}*\n\n"
                "The agent will open the corresponding pinned chat in the sidebar and process the next sub-topic.\n\n"
                "Tap 📊 Status to track progress.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.message.reply_text(f"❌ Failed to trigger workflow for {track_display}.",
                                           reply_markup=main_menu_keyboard())

    elif action == "resume":
        success = trigger_workflow(topic="random", resume=True)
        if success:
            await query.message.reply_text(
                "🔄 *Resuming last chat!*\n\n"
                "The agent will pick up where you left off.\n\n"
                "Tap 📊 Status to track progress.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.message.reply_text("❌ Failed to trigger workflow. Check your GH\\_PAT permissions.",
                                           reply_markup=main_menu_keyboard())

    elif action == "start_topic":
        context.user_data["awaiting_topic"] = True
        await query.message.reply_text(
            "📚 *Send me the topic name:*\n\nType the exact topic title you want to learn.",
            parse_mode="Markdown"
        )

    elif action == "stop":
        runs = get_running_runs()
        if not runs:
            await query.message.reply_text(
                "✅ No active runs to stop.",
                reply_markup=main_menu_keyboard()
            )
        else:
            cancelled = 0
            for run in runs:
                if cancel_run(run["id"]):
                    cancelled += 1
            await query.message.reply_text(
                f"🛑 *Cancelled {cancelled} active run(s).*\n\n"
                "The agent will save its progress before shutting down.\n"
                "A session summary will be sent once the run completes.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )

    elif action == "status":
        runs = get_running_runs()
        
        if runs:
            msg = ""
            for run in runs:
                msg += format_run_status(run)
        else:
            latest = get_latest_run()
            if latest:
                conclusion = latest.get("conclusion", "unknown")
                status_emoji = {"success": "✅", "failure": "❌", "cancelled": "🟡"}.get(conclusion, "⏳")
                started = latest.get("run_started_at", "")
                elapsed = format_elapsed(started) if started else "N/A"
                
                msg = f"{status_emoji} *Last run #{latest['run_number']}:* {conclusion}\n"
                msg += f"⏱️ Duration: {elapsed}\n\n"
                
                # Show step details for last run too
                jobs = get_run_jobs(latest["id"])
                if jobs:
                    steps = jobs[0].get("steps", [])
                    for step in steps:
                        name = step["name"]
                        if name.startswith("Post ") or name in ["Get Playwright Version", "Cache Playwright Browsers"]:
                            continue
                        conc = step.get("conclusion", "skipped")
                        icon = {"success": "✅", "failure": "❌", "cancelled": "🟡", "skipped": "⏭️"}.get(conc, "⬜")
                        msg += f"{icon} {name}\n"
            else:
                msg = "📭 No workflow runs found."
        
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif action == "toggle_auto_loop":
        state_path = Path(__file__).resolve().parent / "data" / "scheduler_state.json"
        enabled = False
        state_data = {}
        if state_path.exists():
            try:
                state_data = json.loads(state_path.read_text())
                enabled = state_data.get("enabled", False)
            except Exception:
                pass
        
        new_enabled = not enabled
        state_data["enabled"] = new_enabled
        
        try:
            state_path.write_text(json.dumps(state_data, indent=4))
        except Exception:
            pass
            
        status_msg = "⏰ *Auto-Loop Scheduler activated!*" if new_enabled else "🛑 *Auto-Loop Scheduler deactivated.*"
        await query.message.reply_text(
            status_msg,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )

@authorized
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle topic text input when user is prompted."""
    if context.user_data.get("awaiting_topic"):
        topic = update.message.text.strip()
        context.user_data["awaiting_topic"] = False
        success = trigger_workflow(topic=topic, resume=False)
        if success:
            await update.message.reply_text(
                f"📚 *Started topic:* _{topic}_\n\n"
                "The agent is booting up. Tap 📊 Status to track progress.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text("❌ Failed to trigger workflow. Check your GH\\_PAT permissions.",
                                            reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("Use /menu to see available actions.", reply_markup=main_menu_keyboard())

@authorized
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *Oboe Learning Agent*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

# ─── Main ────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🤖 Oboe Telegram Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
