# =================================================================
# TTS ENGINE (AZURE SPEECH SDK + PYDUB)
# Purpose: Synthesizes text to MP3 and handles audio stitching.
# Special Logic: Automatically migrates FFmpeg binaries to /tmp/ 
#                and sets executable permissions for Azure Linux.
# =================================================================

import os
import stat
import shutil
import platform
import config

"""
# 1. SETUP PATHS FIRST
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_ffmpeg = os.path.join(base_path, "bin", "ffmpeg")
src_ffprobe = os.path.join(base_path, "bin", "ffprobe")
dest_ffmpeg = "/tmp/ffmpeg"
dest_ffprobe = "/tmp/ffprobe"

# 2. MOVE THE BINARIES BEFORE IMPORTING PYDUB
if os.path.exists(src_ffmpeg):
    for src, dest in [(src_ffmpeg, dest_ffmpeg), (src_ffprobe, dest_ffprobe)]:
        if not os.path.exists(dest):
            shutil.copy2(src, dest)
            os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)

# 3. FORCE ENVIRONMENT VARIABLES
# This is the "Nuclear" part. pydub looks at PATH if its internal check fails.
os.environ["PATH"] += os.pathsep + "/tmp"
os.environ["PATH"] += os.pathsep + "/opt/homebrew/bin" # For your Mac

# 4. NOW IMPORT PYDUB
from pydub import AudioSegment

# 5. EXPLICITLY SET THE PATHS AGAIN JUST IN CASE
if os.path.exists(dest_ffmpeg):
    AudioSegment.converter = dest_ffmpeg
    AudioSegment.ffprobe = dest_ffprobe
elif os.path.exists("/opt/homebrew/bin/ffmpeg"):
    AudioSegment.converter = "/opt/homebrew/bin/ffmpeg"
    AudioSegment.ffprobe = "/opt/homebrew/bin/ffprobe"
"""

# 1. SETUP PATHS
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_ffmpeg = os.path.join(base_path, "bin", "ffmpeg")
src_ffprobe = os.path.join(base_path, "bin", "ffprobe")
dest_ffmpeg = "/tmp/ffmpeg"
dest_ffprobe = "/tmp/ffprobe"

# 2. THE CLOUD "DANCE" (Only runs on Azure)
if config.IS_CLOUD and os.path.exists(src_ffmpeg):
    for src, dest in [(src_ffmpeg, dest_ffmpeg), (src_ffprobe, dest_ffprobe)]:
        if not os.path.exists(dest):
            shutil.copy2(src, dest)
            os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)

# 3. THE NUCLEAR PATH INJECTION
# We inject both the cloud temp path AND your Mac's Homebrew path
os.environ["PATH"] += os.pathsep + "/tmp"
os.environ["PATH"] += os.pathsep + "/opt/homebrew/bin"

# 4. NOW IMPORT PYDUB
from pydub import AudioSegment

# 5. EXPLICIT OVERRIDE (Double-Lock Security)
if platform.system() == "Darwin": 
    # Force Mac to use system ffmpeg (prevents the 'Exec format error')
    AudioSegment.converter = "ffmpeg"
    AudioSegment.ffprobe = "ffprobe"
    print("💻 Mac: Forced system FFmpeg path.")
elif config.IS_CLOUD:
    # Force Azure to use the /tmp binaries we just moved
    AudioSegment.converter = dest_ffmpeg
    AudioSegment.ffprobe = dest_ffprobe
    print("☁️ Azure: Forced /tmp/ffmpeg path.")

# Rest of your imports (speechsdk, langid, etc.)
import azure.cognitiveservices.speech as speechsdk
import langid
from xml.sax.saxutils import escape

VOICE_MAP = {
    "en-US": {
        "Female": "en-US-AvaMultilingualNeural",
        "Male": "en-US-AndrewMultilingualNeural",
        "Unknown": "en-US-AvaMultilingualNeural"
    },
    "zh-CN": {
        "Female": "zh-CN-XiaoxiaoMultilingualNeural",
        "Male": "zh-CN-YunyiMultilingualNeural",
        "Unknown": "zh-CN-XiaoxiaoMultilingualNeural"
    }
}

def synthesize_audio(text, speech_key, service_region, output_path, gender="Female", voice_name=None, rate="0.92"):
    """
    1. Splits long stories into chunks (Azure TTS has character limits).
    2. Synthesizes each chunk into a temporary MP3 file.
    3. Uses Pydub/FFmpeg to merge chunks into a single high-quality podcast file.
    4. Cleans up temporary chunk files after successful export.
    """

    # Convert to Absolute Path to ensure Azure/FFmpeg don't get lost
    abs_output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(abs_output_path)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    # Ensure standard MP3 output format
    speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)

    if not voice_name:
        lang, _ = langid.classify(text)
        locale = "zh-CN" if lang == 'zh' else "en-US"
        voice_name = VOICE_MAP.get(locale, VOICE_MAP["en-US"]).get(gender, VOICE_MAP["en-US"]["Female"])

    # Chunking 
    MAX_CHUNK_SIZE = 3000
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""
    for p in paragraphs:
        p = p.strip()
        if not p: continue

        # Hard break for "Wall of Text" paragraphs
        if len(p) > MAX_CHUNK_SIZE:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            for i in range(0, len(p), MAX_CHUNK_SIZE):
                chunks.append(p[i : i + MAX_CHUNK_SIZE])
            continue

        if len(current_chunk) + len(p) < MAX_CHUNK_SIZE:
            current_chunk += p + "\n"
        else:
            chunks.append(current_chunk.strip())
            current_chunk = p + "\n"
    if current_chunk:
        chunks.append(current_chunk.strip())

    combined_audio = AudioSegment.empty()
    temp_files = []

    try:
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip(): continue
            
            # Use absolute path for temp files
            temp_file = f"{abs_output_path}_temp_{i}.mp3"
            temp_files.append(temp_file)
            
            safe_text = escape(chunk_text)
            ssml_text = f"""
            <speak version='1.0' xml:lang='en-US' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts'>
                <voice name='{voice_name}'>
                    <prosody rate='{rate}'>
                        {safe_text}
                    </prosody>
                </voice>
            </speak>
            """
            
            audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_file)
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
            
            result = synthesizer.speak_ssml_async(ssml_text).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                segment = AudioSegment.from_file(temp_file, format="mp3")
                # --- DEBUGGING: Uncomment to verify chunk durations ---
                # print(f"Chunk {i} synthesized. Duration: {len(segment)/1000:.2f}s") 
                combined_audio += segment
            else:
                print(f"❌ Chunk {i} failed: {result.reason}")
                if result.reason == speechsdk.ResultReason.Canceled:
                    details = result.cancellation_details
                    print(f"Reason: {details.reason} | Details: {details.error_details}")
                return False

        combined_audio.export(abs_output_path, format="mp3")
        return True

    except Exception as e:
        print(f"🔥 CRITICAL CRASH in synthesize_audio: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

    finally:
        for f in temp_files:
            if os.path.exists(f):
                # keep intermediate files for debugging if needed, comment out the next line to retain them
                # print(f"Retained: {f}")
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"Warning: Could not delete temp file {f}: {e}")