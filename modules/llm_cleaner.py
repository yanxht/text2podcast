# =================================================================
# LLM CLEANER (DEEPSEEK / OPENAI)
# Purpose: Extracts narrative and infers gender from raw Reddit content.
# Defensive Logic: Includes 'JSON Rescue' regex to handle cases where 
#                 the AI response is cut off or malformed.
# =================================================================

from openai import OpenAI
import json
import re

def clean_text_via_llm(raw_html, post_info, api_key):
    """
    Sends raw post data to the LLM with a strict persona prompt.
    Returns: A structured dictionary with cleaned text and inferred gender.
    If JSON parsing fails, the 'JSON Rescue' block manually extracts data.
    """
    
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    prompt = f"""
    You are a professional data processing assistant. Please process the following Reddit post content.
    
    Metadata:
    PostId: {post_info['PostId']} | UserId: {post_info['UserId']} | Title: {post_info['Title']}
    
    Task Requirements:
    1. **Extract Body**: Extract only the narrative. **Strictly preserve original wording.** No rewriting or polishing.
    2. **Remove Noise**: Strip HTML tags, Reddit-specific meta (Edit:, TL;DR, NSFW), and author's notes.
    3. **Content Filtering**: If content is rules/meta/announcements, set clean_content to "SKIP".
    4. **Gender Inference**: Infer narrator's gender ("Male", "Female", or "Unknown").
    5. **Output JSON**: Return ONLY a JSON object with keys: PostId, UserId, Title, clean_content, gender.

    Content:
    {raw_html}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a precise content extraction expert. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        raw_content = response.choices[0].message.content.strip()
        
        # --- DEFENSIVE PARSING LOGIC ---
        
        # 1. Strip Markdown wrappers if present
        json_str = re.sub(r'^```json\s*|\s*```$', '', raw_content, flags=re.MULTILINE)

        try:
            # 2. Try standard JSON load
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 3. Handle "Unterminated String" by escaping raw newlines inside the string
            # This replaces actual enters with the \n character
            sanitized = json_str.replace('\n', '\\n')
            # Fix back structural braces that we accidentally escaped
            sanitized = sanitized.replace('{\\n', '{').replace('\\n}', '}')
            
            try:
                return json.loads(sanitized)
            except Exception:
                # 4. FINAL RESCUE: Regex Extraction
                # If JSON is totally broken (cutoff), manually grab the fields
                print(f"⚠️ JSON Rescue initiated for {post_info['PostId']}...")
                
                # Extract gender (usually short, likely to have finished)
                gender_match = re.search(r'"gender":\s*"(.*?)"', json_str)
                gender = gender_match.group(1) if gender_match else "Unknown"
                
                # Extract clean_content (handles missing closing quote)
                content_match = re.search(r'"clean_content":\s*"(.*)', json_str, re.DOTALL)
                clean_content = "SKIP"
                if content_match:
                    clean_content = content_match.group(1)
                    # Remove trailing JSON debris if it exists
                    clean_content = re.sub(r'"\s*,\s*"gender".*|"\s*}.*', '', clean_content, flags=re.DOTALL).strip()
                    # Final cleanup of escaped chars
                    clean_content = clean_content.replace('\\n', '\n').replace('\\"', '"')

                return {
                    "PostId": post_info['PostId'],
                    "UserId": post_info.get('UserId', 'Unknown'),
                    "Title": post_info.get('Title', 'Unknown'),
                    "clean_content": clean_content,
                    "gender": gender
                }

    except Exception as e:
        print(f"LLM Cleaning failed for Post {post_info['PostId']}: {e}")
        return None