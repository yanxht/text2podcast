# 🎙️ Reddit-to-Podcast Automation (Text2Podcast)

**[Hybrid Cloud/Local System]** An automated pipeline that scrapes Reddit, cleans text using DeepSeek AI, synthesizes a podcast-style audio file via Azure TTS, and publishes it to a private RSS feed and Telegram channel.

---

## 🏗️ System Architecture

The project is built to handle the transition from a local development environment to a restricted Azure Functions (Linux) environment.

### **The "Future Me" Cheat Sheet**

* **Audio Engine:** Uses `pydub` + `Azure Speech SDK`.
* **The FFmpeg Workaround:** Azure Functions are read-only. We bundle `amd64` static binaries in `/bin`. The code automatically copies them to `/tmp` and sets executable permissions on every run.
* **Memory:** Uses **Azure Table Storage** (`PostHistory`) to ensure we never process the same Reddit post twice.
* **Hosting:** Audio files and the `feed.xml` live in **Azure Blob Storage**.

---

## 📁 File Directory & Roles

### **Core Orchestration**

* **`function_app.py` [Cloud Only]:** The entry point. Contains the Timer Trigger (hourly) and the HTTP Trigger (manual URL).
* **`main.py` [Hybrid]:** The "Brain" that coordinates the modules.
* **`config.py` [Hybrid]:** Centralizes keys. **Crucial:** Detects `IS_CLOUD` to adjust file paths automatically.

### **Heavy Lifter Modules (`/modules`)**

* **`llm_cleaner.py`:** Uses DeepSeek to turn Reddit HTML into a clean script. Includes a "JSON Rescue" regex for cut-off AI responses.
* **`tts_engine.py`:** Handles the "Nuclear" FFmpeg setup and synthesizes the voice.
* **`rss_generator.py`:** Updates the XML feed so the podcast appears in your app.
* **`telegram_bot.py`:** Sends the final MP3 to your phone. **Note:** `parse_mode` is disabled to prevent crashes from weird characters in titles.

### **Maintenance & Dev Tools**

* **`test_single_post.py` [Local Only]:** Use this to test a specific PostID on your laptop without touching the cloud.
* **`manual_trigger.py` [Hybrid]:** Force-processes specific IDs into the production feed.
* **`sync_feed_logics.py` [Hybrid]:** Use this if the RSS feed and Blob storage get out of sync.

---

## 🚀 Deployment & Updates

### **1. Local Setup**

1. Ensure you have a **Python 3.12+** environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Ensure `local.settings.json` matches your `config.py` keys.

### **2. Deploying to Azure**

Use the Azure Functions Core Tools to publish:

```bash
func azure functionapp publish text2podcast-service-01

```

**Fetch Manual Trigger URL:**
To get your secret URL for manual runs (including the required API key), run:

```bash
func azure functionapp function show --name manual_run --resource-group [Your-RG] --app-name text2podcast-service-01 --show-keys

```

---

## 🔗 Output Links

* **RSS Feed:** `https://text2podcastbox.blob.core.windows.net/podcasts/feed.xml`
* **Function App Dashboard:** `https://portal.azure.com` (Search for `text2podcast-service-01`)

---

**Project status: Closed & Functional.** *Last updated: February 2026*
