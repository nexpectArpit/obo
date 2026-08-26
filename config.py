import os
from pathlib import Path
from dotenv import load_dotenv

# Define workspace directory paths
BASE_DIR = Path(__file__).resolve().parent

# Load .env.local
ENV_PATH = BASE_DIR / ".env.local"
load_dotenv(dotenv_path=ENV_PATH)

# Load all keys matching GROQ_API_KEY, GROQ_API_KEY2, etc.
GROQ_API_KEYS = []
base_key = os.getenv("GROQ_API_KEY", "").strip()
if base_key:
    GROQ_API_KEYS.append(base_key)

for i in range(2, 10):
    key = os.getenv(f"GROQ_API_KEY{i}", "").strip()
    if key:
        GROQ_API_KEYS.append(key)

# Load all keys matching MISTRAL_API_KEY, MISTRAL_API_KEY2, etc.
MISTRAL_API_KEYS = []
mistral_base_key = os.getenv("MISTRAL_API_KEY", "").strip()
if mistral_base_key:
    MISTRAL_API_KEYS.append(mistral_base_key)

for i in range(2, 10):
    key = os.getenv(f"MISTRAL_API_KEY{i}", "").strip()
    if key:
        MISTRAL_API_KEYS.append(key)

# Load all keys matching NVIDIA_API_KEY, NVIDIA_API_KEY2, etc.
NVIDIA_API_KEYS = []
nvidia_base_key = os.getenv("NVIDIA_API_KEY", "").strip()
if nvidia_base_key:
    NVIDIA_API_KEYS.append(nvidia_base_key)

for i in range(2, 10):
    key = os.getenv(f"NVIDIA_API_KEY{i}", "").strip()
    if key:
        NVIDIA_API_KEYS.append(key)

# Configurable per-provider timeouts (in seconds)
PROVIDER_TIMEOUTS = {
    "groq": float(os.getenv("GROQ_TIMEOUT", "15.0")),
    "mistral": float(os.getenv("MISTRAL_TIMEOUT", "20.0")),
    "nvidia": float(os.getenv("NVIDIA_TIMEOUT", "20.0"))
}

# Maximum total time to spend retrying LLM calls across all providers
# Prevents 6+ minute hangs when all providers are rate-limited
MAX_LLM_RETRY_DURATION = float(os.getenv("MAX_LLM_RETRY_DURATION", "45.0"))  # seconds

# Pacing parameters (Quota & Rate-Limit Management)
MIN_DELAY = float(os.getenv("MIN_DELAY", "7.0"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "20.0"))

SKILL_DEPTH_MODE = os.getenv("SKILL_DEPTH_MODE", "true").lower() == "true"

GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
OBOE_URL = os.getenv("OBOE_URL", "https://oboe.com")
USER_DATA_DIR = BASE_DIR / ".user_data"

def validate_config():
    """Verify that vital environment variables are set."""
    if not GROQ_API_KEYS and not NVIDIA_API_KEYS and not MISTRAL_API_KEYS:
        print("[WARNING] No Groq, Nvidia, or Mistral API keys found in .env.local.")
        return False
    return True

