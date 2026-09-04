import sys
import signal

def register_shutdown_signals(agent):
    """Registers standard POSIX signals for clean abort state-saving."""
    def handle_signal(sig, frame):
        print(f"\n[INFO] Received signal {sig}. Interrupted/Cancelled. Saving session state...")
        agent._final_status = "CANCELLED"
        
        # Write state immediately before browser close (browser close can hang and trigger SIGKILL)
        try:
            from pathlib import Path
            state_path = Path(__file__).resolve().parent.parent / "data" / "agent_state.json"
            pid_path = Path(__file__).resolve().parent.parent / "agent.pid"
            from agent.session_state import OboeStateManager
            OboeStateManager.finalize_session(agent, agent.start_time, state_path, pid_path, status="CANCELLED")
        except Exception as e:
            print(f"[WARNING] Signal handler failed state writing: {e}")
            
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
    except Exception as register_err:
        print(f"[WARNING] Could not register process signals: {register_err}")
