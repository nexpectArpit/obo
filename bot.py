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
        user_id = update.effective_user.id
        if user_id != ALLOWED_USER_ID:
            await update.effective_message.reply_text("⛔ Unauthorized.")
            return
        return await func(update, context)
    return wrapper

# ─── GitHub API Helpers ──────────────────────────────────────────
def gh_headers():
    return {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def trigger_workflow(topic="random", resume=False, level_up=False):
    """Trigger the GitHub Actions workflow."""
    url = f"{GH_API}/actions/workflows/{GH_WORKFLOW}/dispatches"
    payload = {
        "ref": "main",
        "inputs": {
            "topic": topic,
            "resume": str(resume).lower(),
            "level_up": str(level_up).lower()
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
    started = run.get("run_started_at", "")
    elapsed = format_elapsed(started) if started else "starting..."

    # Get step-level details
    jobs = get_run_jobs(run_id)
    
    msg = f"🟢 *Run #{run_num}* — Running for {elapsed}\n\n"
    
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
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Random", callback_data="start_random"),
         InlineKeyboardButton("📈 Focus Level Up", callback_data="level_up")],
        [InlineKeyboardButton("📚 Start Topic", callback_data="start_topic"),
         InlineKeyboardButton("🔄 Resume Last", callback_data="resume")],
        [InlineKeyboardButton("🛑 Stop Agent", callback_data="stop"),
         InlineKeyboardButton("📊 Status", callback_data="status")]
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

    if action == "start_random":
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
        success = trigger_workflow(topic="random", resume=False, level_up=True)
        if success:
            await query.message.reply_text(
                "📈 *Focus Level Up started!*\n\n"
                "The agent will target your existing skills to level them up.\n\n"
                "Tap 📊 Status to track progress.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await query.message.reply_text("❌ Failed to trigger workflow. Check your GH\\_PAT permissions.",
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
