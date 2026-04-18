import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*experimental.*")

import asyncio
import os
import httpx
import json
import traceback
import base64
import re
import io
import wave
import sqlite3
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from google.oauth2 import service_account
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from google.cloud import storage
from google.adk.runners import InMemoryRunner
from agent import summary_agent

# Direct API Tool Implementations for Ultra-Low Latency (<350ms)
BASE_API_URL = "https://insurance-api-471936962134.us-central1.run.app"
# Persistent client for connection pooling
shared_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    follow_redirects=True
)

async def get_customer(email: str):
    """Get basic customer details using their registered email address."""
    log_event(Colors.CYAN, "🔌", f"Direct API: get_customer({email})")
    start = time.time()
    try:
        response = await shared_client.get(f"{BASE_API_URL}/customer/{email}")
        response.raise_for_status()
        data = response.json()
        log_event(Colors.GREEN, "✅", f"Direct API success in {int((time.time()-start)*1000)}ms")
        return data
    except Exception as e:
        log_event(Colors.RED, "❌", f"Direct API Error: {e}")
        return {"error": str(e)}

async def get_claim(claim_number: str):
    """Retrieve specific claim details and status by claim number."""
    log_event(Colors.CYAN, "🔌", f"Direct API: get_claim({claim_number})")
    start = time.time()
    try:
        response = await shared_client.get(f"{BASE_API_URL}/claim/{claim_number}")
        response.raise_for_status()
        data = response.json()
        log_event(Colors.GREEN, "✅", f"Direct API success in {int((time.time()-start)*1000)}ms")
        return data
    except Exception as e:
        log_event(Colors.RED, "❌", f"Direct API Error: {e}")
        return {"error": str(e)}

async def get_full_details(email: str):
    """Get comprehensive insurance details including policies, all claims, and history for a customer."""
    log_event(Colors.CYAN, "🔌", f"Direct API: get_full_details({email})")
    start = time.time()
    try:
        response = await shared_client.get(f"{BASE_API_URL}/full-details/{email}")
        response.raise_for_status()
        data = response.json()
        log_event(Colors.GREEN, "✅", f"Direct API success in {int((time.time()-start)*1000)}ms")
        return data
    except Exception as e:
        log_event(Colors.RED, "❌", f"Direct API Error: {e}")
        return {"error": str(e)}

def flush_buffer_sync(sender, text, audio_data, session_id):
    """Sync version of flush_buffer to be run in a background thread."""
    if not text.strip(): return
    
    audio_path = None
    timestamp = int(datetime.now().timestamp() * 1000)
    
    # Save relevant audio to GCS
    if audio_data:
        date_str = datetime.now().strftime("%Y-%m-%d")
        blob_path = f"{date_str}/{session_id}/{sender.lower()}_{timestamp}.wav"
        
        bucket = get_gcs_bucket()
        if bucket:
            try:
                out_io = io.BytesIO()
                with wave.open(out_io, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000 if sender == "Assistant" else 16000)
                    wav_file.writeframes(audio_data)
                
                blob = bucket.blob(blob_path)
                out_io.seek(0)
                blob.upload_from_file(out_io, content_type="audio/wav")
                audio_path = f"gcs://{GCS_BUCKET_NAME}/{blob_path}"
                log_event(Colors.GREEN, "☁️", f"Uploaded {sender} audio to GCS (BG Thread)")
            except Exception as e:
                log_event(Colors.RED, "❌", f"GCS Upload Error: {e}")

    # Save to Database
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO messages (session_id, sender, text, created_at, audio_path) VALUES (?, ?, ?, ?, ?)",
                  (session_id, sender, text.strip(), datetime.now().isoformat(), audio_path))
        conn.commit()
        conn.close()
        log_event(Colors.MAGENTA, "💾", f"Saved {sender} turn to DB (BG Thread)")
    except Exception as e:
        log_event(Colors.RED, "❌", f"DB Save Error: {e}")


load_dotenv()

