import sys
import argparse
import config
from browser import OboeBrowser
from agent import OboeAgent

def setup_session():
    """Phase 2: Authentication setup."""
    print("=== Starting Oboe Authentication Setup ===")
    print("This will open a persistent Chrome browser. Please log in manually.")
    print("Once logged in, return here and press Enter to save session.")
    
    browser = OboeBrowser(headless=False)
    try:
        browser.start()
        browser.navigate_to_home()
        input("\n>>> Press ENTER once you have logged in and are on the main dashboard... <<<")
        browser.take_screenshot("setup_success.png")
        print("Session successfully persisted in .user_data.")
    except Exception as e:
        print(f"Error during setup: {e}")
    finally:
        browser.close()

def is_setup_complete():
    """Check if the user data directory exists and is not empty, or if state.json exists."""
    from pathlib import Path
    state_path = Path(__file__).resolve().parent / "state.json"
    if state_path.exists():
        return True
    if not config.USER_DATA_DIR.exists():
        return False
    # Check if there is any file or directory inside .user_data
    try:
        return any(config.USER_DATA_DIR.iterdir())
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="obo - Browser-based learning agent for oboe.com")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Setup command
    subparsers.add_parser("setup", help="Launch browser for manual login / authentication setup")

    # Learn command
    learn_parser = subparsers.add_parser("learn", help="Run the continuous agent learning loop")
    learn_parser.add_argument("--topic", type=str, default="random", help="The topic to learn (default: random)")
    learn_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    learn_parser.add_argument("--resume", action="store_true", help="Resume the most recent chat session from history")
    learn_parser.add_argument("--level-up", action="store_true", help="Only select level-up topics from topics.json")

    args = parser.parse_args()

    # Validate config
    config.validate_config()

    if args.command == "setup":
        setup_session()
    elif args.command == "learn":
        if not is_setup_complete():
            print("\n[INFO] Persistent session not detected in .user_data. Starting authentication setup first...")
            setup_session()
            print("[INFO] Authentication completed. Now starting the learning loop...")
            
        if args.resume:
            print("[INFO] Resuming the most recent chat session from history.")
        else:
            print(f"Starting agent learning loop for topic: {args.topic}")
        
        agent = OboeAgent(topic=args.topic, headless=args.headless, resume=args.resume, level_up=args.level_up)
        agent.run()


if __name__ == "__main__":
    main()
