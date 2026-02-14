import os
import re
import html
import config
from azure.storage.blob import BlobServiceClient
from modules import tts_engine, blob_uploader, rss_generator, telegram_bot

def parse_md_content(content):
    """Parses metadata from the Markdown text stored in Blob."""
    
    def get_val(key):
        # Improved regex to handle potential whitespace or formatting quirks
        match = re.search(f"- \*\*{key}:\*\* (.*)", content)
        if match:
            val = match.group(1).strip(" `[]()")
            return html.unescape(val) # Ensure &amp; becomes &
        return "Unknown"

    story_parts = content.split("---")
    clean_story = story_parts[-1].strip() if len(story_parts) > 1 else ""

    # Get the Title (first line, remove '# ')
    first_line = content.split("\n")[0]
    title = first_line.replace("# ", "").strip()

    return {
        "Title": html.unescape(title),
        "PostId": get_val("PostID"),
        "UserId": get_val("UserID"),
        "Subreddit": get_val("Subreddit").replace("r/", ""),
        "Created": get_val("Created"), # This maps to 'CreateTime' logic
        "URL": get_val("URL"),
        "Gender": get_val("Gender"),
        "CleanContent": clean_story
    }

def run_cloud_backfill():
    # Setup Azure Client
    blob_service_client = BlobServiceClient.from_connection_string(config.AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(config.AZURE_STORAGE_CONTAINER)

    print(f"🔍 Scanning Azure Container for missing audio...")

    try:
        blobs = list(container_client.list_blobs())
    except Exception as e:
        print(f"❌ Could not list blobs: {e}")
        return

    md_ids = {b.name.replace(".md", "") for b in blobs if b.name.endswith(".md")}
    mp3_ids = {b.name.replace(".mp3", "") for b in blobs if b.name.endswith(".mp3")}

    missing_audio_ids = md_ids - mp3_ids

    if not missing_audio_ids:
        print("✅ No missing audio found.")
        return

    print(f"Found {len(missing_audio_ids)} stories needing synthesis.")

    for post_id in missing_audio_ids:
        print(f"\n🛠 Processing: {post_id}")

        # 1. Download MD
        blob_client = container_client.get_blob_client(f"{post_id}.md")
        md_text = blob_client.download_blob().readall().decode("utf-8")
        meta = parse_md_content(md_text)

        # 2. Local Temp Path (Workbench)
        # Using tempfile ensures it works on Azure Functions too
        import tempfile
        temp_dir = tempfile.gettempdir()
        local_mp3_path = os.path.join(temp_dir, f"{post_id}.mp3")
        
        # 3. Synthesize with Chunking
        print(f"🎙 Synthesizing: {meta['Title'][:40]}...")
        success = tts_engine.synthesize_audio(
            meta["CleanContent"], 
            config.AZURE_SPEECH_KEY, 
            config.AZURE_SPEECH_REGION, 
            local_mp3_path, 
            gender=meta["Gender"]
        )

        if success:
            # 4. Upload MP3
            audio_url = blob_uploader.upload_to_blob(
                local_mp3_path, 
                config.AZURE_STORAGE_CONNECTION_STRING, 
                config.AZURE_STORAGE_CONTAINER, 
                "audio/mpeg"
            )
            
            # 5. Delivery Packet (Ensuring key names match rss_generator expectations)
            rss_packet = {
                "PostId": meta["PostId"],
                "Title": meta["Title"],
                "UserId": meta["UserId"],
                "Subreddit": meta["Subreddit"],
                "Created": meta["Created"],
                "URL": meta["URL"],
                "CleanContent": meta["CleanContent"],
                "MP3_URL": audio_url
            }

            # Update RSS
            rss_generator.update_rss_feed(
                config.AZURE_STORAGE_CONNECTION_STRING, 
                config.AZURE_STORAGE_CONTAINER, 
                rss_packet
            )
            
            # Notify Telegram (Optional)
            telegram_bot.send_notification(
                config.TELEGRAM_TOKEN, 
                config.TELEGRAM_CHAT_ID, 
                rss_packet, 
                local_mp3_path
            )
            
            # Clean up workbench
            if os.path.exists(local_mp3_path):
                os.remove(local_mp3_path)
            print(f"✅ Successfully backfilled {post_id}")
        else:
            print(f"❌ Synthesis failed for {post_id}")

if __name__ == "__main__":
    run_cloud_backfill()