# Database Setup
DB_PATH = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY, title TEXT, created_at TIMESTAMP, summary TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, 
                  sender TEXT, text TEXT, created_at TIMESTAMP, audio_path TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id))''')
    # Migrate: add summary column if it doesn't exist yet
    try:
        c.execute('ALTER TABLE sessions ADD COLUMN summary TEXT')
    except Exception:
        pass  # Column already exists
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

# GCS & Credentials Configuration
GCS_BUCKET_NAME = "conversational-ai-recordings"
SERVICE_ACCOUNT_PATH = "/Users/goutham/Desktop/demo/xenon-lantern-490215-q3-ef0724aea8d0.json"

# Set environment variable for any libraries that use ADC
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

# Load credentials once for reuse
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_PATH,
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)

gcs_client = None
gcs_bucket = None

def get_gcs_bucket():
    """Lazy-initialize and return the GCS bucket."""
    global gcs_bucket, gcs_client
    if gcs_bucket:
        return gcs_bucket
    try:
        gcs_client = storage.Client(credentials=credentials, project=credentials.project_id)
        gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
        log_event(Colors.GREEN, "☁️", f"GCS Client Lazy-Initialized (Bucket: {GCS_BUCKET_NAME})")
        return gcs_bucket
    except Exception as e:
        log_event(Colors.RED, "❌", f"GCS Lazy-Init Error: {e}")
        return None

# Initial startup attempt
get_gcs_bucket()

def get_signed_url(blob_path: str):
    """Generate a temporary signed URL for a private GCS blob."""
    bucket = get_gcs_bucket()
    if not bucket or not blob_path:
        return blob_path
    
    # Strip leading slash if present (e.g. /gcs:// -> gcs://)
    clean_path = blob_path.lstrip('/')
    if not clean_path.startswith("gcs://"):
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
    project=credentials.project_id,
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    credentials=credentials
)

MODEL_NAME = "gemini-live-2.5-flash-native-audio"

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    media_resolution="MEDIA_RESOLUTION_MEDIUM",
    # speech_config moved to session-specific config to ensure dynamic selection
    realtime_input_config=types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            disabled=False,  # Keep VAD on
            start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,  # Less trigger-happy
            end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,        # Wait longer before cutting off
            prefix_padding_ms=200,      # ms of audio required before speech is confirmed
            silence_duration_ms=300,    # REDUCED TO 300ms for ultra-low latency
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(language_codes=[
        "en-US", "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "bn-IN", "pa-IN",
        "es-ES", "es-US", "fr-FR", "de-DE", "it-IT", "pt-BR", "zh-CN", "ja-JP", "ko-KR", "ar-SA", "ru-RU"
    ]),
    output_audio_transcription=types.AudioTranscriptionConfig(language_codes=[
        "en-US", "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "gu-IN", "bn-IN", "pa-IN",
        "es-ES", "es-US", "fr-FR", "de-DE", "it-IT", "pt-BR", "zh-CN", "ja-JP", "ko-KR", "ar-SA", "ru-RU"
    ]),
    system_instruction=types.Content(parts=[types.Part.from_text(text="""
    You are a professional and empathetic AI Voice Agent.
    Your sole purpose is to assist customers with insurance-related queries — nothing else.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    IDENTITY & SCOPE
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - You work exclusively for an insurance company handling:
    - Claim status, policies, premium payments, and coverage details.
    - Adding beneficiaries or document verification.
    - If a user asks ANYTHING outside insurance (e.g., weather, politics, jokes):
    → Respond: "I'm specifically trained to help you with insurance-related matters only."
    → Never engage with off-topic content.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    LANGUAGE BEHAVIOR
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Always BEGIN in clear, professional English.
    - STRICTLY match the customer's language once they speak.
    - Only switch to Hindi, Tamil, or Telugu if the user has spoken a complete sentence in that language.
    - If you are unsure of the user's language, default to English.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    EMOTIONAL INTELLIGENCE PROTOCOL
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - ANGRY: NEVER argue. Acknowledge frustration first: "I completely understand how frustrating this must be..."
    - ANXIOUS: Use reassuring language: "You're in safe hands." / "We'll sort it out together."
    - GRIEVING: Speak with exceptional softness and zero urgency. Open with: "I'm so sorry for your loss."
    - HAPPY: Match their positive energy warmly but professionally.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ANTI-HALLUCINATION RULES (CRITICAL)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - NEVER invent policy numbers, claim statuses, amounts, or dates.
    - ALWAYS use tools to verify real data. 
    - Tools available: `get_claim(claim_number)`, `get_customer(email)`, `get_full_details(email)`.
    - If data is missing after tool call, inform user and ask for the missing detail.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    CONVERSATION STRUCTURE
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. GREETING: "Hello! Thank you for calling us. I'm your insurance assistant. How may I help you today?"
    2. IDENTIFICATION: "May I have your policy number or registered mobile number?"
    3. RESOLUTION: Give clear, step-by-step guidance. Confirm understanding.
    4. CLOSING: "Is there anything else I can help you with regarding your insurance today?"

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    TONE & VOICE PERSONALITY
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Professional yet warm — like a knowledgeable friend.
    - Concise — avoid rambling. One clear idea per sentence.
    - You support barge-in. If the user interrupts, stop immediately and listen.
    """)]))

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
    c.execute("SELECT sender, text, created_at, audio_path FROM messages WHERE session_id = ? AND text IS NOT NULL ORDER BY created_at ASC", (session_id,))
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

@app.post("/api/sessions/{session_id}/sync")
async def sync_session(session_id: str):
    """Scan GCS for this session and restore any missing records in the DB."""
    if not gcs_bucket:
        return {"error": "GCS not initialized"}
    
    try:
        # 1. Get session date from DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT created_at FROM sessions WHERE id = ?", (session_id,))
        res = c.fetchone()
        if not res:
            return {"error": "Session not found"}
        
        # Format: 2026-04-14T...
        date_str = datetime.fromisoformat(res[0]).strftime("%Y-%m-%d")
        
        # 2. List GCS blobs for this session
        prefix = f"{date_str}/{session_id}/"
        blobs = list(gcs_bucket.list_blobs(prefix=prefix))
        log_event(Colors.CYAN, "🔍", f"Syncing {session_id}: Found {len(blobs)} blobs in GCS")
        
        synced_count = 0
        for blob in blobs:
            if not blob.name.endswith(".wav"): continue
            
            # Check if exists in DB
            gcs_path = f"gcs://{GCS_BUCKET_NAME}/{blob.name}"
            c.execute("SELECT id FROM messages WHERE audio_path = ?", (gcs_path,))
            if not c.fetchone():
                # Reconstruct record
                sender = "Assistant" if "assistant" in blob.name.lower() else "User"
                created_at = blob.time_created or datetime.now()
                c.execute("INSERT INTO messages (session_id, sender, text, created_at, audio_path) VALUES (?, ?, ?, ?, ?)",
                          (session_id, sender, "[Discovered from Cloud]", created_at.isoformat(), gcs_path))
                synced_count += 1
        
        conn.commit()
        conn.close()
        return {"status": "success", "synced": synced_count}
    except Exception as e:
        log_event(Colors.RED, "❌", f"Sync Error: {e}")
        return {"error": str(e)}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Fetch created_at to reconstruct GCS prefix for cleanup
    c.execute("SELECT created_at FROM sessions WHERE id = ?", (session_id,))
    res = c.fetchone()
    
    if res:
        created_at_str = res[0]
        try:
            # Reconstruct the GCS path used in upload: date_str/session_id/
            date_str = datetime.fromisoformat(created_at_str).strftime("%Y-%m-%d")
            # Using the prefix without the trailing slash to catch the "folder" object itself
            prefix = f"{date_str}/{session_id}"
            
            bucket = get_gcs_bucket()
            if bucket:
                # Use the prefix to find all items including the folder placeholder
                blobs = list(bucket.list_blobs(prefix=prefix))
                if blobs:
                    log_event(Colors.YELLOW, "🗑️", f"Deleting {len(blobs)} items (including folder) from GCS for session {session_id}")
                    bucket.delete_blobs(blobs)
                    log_event(Colors.GREEN, "✅", f"Successfully cleaned up all GCS data for {session_id}")
                else:
                    log_event(Colors.CYAN, "ℹ️", f"No GCS data found for session {session_id} using prefix {prefix}")
        except Exception as e:
            log_event(Colors.RED, "❌", f"GCS Cleanup Error: {e}")

    # 2. Proceed with database deletion
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/sessions/{session_id}/summary")
async def generate_summary(session_id: str):
    """Generate a post-call summary using the ADK summary_agent."""
    # 1. Fetch transcript from DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT sender, text FROM messages
        WHERE session_id = ? AND text IS NOT NULL AND text != ''
          AND text != '[Discovered from Cloud]'
        ORDER BY created_at ASC
    """, (session_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {"error": "No transcript found for this session"}

    # 2. Build transcript string
    transcript = "\n".join(f"{sender}: {text}" for sender, text in rows)
    prompt = f"Please summarize the following insurance support call transcript:\n\n{transcript}"

    try:
        # 3. Run through ADK summary_agent
        runner = InMemoryRunner(agent=summary_agent)
        adk_session = await runner.session_service.create_session(
            app_name=runner.app_name, user_id="system"
        )

        from google.genai.types import Content, Part
        response_text = ""
        async for event in runner.run_async(
            session_id=adk_session.id,
            user_id="system",
            new_message=Content(role="user", parts=[Part(text=prompt)])
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text

        # 4. Parse and return JSON
        # Strip any accidental markdown code fences
        cleaned = response_text.strip().strip('`').strip()
        if cleaned.startswith('json'):
            cleaned = cleaned[4:].strip()
        summary_data = json.loads(cleaned)
        log_event(Colors.GREEN, "📋", f"Summary generated for session {session_id}: {summary_data.get('title', 'N/A')}")
        # Persist summary to DB so it can be used as session context on resume
        try:
            db_conn = sqlite3.connect(DB_PATH)
            db_conn.execute("UPDATE sessions SET summary = ?, title = ? WHERE id = ?",
                            (json.dumps(summary_data), summary_data.get('title', 'Call Summary'), session_id))
            db_conn.commit()
            db_conn.close()
        except Exception as db_err:
            log_event(Colors.YELLOW, "⚠️", f"Failed to persist summary to DB: {db_err}")
        return {"status": "success", "summary": summary_data, "session_id": session_id}

    except json.JSONDecodeError as e:
        log_event(Colors.YELLOW, "⚠️", f"Summary JSON parse failed: {e}. Raw: {response_text[:200]}")
        fallback = {"title": "Call Summary", "language": "N/A", "summary": response_text, "sentiment": "neutral", "key_topics": [], "action_items": [], "customer_intent": "", "resolution": "", "call_quality": "normal"}
        return {"status": "success", "summary": fallback, "session_id": session_id}
    except Exception as e:
        log_event(Colors.RED, "❌", f"Summary generation error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.websocket("/ws")
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = None, voice: str = Query("Zephyr")):
    await websocket.accept()
    
    # Explicitly get voice from query params to ensure it's captured
    voice = websocket.query_params.get("voice", voice)
    log_event(Colors.BOLD + Colors.CYAN, "🎙️", f"NEW SESSION: Voice chosen = {voice}")
    
    if not session_id:
        session_id = f"sess_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO sessions (id, title, created_at) VALUES (?, ?, ?)", 
                  (session_id, f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}", datetime.now().isoformat()))
        conn.commit()
        conn.close()

    # ── Tell the client which session this is (critical for new sessions) ──
    await websocket.send_text(json.dumps({"type": "session_init", "session_id": session_id}))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Prefer the stored post-call summary for context (compact & clean)
    c.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,))
    summary_row = c.fetchone()
    stored_summary = None
    if summary_row and summary_row[0]:
        try:
            stored_summary = json.loads(summary_row[0])
        except Exception:
            stored_summary = None
    conn.close()

    history_block = ""
    if stored_summary:
        # Use the generated summary — much more compact than raw transcript
        history_block = f"""

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    PREVIOUS CALL SUMMARY
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    This session was previously completed. Here is its summary:

    Title: {stored_summary.get('title', '')}
    Customer Intent: {stored_summary.get('customer_intent', '')}
    Resolution: {stored_summary.get('resolution', '')}
    Key Topics: {', '.join(stored_summary.get('key_topics', []))}
    Action Items: {'; '.join(stored_summary.get('action_items', [])) or 'None'}
    Sentiment: {stored_summary.get('sentiment', 'neutral')}
    Summary: {stored_summary.get('summary', '')}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    The customer is calling back. Use this context to maintain continuity — you
    already know what was discussed. Do not repeat resolved matters; build forward.
    """

    # ── Build a session-specific CONFIG with history and chosen voice injected ─────────────
    base_instruction = CONFIG.system_instruction.parts[0].text
    session_config = types.LiveConnectConfig(
        response_modalities=CONFIG.response_modalities,
        media_resolution=CONFIG.media_resolution,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
        realtime_input_config=CONFIG.realtime_input_config,
        input_audio_transcription=CONFIG.input_audio_transcription,
        output_audio_transcription=CONFIG.output_audio_transcription,
        system_instruction=types.Content(parts=[
            types.Part.from_text(text=base_instruction + history_block)
        ]),
        tools=[get_customer, get_claim, get_full_details]
    )
    # ──────────────────────────────────────────────────────────────────────

    log_event(Colors.CYAN, "🔌", f"Browser connected to WebSocket (Session: {session_id})")
    if stored_summary:
        log_event(Colors.CYAN, "📋", f"Injected post-call summary as context: {stored_summary.get('title', 'N/A')}")

    out_queue = asyncio.Queue(maxsize=100)
    
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
        async with client.aio.live.connect(model=MODEL_NAME, config=session_config) as session:
            log_event(Colors.GREEN, "✨", f"Connected to Gemini Live API ({MODEL_NAME})")
            
            if stored_summary:
                initial_prompt = (
                    f"[BEGIN CALL] Greet the returning customer warmly. "
                    f"Acknowledge that you previously helped them with '{stored_summary.get('title', 'their insurance policy')}' "
                    f"and invite them to continue. Keep it brief, natural, and professional."
                )
            else:
                initial_prompt = (
                    "[BEGIN CALL] You are an insurance voice agent. "
                    "Deliver your opening greeting now, speaking directly to the customer as if the call just connected. "
                    "Be warm, professional, and brief."
                )

            await session.send(input=initial_prompt, end_of_turn=True)
            
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
                
                # Latency tracking & Speculative state
                last_user_word_time = 0
                first_agent_word_received = False
                latencies = []
                # Speculative tool cache: { (tool_name, id): asyncio.Task }
                speculative_cache = {}

                async def speculative_fetch(tool_name, arg_name, arg_val):
                    key = (tool_name, arg_val)
                    if key in speculative_cache:
                        return
                    
                    log_event(Colors.CYAN, "🚀", f"Speculative Fetch: {tool_name}({arg_val}) started while user is speaking...")
                    tool_func = tool_map.get(tool_name)
                    if tool_func:
                        # Create task and store in cache
                        task = asyncio.create_task(tool_func(**{arg_name: arg_val}))
                        speculative_cache[key] = task
                        try:
                            await task
                            log_event(Colors.CYAN, "✨", f"Speculative Fetch: {tool_name}({arg_val}) completed and cached.")
                        except Exception as e:
                            log_event(Colors.RED, "⚠️", f"Speculative Fetch failed for {arg_val}: {e}")

                try:
                    while True:
                        tool_map = {
                            "get_customer": get_customer,
                            "get_claim": get_claim,
                            "get_full_details": get_full_details
                        }
                        async for response in session.receive():
                            # 0. Handle Tool Calls
                            if response.tool_call:
                                log_event(Colors.YELLOW, "🛠️", f"Gemini requested tools: {[fc.name for fc in response.tool_call.function_calls]}")
                                function_responses = []
                                for fc in response.tool_call.function_calls:
                                    tool_func = tool_map.get(fc.name)
                                    if tool_func:
                                        try:
                                            # Check speculative cache
                                            arg_val = next(iter(fc.args.values())) if fc.args else None
                                            key = (fc.name, arg_val)
                                            
                                            if key in speculative_cache:
                                                log_event(Colors.GREEN + Colors.BOLD, "⚡", f"INSTANT RESPONSE: Using cached speculative result for {fc.name}({arg_val})")
                                                result = await speculative_cache[key]
                                            else:
                                                log_event(Colors.YELLOW, "⏳", f"Tool {fc.name} not in speculative cache, calling now...")
                                                result = await tool_func(**fc.args)

                                            function_responses.append(
                                                types.FunctionResponse(
                                                    name=fc.name,
                                                    id=fc.id,
                                                    response=result
                                                )
                                            )
                                            log_event(Colors.GREEN, "✅", f"Tool {fc.name} result obtained.")
                                        except Exception as tool_err:
                                            log_event(Colors.RED, "❌", f"Tool {fc.name} error: {tool_err}")
                                            function_responses.append(
                                                types.FunctionResponse(
                                                    name=fc.name,
                                                    id=fc.id,
                                                    response={"error": str(tool_err)}
                                                )
                                            )
                                
                                if function_responses:
                                    await session.send(input=types.LiveClientToolResponse(function_responses=function_responses))
                                continue

                            server_content = response.server_content
                            
                            is_interrupted = getattr(response, 'interrupted', False) or (
                                server_content and server_content.interrupted
                            ) if server_content else getattr(response, 'interrupted', False)

                            if is_interrupted:
                                log_event(Colors.RED + Colors.BOLD, "🛑", "Assistant Interrupted (Barge-in)")
                                if assistant_transcript_buffer:
                                    audio_copy = bytes(assistant_audio_turn_buffer)
                                    assistant_audio_turn_buffer.clear()
                                    asyncio.create_task(asyncio.to_thread(flush_buffer_sync, "Assistant", assistant_transcript_buffer + " [Interrupted]", audio_copy, session_id))
                                    assistant_transcript_buffer = ""
                                user_audio_turn_buffer = bytearray() 
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
                                    
                                    # --- Speculative Engine ---
                                    # Look for Claim IDs: CL-105 or CL105
                                    claim_matches = re.findall(r"(?:CL-?\d+)", user_transcript_buffer, re.IGNORECASE)
                                    for mid in claim_matches:
                                        asyncio.create_task(speculative_fetch("get_claim", "claim_number", mid.upper()))
                                    
                                    # Look for Emails
                                    email_matches = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", user_transcript_buffer)
                                    for email in email_matches:
                                        # Speculatively fetch both customer and full details for emails
                                        asyncio.create_task(speculative_fetch("get_customer", "email", email.lower()))
                                        asyncio.create_task(speculative_fetch("get_full_details", "email", email.lower()))
                                    # --------------------------

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
                                first_agent_word_received = False 
                                if user_transcript_buffer:
                                    audio_copy = bytes(user_audio_turn_buffer)
                                    user_audio_turn_buffer.clear()
                                    asyncio.create_task(asyncio.to_thread(flush_buffer_sync, "User", user_transcript_buffer, audio_copy, session_id))
                                    user_transcript_buffer = ""
                                if assistant_transcript_buffer:
                                    audio_copy = bytes(assistant_audio_turn_buffer)
                                    assistant_audio_turn_buffer.clear()
                                    asyncio.create_task(asyncio.to_thread(flush_buffer_sync, "Assistant", assistant_transcript_buffer, audio_copy, session_id))
                                    assistant_transcript_buffer = ""
                                    
                                user_audio_turn_buffer = bytearray()
                                assistant_audio_turn_buffer = bytearray()

                except Exception as e:
                    # Handle normal API closure (1000)
                    if "1000" in str(e) or "ConnectionClosedOK" in str(type(e).__name__):
                        log_event(Colors.GREEN, "✨", "Gemini session ended normally")
                    else:
                        log_event(Colors.RED, "❌", f"Model receive error: {e}")
                        traceback.print_exc()

            # Use list of tasks to ensure clean cleanup
            tasks = [
                asyncio.create_task(receive_from_browser()),
                asyncio.create_task(send_realtime()),
                asyncio.create_task(receive_from_model())
            ]
            
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            # Cancel pending tasks to avoid "Task destroyed but pending" warnings
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            
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

@app.get("/api/debug/gcs")
async def debug_gcs():
    bucket = get_gcs_bucket()
    return {
        "bucket_initialized": bucket is not None,
        "bucket_name": GCS_BUCKET_NAME,
        "service_account_path": SERVICE_ACCOUNT_PATH,
        "service_account_exists": os.path.exists(SERVICE_ACCOUNT_PATH)
    }

@app.get("/api/debug/sign")
async def debug_sign():
    bucket = get_gcs_bucket()
    if not bucket:
        return {"error": "GCS not initialized"}
    try:
        blob = bucket.blob("test.wav")
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=5),
            method="GET",
        )
        return {"success": True, "url": url}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)