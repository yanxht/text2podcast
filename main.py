import feedparser
import requests
import os
import config
from datetime import datetime
from time import mktime
# Added rss_generator to the modules
from modules import llm_cleaner, tts_engine, blob_uploader, rss_generator, telegram_bot

def run_pipeline():
    """
    MAIN ORCHESTRATOR:
    1. Scrapes Subreddit RSS feeds for 'Hot' posts.
    2. Filters out MOD posts and short/junk content.
    3. Checks Azure Table Storage to prevent processing duplicate PostIDs.
    4. Coordinates LLM (Clean), TTS (Speak), and Blob (Storage) modules.
    """
    
    # Ensure local directory exists for processing and debugging
    if not os.path.exists(config.LOCAL_BACKUP_PATH):
        os.makedirs(config.LOCAL_BACKUP_PATH)

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PrivateAudioBot/1.0'}
    SKIP_KEYWORDS = ["[MOD POST]", "RULES", "EFFECTIVE IMMEDIATELY", "QUESTION", "TELEGRAM", "SNAPCHAT", "BOTS", "HELP"]

    for sub in config.SUBREDDITS:
        print(f"\n--- Checking Subreddit: r/{sub} ---")
        rss_url = f"https://www.reddit.com/r/{sub}/hot/.rss?t=day"
        
        try:
            res = requests.get(rss_url, headers=headers, timeout=15)
            feed = feedparser.parse(res.text)
        except Exception as e:
            print(f"Fetch failed: {e}")
            continue

        for entry in feed.entries[:10]:
            # --- 1. Basic Filtering (Length and Keywords) ---
            post_id = entry.id.split('_')[-1]
            title_upper = entry.title.upper()
            raw_content = entry.content[0].value if entry.content else ""

            if any(kw in title_upper for kw in SKIP_KEYWORDS) or len(raw_content) < 600:
                print(f"Skipping (Short/Keyword): {entry.title[:40]}...")
                continue

            # --- 2. Metadata Preparation & Duplication Check ---
            raw_author = entry.author_detail.name if 'author_detail' in entry else (entry.author if 'author' in entry else "Unknown")
            user_id = raw_author.replace("u/", "").lstrip("/")
            create_time_iso = datetime.fromtimestamp(mktime(entry.updated_parsed)).isoformat()
            reddit_url = f"https://www.reddit.com/r/{sub}/comments/{post_id}"
            
            post_metadata = {
                "PostId": post_id,
                "UserId": user_id,
                "Title": entry.title,
                "CreateTime": create_time_iso,
                "Subreddit": sub,
                "URL": reddit_url
            }

            # Check Azure Table Storage to see if we've already processed this ID; If not, leave trace in the table for what we are about to process.
            if blob_uploader.check_and_mark_duplicate(sub, post_id, post_metadata, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_TABLE_NAME):
                print(f"Skip existing: {entry.title}")
                continue

            # --- 3. LLM Cleaning & Gender Inference ---
            print(f"Cleaning content: {entry.title}")
            content_json = llm_cleaner.clean_text_via_llm(raw_content, post_metadata, config.DEEPSEEK_API_KEY)
            
            # Use 'SKIP' check as a secondary filter via LLM intelligence
            if not content_json or content_json.get('clean_content', '').upper() == "SKIP":
                print("Skipping: Content filtered by LLM.")
                continue

            clean_story = content_json['clean_content']
            inferred_gender = content_json.get("gender", "Female")

            # --- 4. Markdown Handling (Local Save + Upload) ---
            md_filename = f"{post_id}.md"
            local_md_path = os.path.join(config.LOCAL_BACKUP_PATH, md_filename)

            with open(local_md_path, "w", encoding="utf-8") as f:
                f.write(f"# {entry.title}\n\n")
                f.write(f"- **PostID:** `{post_id}`\n")
                f.write(f"- **UserID:** {user_id}\n")
                f.write(f"- **Subreddit:** r/{sub}\n")
                f.write(f"- **Created:** {create_time_iso}\n")
                f.write(f"- **URL:** [{reddit_url}]({reddit_url})\n")
                f.write(f"- **Gender:** {inferred_gender}\n\n")
                f.write("---\n\n")
                f.write(clean_story)

            blob_uploader.upload_to_blob(local_md_path, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_STORAGE_CONTAINER, "text/markdown")

            # --- 5. Audio Handling (TTS + Upload) & RSS Delivery ---
            mp3_filename = f"{post_id}.mp3"
            local_mp3_path = os.path.join(config.LOCAL_BACKUP_PATH, mp3_filename)
            
            print(f"Synthesizing audio (Gender: {inferred_gender})...")
            if tts_engine.synthesize_audio(clean_story, config.AZURE_SPEECH_KEY, config.AZURE_SPEECH_REGION, local_mp3_path, gender=inferred_gender):
                # Upload the synthesized MP3 to Blob Storage and get the public/private URL
                audio_url = blob_uploader.upload_to_blob(local_mp3_path, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_STORAGE_CONTAINER, "audio/mpeg")
                
                if audio_url:
                    # Package all metadata and audio link for the RSS Feed update
                    rss_packet = {
                        "PostId": post_id,
                        "Title": entry.title,
                        "UserId": user_id,
                        "Subreddit": sub,
                        "Created": create_time_iso,
                        "URL": reddit_url,
                        "CleanContent": clean_story,
                        "MP3_URL": audio_url
                    }
                    
                    # 1. Update feed.xml so Podcast apps see the new episode
                    feed_url = rss_generator.update_rss_feed(
                        config.AZURE_STORAGE_CONNECTION_STRING, 
                        config.AZURE_STORAGE_CONTAINER, 
                        rss_packet
                    )

                    # 2. Send Telegram Notification
                    telegram_bot.send_notification(
                        config.TELEGRAM_TOKEN,
                        config.TELEGRAM_CHAT_ID,
                        rss_packet,
                        local_mp3_path
                    )

                    print(f"✅ Success! RSS Updated: {feed_url}")
                else:
                    print("❌ Audio upload failed, skipping RSS update.")
            else:
                print("❌ TTS Synthesis failed.")

if __name__ == "__main__":
    run_pipeline()