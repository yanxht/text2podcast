import os
import requests
import config
from datetime import datetime
from modules import llm_cleaner, tts_engine, blob_uploader, rss_generator, telegram_bot

def fetch_reddit_post_by_id(post_id):
    """
    Uses Reddit's JSON API to pull full text and metadata for a specific ID.
    Bypasses the RSS feed to target a single known story.
    """

    url = f"https://www.reddit.com/comments/{post_id}.json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PrivateAudioBot/1.0'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        
        # Reddit returns a list: [post_data, comment_data]
        post_info = data[0]['data']['children'][0]['data']
        
        return {
            "PostId": post_id,
            "Title": post_info['title'],
            "UserId": post_info['author'],
            "Subreddit": post_info['subreddit'],
            "Created": datetime.fromtimestamp(post_info['created_utc']).isoformat(),
            "URL": f"https://www.reddit.com{post_info['permalink']}",
            "RawContent": post_info['selftext']
        }
    except Exception as e:
        print(f"❌ Error fetching post {post_id}: {e}")
        return None

def process_specific_posts(post_ids):
    """
    A loop wrapper that runs the full run_pipeline logic on a specific 
    list of IDs provided by the user.
    """
    
    if not os.path.exists(config.LOCAL_BACKUP_PATH):
        os.makedirs(config.LOCAL_BACKUP_PATH)

    for pid in post_ids:
        print(f"\n🚀 Manually triggering: {pid}")
        
        # 1. Fetch Data
        post_data = fetch_reddit_post_by_id(pid)
        if not post_data or len(post_data['RawContent']) < 100:
            print(f"⚠️ Skipping {pid}: Could not fetch content or post is empty.")
            continue

        # 2. Setup Metadata for existing modules
        post_metadata = {
            "PostId": pid,
            "UserId": post_data['UserId'],
            "Title": post_data['Title'],
            "CreateTime": post_data['Created'],
            "Subreddit": post_data['Subreddit'],
            "URL": post_data['URL']
        }

        # Disable the de-dup intentionally to assure triggering on specific IDs, even if they were processed before. In a real scenario, you might want to keep this check.
        # As a result, any processed id will not get updated in the Azure Table Storage.
        #if blob_uploader.check_and_mark_duplicate(sub, post_id, post_metadata, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_TABLE_NAME):
        #    print(f"Skip existing: {entry.title}")
        #    continue
        
        # 3. LLM Cleaning
        print(f"Cleaning content: {post_data['Title']}")
        content_json = llm_cleaner.clean_text_via_llm(post_data['RawContent'], post_metadata, config.DEEPSEEK_API_KEY)
        
        if not content_json or content_json.get('clean_content', '').upper() == "SKIP":
            print("Skipping: Content filtered by LLM.")
            continue

        clean_story = content_json['clean_content']
        inferred_gender = content_json.get("gender", "Female")

        # 4. Save Markdown & Upload
        md_filename = f"{pid}.md"
        local_md_path = os.path.join(config.LOCAL_BACKUP_PATH, md_filename)
        with open(local_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {post_data['Title']}\n\n")
            f.write(f"- **PostID:** `{pid}`\n")
            f.write(f"- **UserID:** {post_data['UserId']}\n")
            f.write(f"- **Subreddit:** r/{post_data['Subreddit']}\n")
            f.write(f"- **Created:** {post_data['Created']}\n")
            f.write(f"- **URL:** [{post_data['URL']}]({post_data['URL']})\n")
            f.write(f"- **Gender:** {inferred_gender}\n\n")
            f.write("---\n\n")
            f.write(clean_story)

        blob_uploader.upload_to_blob(local_md_path, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_STORAGE_CONTAINER, "text/markdown")

        # 5. Audio Handling & Delivery
        mp3_filename = f"{pid}.mp3"
        local_mp3_path = os.path.join(config.LOCAL_BACKUP_PATH, mp3_filename)
        
        print(f"Synthesizing audio (Gender: {inferred_gender})...")
        if tts_engine.synthesize_audio(clean_story, config.AZURE_SPEECH_KEY, config.AZURE_SPEECH_REGION, local_mp3_path, gender=inferred_gender):
            audio_url = blob_uploader.upload_to_blob(local_mp3_path, config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_STORAGE_CONTAINER, "audio/mpeg")
            
            if audio_url:
                rss_packet = {
                    "PostId": pid,
                    "Title": post_data['Title'],
                    "UserId": post_data['UserId'],
                    "Subreddit": post_data['Subreddit'],
                    "Created": post_data['Created'],
                    "URL": post_data['URL'],
                    "CleanContent": clean_story,
                    "MP3_URL": audio_url
                }
                
                # Update RSS
                feed_url = rss_generator.update_rss_feed(config.AZURE_STORAGE_CONNECTION_STRING, config.AZURE_STORAGE_CONTAINER, rss_packet)
                # Send Telegram
                telegram_bot.send_notification(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID, rss_packet, local_mp3_path)
                
                print(f"✅ Success! Manual task complete: {pid}")

if __name__ == "__main__":
    # Add the Post IDs you want to process here
    target_ids = ["1qtbtjp"] 
    process_specific_posts(target_ids)