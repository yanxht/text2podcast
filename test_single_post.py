import os
import requests
import config
import re
from datetime import datetime
from modules import llm_cleaner, tts_engine

# --- TEST CONFIGURATION ---
TARGET_POST_ID = "1qtbtjp"
SUBREDDIT = "LetsNotMeet" 
TEST_OUTPUT_FOLDER = "test_outputs"
USE_LOCAL_MD_IF_AVAILABLE = False  

def parse_local_markdown(file_path):
    """
    Loads a text file from your computer to test the TTS engine 
    without needing an internet connection to Reddit.
    """

    with open(file_path, "r", encoding="utf-8") as f:
        full_text = f.read()
    
    title_match = re.search(r'^#\s+(.*)', full_text, re.MULTILINE)
    title = title_match.group(1) if title_match else "Unknown Title"
    
    def get_meta(field):
        match = re.search(fr'{field}:\*\*?\s*`?(.*?)`?(?:\n|$)', full_text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # If the value looks like [text](link), extract just the link
            link_match = re.search(r'\[.*?\]\((.*?)\)', val)
            if link_match:
                return link_match.group(1)
            return val
        return None

    meta_data = {
        "UserId": get_meta("UserID") or "Unknown",
        "Subreddit": (get_meta("Subreddit") or "Unknown").replace("r/", ""),
        "Created": get_meta("Created") or "Unknown",
        "URL": get_meta("URL") or "Unknown",
        "Gender": get_meta("Gender") # Deterministic choice for tts_engine
    }
    
    parts = full_text.split("---")
    clean_content = parts[-1].strip() if len(parts) > 1 else full_text
    
    return title, clean_content, meta_data

def run_single_test():
    """
    End-to-end local test. Output goes to the 'test_outputs' folder.
    Used for checking voice quality and gender inference accuracy.
    """

    if not os.path.exists(TEST_OUTPUT_FOLDER):
        os.makedirs(TEST_OUTPUT_FOLDER)

    print(f"--- Starting Advanced Test: {TARGET_POST_ID} ---")
    backup_md_path = os.path.join(config.LOCAL_BACKUP_PATH, f"{TARGET_POST_ID}.md")
    
    clean_story = None
    gender = "Female"
    title = ""
    meta_data = {}

    # 1. ATTEMPT LOCAL RETRIEVAL
    if USE_LOCAL_MD_IF_AVAILABLE and os.path.exists(backup_md_path):
        print(f"📖 LOCAL-FIRST: Found {backup_md_path}. Using all local results.")
        title, clean_story, meta_data = parse_local_markdown(backup_md_path)
        gender = meta_data.get("Gender", "Female")
    else:
        # 2. FALLBACK TO LLM PARSING & CLEANING
        print(f"🌐 FETCH-MODE: Retrieving from Reddit and invoking LLM...")
        url = f"https://www.reddit.com/r/{SUBREDDIT}/comments/{TARGET_POST_ID}.json"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PrivateAudioBot/1.0'}
        
        try:
            res = requests.get(url, headers=headers)
            res.raise_for_status()
            # Reddit API for a single post returns a list of two objects (post, comments)
            data = res.json()
            post_data = data[0]['data']['children'][0]['data']
            
            raw_content = post_data.get('selftext', '')
            title = post_data.get('title', '')
            
            # --- Sync logic with main.py ---
            raw_author = post_data.get('author', 'Unknown')
            user_id = raw_author.replace("u/", "").lstrip("/")
            
            created_utc = post_data.get('created_utc', 0)
            created_iso = datetime.fromtimestamp(created_utc).isoformat() if created_utc else "Unknown"

            # 1. Define meta_data fully BEFORE passing it anywhere
            meta_data = {
                "PostId": TARGET_POST_ID,
                "UserId": user_id,
                "Subreddit": SUBREDDIT,
                "Created": created_iso,
                "URL": f"https://www.reddit.com/r/{SUBREDDIT}/comments/{TARGET_POST_ID}",
                "Title": title
            }
            
            # 2. Invoke LLM with the defined metadata
            print("Invoking LLM for cleaning and gender inference...")
            llm_res = llm_cleaner.clean_text_via_llm(raw_content, meta_data, config.DEEPSEEK_API_KEY)
            
            if llm_res:
                clean_story = llm_res.get('clean_content', '')
                gender = llm_res.get("gender", "Female")
                meta_data["Gender"] = gender # Update meta_data with the inference result
            else:
                print("❌ LLM returned no result.")
                return
            
        except Exception as e:
            print(f"❌ Error during Reddit Fetch/LLM: {e}")
            import traceback
            traceback.print_exc() # This will help find the exact line number if it fails again
            return

    # 3. SAVE THE TEST RECORD (Guarantees Gender is in the test output)
    test_md_path = os.path.join(TEST_OUTPUT_FOLDER, f"{TARGET_POST_ID}_test.md")
    with open(test_md_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"- **PostID:** `{TARGET_POST_ID}`\n")
        f.write(f"- **UserID:** {meta_data['UserId']}\n")
        f.write(f"- **Subreddit:** r/{meta_data['Subreddit']}\n")
        f.write(f"- **Created:** {meta_data['Created']}\n")
        f.write(f"- **URL:** [{meta_data['URL']}]({meta_data['URL']})\n")
        f.write(f"- **Gender:** {gender}\n\n")
        f.write("---\n\n")
        f.write(clean_story)

    # 4. DOWNSTREAM AUDIO SYNTHESIS
    print(f"🎙️ Using Gender: {gender} (Source: {'Local Markdown' if USE_LOCAL_MD_IF_AVAILABLE else 'LLM Inference'})")
    mp3_filename = f"{TARGET_POST_ID}_test.mp3"
    local_mp3_path = os.path.join(TEST_OUTPUT_FOLDER, mp3_filename)
    
    if tts_engine.synthesize_audio(clean_story, config.AZURE_SPEECH_KEY, config.AZURE_SPEECH_REGION, local_mp3_path, gender=gender):
        print(f"✅ SUCCESS: Final combined audio saved to {local_mp3_path}")

if __name__ == "__main__":
    run_single_test()