import os
import re
import html
import config
import xml.etree.ElementTree as ET
from azure.storage.blob import BlobServiceClient
from modules import rss_generator, telegram_bot

def get_ids_from_rss(container_client):
    """
    Reads the existing feed.xml from Azure Blob Storage to identify 
    which stories are already published.
    """

    try:
        blob_client = container_client.get_blob_client("feed.xml")
        xml_data = blob_client.download_blob().readall()
        root = ET.fromstring(xml_data)
        # GUIDs in our feed are the PostIds
        return {guid.text for guid in root.findall(".//guid")}
    except Exception as e:
        print(f"⚠️ Feed.xml not found or empty. Starting fresh. (Error: {e})")
        return set()

def parse_md_from_blob(blob_client):
    """
    Backfill Logic: Reconstructs metadata by reading the .md files 
    previously saved to Azure. Prevents needing to re-run the LLM.
    """

    content = blob_client.download_blob().readall().decode("utf-8")
    
    def get_val(key):
        # Corrected: rf prefix for raw f-string, removed extra parentheses
        pattern = rf"- \*\*{key}:\*\* (.*)"
        match = re.search(pattern, content)
        if match:
            return html.unescape(match.group(1).strip(" `[]()"))
        return "Unknown"

    story_parts = content.split("---")
    clean_story = story_parts[-1].strip() if len(story_parts) > 1 else ""
    title = content.split("\n")[0].replace("# ", "").strip()

    return {
        "Title": html.unescape(title),
        "PostId": get_val("PostID"),
        "UserId": get_val("UserID"),
        "Subreddit": get_val("Subreddit").replace("r/", ""),
        "Created": get_val("Created"),
        "URL": get_val("URL"),
        "CleanContent": clean_story
    }

def sync_missing_to_feed():
    """
    Compares Storage (MP3s) vs RSS (feed.xml). 
    If a file exists in storage but not the feed, it adds it back.
    """
    
    # 1. Initialize Azure Client
    blob_service_client = BlobServiceClient.from_connection_string(config.AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(config.AZURE_STORAGE_CONTAINER)

    print("🔍 Checking RSS feed against storage content...")

    # 2. Get existing state
    existing_guids = get_ids_from_rss(container_client)
    
    # List blobs and filter for pairs
    all_blobs = list(container_client.list_blobs())
    md_ids = {b.name.replace(".md", "") for b in all_blobs if b.name.endswith(".md")}
    mp3_ids = {b.name.replace(".mp3", "") for b in all_blobs if b.name.endswith(".mp3")}

    # 3. Identify completed pairs that are NOT in the RSS feed
    ready_to_sync = (md_ids & mp3_ids) - existing_guids

    if not ready_to_sync:
        print("✅ RSS feed is perfectly in sync with storage.")
        return

    print(f"🛠 Found {len(ready_to_sync)} episodes to add to RSS/Telegram.")

    for post_id in ready_to_sync:
        print(f"Appending: {post_id}...")
        
        # 4. Get Metadata
        md_blob = container_client.get_blob_client(f"{post_id}.md")
        meta = parse_md_from_blob(md_blob)
        
        # 5. Construct Audio URL
        audio_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{config.AZURE_STORAGE_CONTAINER}/{post_id}.mp3"

        # 6. Build RSS Packet
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

        # 7. Update RSS
        rss_generator.update_rss_feed(
            config.AZURE_STORAGE_CONNECTION_STRING, 
            config.AZURE_STORAGE_CONTAINER, 
            rss_packet
        )
        
        # 8. Download temp copy for Telegram notification
        local_mp3 = os.path.join(config.LOCAL_BACKUP_PATH, f"{post_id}.mp3")
        
        try:
            if not os.path.exists(local_mp3):
                with open(local_mp3, "wb") as f:
                    f.write(container_client.get_blob_client(f"{post_id}.mp3").download_blob().readall())

            telegram_bot.send_notification(
                config.TELEGRAM_TOKEN, 
                config.TELEGRAM_CHAT_ID, 
                rss_packet, 
                local_mp3
            )
        except Exception as e:
            print(f"⚠️ Telegram notification failed for {post_id}: {e}")
        
        print(f"✅ Synced: {meta['Title']}")

if __name__ == "__main__":
    sync_missing_to_feed()