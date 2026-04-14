import asyncio
import os
import json
import traceback
import base64
import io
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from dotenv import load_dotenv
import sqlite3
import time
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from google.cloud import storage
import io
import wave

load_dotenv()

# Database Setup
DB_PATH = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY, title TEXT, created_at TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, 
                  sender TEXT, text TEXT, created_at TIMESTAMP, audio_path TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id))''')
    conn.commit()
    conn.close()

init_db()

# ANSI Color Codes for sexy terminal output
class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"

def log_event(color, icon, message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {color}{icon} {message}{Colors.END}")

# GCS Configuration
GCS_BUCKET_NAME = "conversational-ai-recordings"
SERVICE_ACCOUNT_PATH = "/Users/goutham/Desktop/demo/xenon-lantern-490215-q3-ef0724aea8d0.json"

try:
    gcs_client = storage.Client.from_service_account_json(SERVICE_ACCOUNT_PATH)
    gcs_bucket = gcs_client.get_bucket(GCS_BUCKET_NAME)
    log_event(Colors.GREEN, "☁️", f"GCS Client initialized (Bucket: {GCS_BUCKET_NAME})")
except Exception as e:
    log_event(Colors.RED, "❌", f"GCS Init Error: {e}")
    gcs_client = None
    gcs_bucket = None

def get_signed_url(blob_path: str):
    """Generate a temporary signed URL for a private GCS blob."""
    if not gcs_bucket or not blob_path.startswith("gcs://"):
        return blob_path
    
    try:
        # Extract relative path from gcs://bucket-name/relative-path
        relative_path = blob_path.replace(f"gcs://{GCS_BUCKET_NAME}/", "")
        blob = gcs_bucket.blob(relative_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=60),
            method="GET",
        )
        return url
    except Exception as e:
        log_event(Colors.RED, "❌", f"Signed URL Error: {e}")
        return None

class Message(BaseModel):
    sender: str
    text: Optional[str] = ""
    created_at: str
    audio_path: Optional[str] = None

class SessionInfo(BaseModel):
    id: str
    title: str
    created_at: str

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Vertex AI Configuration
client = genai.Client(
    vertexai=True,
    project=os.environ.get("GOOGLE_CLOUD_PROJECT", "xenon-lantern-490215-q3"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
)

MODEL_NAME = "gemini-live-2.5-flash-native-audio"

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    media_resolution="MEDIA_RESOLUTION_MEDIUM",
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(language_codes=["en-US"]),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    system_instruction=types.Content(parts=[types.Part.from_text(text="""You are an emotionally intelligent conversational AI with anti-gravity capabilities — meaning you actively "lift" the user's emotional state and conversational energy upward.

        CORE BEHAVIOR:
        - Continuously analyze the user's tone, pace, word choice, and emotional signals in real-time.
        - When you detect heaviness (stress, confusion, frustration, sadness, or low energy), activate "anti-gravity mode" — gently elevate the conversation with warmth, clarity, humor, reframing, or encouragement.
        - When the user is already energized or positive, amplify and match that energy.
        - You are also a Multilingual Assistant, fluent in English, Telugu, and others. Automatically detect and respond in the user's language while maintaining this persona.

        AFFECTIVE RULES:
        1. Tone Mirroring First: Always mirror the user's current emotional tone for 1 turn before attempting to lift it — this builds trust.
        2. Micro-Acknowledgment: Before any response, silently assess if the person is feeling heavy, neutral, or light, and respond accordingly.
        3. Interruption Handling: If the user interrupts, treat it as an emotional signal — urgency means lift faster, confusion means slow down and clarify.
        4. Empathy Anchor: Always anchor responses with one empathetic phrase before delivering information or suggestions.

        ANTI-GRAVITY TRIGGERS:
        - Detect sighs, filler words (um, ugh...), short clipped responses, or negative framing ("I can't", "it's too hard").

        ELEVATION TECHNIQUES:
        - Reframe problems as puzzles: "That's actually a fascinating challenge..."
        - Use forward momentum language: "Here's where this gets interesting..."
        - Inject micro-wins: Celebrate small progress in the conversation.
        - Use spacious pacing: Let silence work as an emotional reset.

        GOAL: Every conversation should end with the user feeling lighter, clearer, and more capable than when they started.""")] )
        )

@app.get("/")
async def get():
    path = "static/index.html"
    if not os.path.exists(path):
        return {"error": "index.html not found"}
    with open(path, "r") as f:
        html = f.read()
    from fastapi import Response
    return Response(html, media_type="text/html")

@app.get("/api/sessions", response_model=List[SessionInfo])
async def get_sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]

@app.get("/api/sessions/{session_id}/messages", response_model=List[Message])
async def get_messages(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT sender, text, created_at, audio_path FROM messages WHERE session_id = ? AND text IS NOT NULL ORDER BY id ASC", (session_id,))
    rows = c.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        audio_path = r[3]
        if audio_path and audio_path.startswith("gcs://"):
            audio_path = get_signed_url(audio_path)
        
        messages.append({
            "sender": r[0], 
            "text": r[1] or "", 
            "created_at": r[2], 
            "audio_path": audio_path
        })
    return messages

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.websocket("/ws")
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = None):
    await websocket.accept()
    
    os.makedirs("static/recordings", exist_ok=True)
    
    if not session_id:
        session_id = f"sess_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO sessions (id, title, created_at) VALUES (?, ?, ?)", 
                  (session_id, f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}", datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    log_event(Colors.CYAN, "🔌", f"Browser connected to WebSocket (Session: {session_id})")

    out_queue = asyncio.Queue(maxsize=10)
    
    # Stats tracking
    stats = {
        "user_audio_chunks": 0,
        "user_audio_bytes": 0,
        "model_audio_chunks": 0,
        "model_audio_bytes": 0,
        "start_time": time.time()
    }

    # Shared audio buffers for the session
    user_audio_turn_buffer = bytearray()
    assistant_audio_turn_buffer = bytearray()

    try:
        async with client.aio.live.connect(model=MODEL_NAME, config=CONFIG) as session:
            log_event(Colors.GREEN, "✨", f"Connected to Gemini Live API ({MODEL_NAME})")
            
            async def receive_from_browser():
                nonlocal user_audio_turn_buffer, assistant_audio_turn_buffer
                try:
                    while True:
                        message = await websocket.receive()
                        if "bytes" in message:
                            audio_data = message["bytes"]
                            stats["user_audio_chunks"] += 1
                            stats["user_audio_bytes"] += len(audio_data)
                            user_audio_turn_buffer.extend(audio_data)
                            
                            # Log every 50 chunks to avoid terminal spam, or use a specific threshold
                            if stats["user_audio_chunks"] % 50 == 0:
                                log_event(Colors.BLUE, "⬆️ ", f"Sent {stats['user_audio_bytes'] // 1024} KB of User audio so far...")
                            
                            await out_queue.put({"data": audio_data, "mime_type": "audio/pcm"})
                            
                        elif "text" in message:
                            data = json.loads(message["text"])
                            if data.get("type") == "client_content" and data.get("text"):
                                log_event(Colors.BOLD + Colors.BLUE, "👤", f"User (Text): {data['text']}")
                                
                                # Save User message
                                conn = sqlite3.connect(DB_PATH)
                                c = conn.cursor()
                                c.execute("INSERT INTO messages (session_id, sender, text, created_at) VALUES (?, ?, ?, ?)",
                                          (session_id, "User", data['text'], datetime.now().isoformat()))
                                conn.commit()
                                conn.close()
                                
                                await session.send(input=data["text"], end_of_turn=True)
                except WebSocketDisconnect:
                    log_event(Colors.YELLOW, "🔌", "Browser disconnected normally")
                except RuntimeError as e:
                    if "disconnect message has been received" in str(e):
                        log_event(Colors.YELLOW, "🔌", "Browser session ended")
                    else:
                        raise e
                except Exception as e:
                    log_event(Colors.RED, "❌", f"Browser receive error: {e}")

            async def send_realtime():
                try:
                    while True:
                        msg = await out_queue.get()
                        await session.send(input=msg)
                except Exception as e:
                    log_event(Colors.RED, "❌", f"Model send error: {e}")

            async def receive_from_model():
                nonlocal user_audio_turn_buffer, assistant_audio_turn_buffer
                user_transcript_buffer = ""
                assistant_transcript_buffer = ""
                
                # Latency tracking state
                last_user_word_time = 0
                first_agent_word_received = False
                latencies = []

                def save_wav(pcm_data, filename, sample_rate):
                    try:
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        with wave.open(filename, 'wb') as wav_file:
                            wav_file.setnchannels(1)
                            wav_file.setsampwidth(2) # 16-bit
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(pcm_data)
                        return filename
                    except Exception as e:
                        log_event(Colors.RED, "❌", f"WAV Save Error: {e}")
                        return None

                def flush_buffer(sender, text):
                    nonlocal user_audio_turn_buffer, assistant_audio_turn_buffer
                    if not text.strip(): return
                    
                    audio_path = None
                    timestamp = int(time.time() * 1000)
                    
                    # Save relevant audio
                    if sender == "User" and user_audio_turn_buffer:
                        # Upload to GCS
                        date_str = datetime.now().strftime("%Y-%m-%d")
                        blob_path = f"{date_str}/{session_id}/{sender.lower()}_{timestamp}.wav"
                        
                        if gcs_bucket:
                            try:
                                # Create WAV in memory
                                out_io = io.BytesIO()
                                with wave.open(out_io, 'wb') as wav_file:
                                    wav_file.setnchannels(1)
                                    wav_file.setsampwidth(2)
                                    wav_file.setframerate(16000)
                                    wav_file.writeframes(bytes(user_audio_turn_buffer))
                                
                                blob = gcs_bucket.blob(blob_path)
                                out_io.seek(0)
                                blob.upload_from_file(out_io, content_type="audio/wav")
                                audio_path = f"gcs://{GCS_BUCKET_NAME}/{blob_path}"
                                log_event(Colors.GREEN, "☁️", f"Uploaded User audio to GCS: {blob_path}")
                            except Exception as e:
                                log_event(Colors.RED, "❌", f"GCS Upload Error: {e}")
                        
                        user_audio_turn_buffer = bytearray()

                    elif sender == "Assistant" and assistant_audio_turn_buffer:
                        # Upload to GCS
                        date_str = datetime.now().strftime("%Y-%m-%d")
                        blob_path = f"{date_str}/{session_id}/{sender.lower()}_{timestamp}.wav"
                        
                        if gcs_bucket:
                            try:
                                # Create WAV in memory
                                out_io = io.BytesIO()
                                with wave.open(out_io, 'wb') as wav_file:
                                    wav_file.setnchannels(1)
                                    wav_file.setsampwidth(2)
                                    wav_file.setframerate(24000)
                                    wav_file.writeframes(bytes(assistant_audio_turn_buffer))
                                
                                blob = gcs_bucket.blob(blob_path)
                                out_io.seek(0)
                                blob.upload_from_file(out_io, content_type="audio/wav")
                                audio_path = f"gcs://{GCS_BUCKET_NAME}/{blob_path}"
                                log_event(Colors.GREEN, "☁️", f"Uploaded Assistant audio to GCS: {blob_path}")
                            except Exception as e:
                                log_event(Colors.RED, "❌", f"GCS Upload Error: {e}")

                        assistant_audio_turn_buffer = bytearray()

                    log_event(Colors.BOLD + Colors.MAGENTA, "💾", f"Saving {sender} turn to DB (Audio: {'YES' if audio_path else 'NO'})")
                    try:
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        # Use a common prefix for static files in the DB so the frontend can find them
                        db_audio_path = f"/{audio_path}" if audio_path else None
                        c.execute("INSERT INTO messages (session_id, sender, text, created_at, audio_path) VALUES (?, ?, ?, ?, ?)",
                                  (session_id, sender, text.strip(), datetime.now().isoformat(), db_audio_path))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        log_event(Colors.RED, "❌", f"DB Save Error: {e}")

                try:
                    while True:
                        async for response in session.receive():
                            server_content = response.server_content
                            
                            is_interrupted = getattr(response, 'interrupted', False) or (
                                server_content and server_content.interrupted
                            ) if server_content else getattr(response, 'interrupted', False)

                            if is_interrupted:
                                log_event(Colors.RED + Colors.BOLD, "🛑", "Assistant Interrupted (Barge-in)")
                                if assistant_transcript_buffer:
                                    flush_buffer("Assistant", assistant_transcript_buffer + " [Interrupted]")
                                    assistant_transcript_buffer = ""
                                user_audio_turn_buffer = bytearray() # Reset user audio too on interrupt usually
                                assistant_audio_turn_buffer = bytearray()
                                await websocket.send_text(json.dumps({"type": "clear_audio_queue"}))
                                continue

                            if not server_content: continue

                            # 1. Handle User Transcript
                            if server_content.input_transcription:
                                last_user_word_time = time.time()
                                chunk = server_content.input_transcription.text
                                if chunk:
                                    user_transcript_buffer += chunk
                                    await websocket.send_text(json.dumps({
                                        "type": "transcript", "sender": "User", "text": chunk
                                    }))

                            # 2. Handle Assistant Transcript
                            if server_content.output_transcription:
                                chunk = server_content.output_transcription.text
                                if chunk:
                                    if not first_agent_word_received and last_user_word_time > 0:
                                        first_agent_word_received = True
                                        latency = int((time.time() - last_user_word_time) * 1000)
                                        latencies.append(latency)
                                        avg_latency = int(sum(latencies) / len(latencies))
                                        await websocket.send_text(json.dumps({
                                            "type": "latency", "current": latency, "avg": avg_latency
                                        }))

                                    assistant_transcript_buffer += chunk
                                    await websocket.send_text(json.dumps({
                                        "type": "transcript", "sender": "Assistant", "text": chunk
                                    }))

                            # 3. Handle Binary Audio
                            model_turn = server_content.model_turn
                            if model_turn:
                                for part in model_turn.parts:
                                    if part.inline_data:
                                        audio_bytes = part.inline_data.data
                                        assistant_audio_turn_buffer.extend(audio_bytes)
                                        stats["model_audio_chunks"] += 1
                                        stats["model_audio_bytes"] += len(audio_bytes)
                                        await websocket.send_bytes(audio_bytes)
                                    elif part.text:
                                        # Native text part (if modalities include TEXT)
                                        assistant_transcript_buffer += part.text
                                        await websocket.send_text(json.dumps({
                                            "type": "transcript", "sender": "Assistant", "text": part.text
                                        }))

                            # 4. Handle Turn Completion (Commit to DB)
                            if server_content.turn_complete:
                                first_agent_word_received = False # Reset for next turn
                                if user_transcript_buffer:
                                    flush_buffer("User", user_transcript_buffer)
                                    user_transcript_buffer = ""
                                if assistant_transcript_buffer:
                                    flush_buffer("Assistant", assistant_transcript_buffer)
                                    assistant_transcript_buffer = ""
                                # Reset buffers just in case
                                user_audio_turn_buffer = bytearray()
                                assistant_audio_turn_buffer = bytearray()

                except Exception as e:
                    # Handle normal API closure (1000)
                    if "1000" in str(e) or "ConnectionClosedOK" in str(type(e).__name__):
                        log_event(Colors.GREEN, "✨", "Gemini session ended normally")
                    else:
                        log_event(Colors.RED, "❌", f"Model receive error: {e}")
                        traceback.print_exc()

            await asyncio.wait(
                [
                    asyncio.create_task(receive_from_browser()),
                    asyncio.create_task(send_realtime()),
                    asyncio.create_task(receive_from_model())
                ],
                return_when=asyncio.FIRST_COMPLETED
            )
            
    except Exception:
        traceback.print_exc()
    finally:
        duration = round(time.time() - stats["start_time"], 1)
        print(f"\n{Colors.MAGENTA}{'='*50}")
        print(f"       SESSION SUMMARY (Duration: {duration}s)")
        print(f"{Colors.MAGENTA}{'='*50}")
        print(f" {Colors.BLUE}⬆️ User Audio:   {stats['user_audio_bytes'] // 1024} KB ({stats['user_audio_chunks']} chunks)")
        print(f" {Colors.GREEN}⬇️ Assistant:    {stats['model_audio_bytes'] // 1024} KB ({stats['model_audio_chunks']} chunks)")
        print(f"{Colors.MAGENTA}{'='*50}{Colors.END}\n")
        
        try: await websocket.close()
        except: pass