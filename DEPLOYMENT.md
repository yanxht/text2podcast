# ☁️ Azure Deployment & Configuration Guide

This document covers the one-time setup and recurring deployment steps for the `text2podcast-service-01` Function App.

---

## 1. Initial Azure Instance Setup

If you ever need to recreate the service from scratch:

1. **Create a Function App**:
* **Runtime Stack**: Python 3.12.
* **Operating System**: Linux (Required for our FFmpeg binary logic).
* **Plan Type**: Consumption (Serverless) is fine for this project.


2. **Storage Account**: Ensure the Function App is linked to the same storage account as your `text2podcastbox` blobs.

---

## 2. Environment Variables (Application Settings)

Azure Functions do **not** read `local.settings.json`. You must manually add these in the Azure Portal.

### **Where to find it:**

Portal UI: **Function App** > **Settings** > **Environment variables**.

### **What must be added:**

Add these as "New application settings":

* `AZURE_STORAGE_CONNECTION_STRING`: (The long string starting with *DefaultEndpointsProtocol*)
* `AZURE_SPEECH_KEY`: Your Azure Speech API key.
* `AZURE_SPEECH_REGION`: `eastus` (or your chosen region).
* `DEEPSEEK_API_KEY`: Your DeepSeek API key.
* `TELEGRAM_TOKEN`: Your bot token.
* `TELEGRAM_CHAT_ID`: Your chat/channel ID.

### **What to remove/ignore:**

* Remove any old `OPENAI_API_KEY` if you have switched entirely to DeepSeek.
* Do **not** add `IS_CLOUD` manually; the script detects the environment by checking the `HOME` folder path.

---

## 3. Deploying from VS Code Terminal

Ensure you are logged in via the Azure CLI (`az login`).

1. **Check your architecture**: Ensure the files in `/bin/` are the Linux `amd64` versions.
2. **Publish**:
```bash
func azure functionapp publish text2podcast-service-01

```


*This command zips your code, uploads it, and triggers a remote build. It will automatically install the libraries listed in `requirements.txt`.*

---

## 4. Locating Triggers in the Portal

Once deployed, you can see your functions in the UI.

1. Go to **Overview** > **Functions** tab (bottom of the page).
2. **`reddit_podcast_timer`**: This is the automatic one. You cannot "run" it with a URL; it follows the CRON schedule.
3. **`manual_run`**: Click this > **Get Function Url**. This is the link you use to trigger a run via your browser.

---

## 5. Monitoring: Log Stream & Status

To see what the bot is doing in real-time (e.g., "Synthesizing audio..."):

1. Navigate to **Monitoring** > **Log Stream** in the left-hand menu.
2. **Switch to "App Service Logs"** if "Filesystem Logs" are empty.
3. **Pro Tip**: Keep this window open while you hit the `manual_run` URL in another tab. You will see the Python `print()` statements and any `logging.info()` calls appear here live.

---

## 6. Common Cloud "Gotchas"

* **Permissions**: If you get "Permission Denied" for FFmpeg in the logs, verify that `tts_engine.py` is correctly running the `os.chmod(dest, ... | stat.S_IEXEC)` command.
* **Timeouts**: The `manual_run` URL might show a "Timeout" error in your browser after 230 seconds. **Ignore it.** The job is likely still running in the background on the server (check the Log Stream to confirm).
* **Cold Starts**: The first run after a long break may take 30-60 seconds just to "wake up" the server.
