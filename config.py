import os
import json
import tempfile

# 1. LOCAL DEVELOPER PROTECTION
# Manually load local.settings.json ONLY if we are on a local machine.
# This ensures raw 'python' commands work without the Azure runtime.
if os.getenv("HOME") != "/home":
    settings_path = os.path.join(os.path.dirname(__file__), 'local.settings.json')
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            try:
                settings = json.load(f)
                for key, value in settings.get("Values", {}).items():
                    os.environ[key] = value
            except Exception as e:
                print(f"⚠️ Warning: Found local.settings.json but couldn't parse it: {e}")

# 2. CONFIGURATION FETCHING
# Now we pull everything from the environment (wherever it came from).
def get_env(key, default=None):
    val = os.getenv(key, default)
    if not val and key != "HOME":
        print(f"⚠️ Warning: Configuration key '{key}' is missing!")
    return val

# API Keys & Connections
AZURE_SPEECH_KEY = get_env("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = get_env("AZURE_SPEECH_REGION", "eastus")
AZURE_STORAGE_CONNECTION_STRING = get_env("AZURE_STORAGE_CONNECTION_STRING")
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY")
TELEGRAM_TOKEN = get_env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_env("TELEGRAM_CHAT_ID")

# App Constants
AZURE_STORAGE_CONTAINER = "podcasts"
AZURE_TABLE_NAME = "PostHistory"
LLM_MODEL = "deepseek-chat"
SUBREDDITS = ["gonewildstories"]

# 3. ENVIRONMENT DETECTION & PATHS
IS_CLOUD = os.getenv("HOME") == "/home"

if IS_CLOUD:
    # Azure Linux environment (Read-only except /tmp)
    LOCAL_BACKUP_PATH = "/tmp"
else:
    # Local machine environment
    LOCAL_BACKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stories_backup")
    if not os.path.exists(LOCAL_BACKUP_PATH):
        os.makedirs(LOCAL_BACKUP_PATH)