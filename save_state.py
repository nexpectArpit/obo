import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def main():
    user_data_dir = Path(__file__).resolve().parent / ".user_data"
    state_file = Path(__file__).resolve().parent / "data" / "state.json"
    
    if not user_data_dir.exists():
        print(f"Error: Local session folder '{user_data_dir}' not found. Please log in locally first.")
        return
        
    print("Launching Chromium to capture session...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True
        )
        # Capture and save the portable authentication state
        await context.storage_state(path=str(state_file))
        await context.close()
        print(f"\n🎉 Success! Portable session state exported to: {state_file.name}")
        print("This file contains your Oboe session cookies. Do NOT share it publicly.")

if __name__ == "__main__":
    asyncio.run(main())
