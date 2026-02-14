# =================================================================
# TELEGRAM NOTIFICATION BOT
# Purpose: Sends instant alerts and audio files to a Telegram Chat.
# =================================================================

import requests
import logging

def send_notification(token, chat_id, metadata, mp3_path):
    """
    Uploads the final MP3 to Telegram along with a formatted caption.
    Note: parse_mode is commented out to prevent crashes from 
          unpredictable characters (like [ or _ ) in Reddit titles.
    """
    
    caption = (
        f"🎙 **New Podcast Episode Published!**\n\n"
        f"**Title:** {metadata['Title']}\n"
        f"**Author:** u/{metadata['UserId']}\n"
        f"**Subreddit:** r/{metadata['Subreddit']}\n\n"
        f"🔗 [Original Reddit Post]({metadata['URL']})"
    )

    url = f"https://api.telegram.org/bot{token}/sendAudio"
    
    try:
        with open(mp3_path, 'rb') as audio:
            payload = {
                'chat_id': chat_id,
                'caption': caption
                #'parse_mode': 'Markdown' # parse_mode removed to treat everything as plain text
            }
            files = {'audio': audio}
            response = requests.post(url, data=payload, files=files)
            
        if response.status_code == 200:
            logging.info("✅ Telegram notification sent.")
        else:
            logging.error(f"❌ Telegram failed: {response.text}")
    except Exception as e:
        logging.error(f"❌ Telegram error: {e}")