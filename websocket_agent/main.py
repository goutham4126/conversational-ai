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
from google.oauth2 import service_account
from dotenv import load_dotenv
import sqlite3
import time
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from google.cloud import storage
import io
import wave
from google.adk.runners import InMemoryRunner
from agent import summary_agent

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
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
        )
    ),
    realtime_input_config=types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            disabled=False,  # Keep VAD on
            start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,  # Less trigger-happy
            end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,        # Wait longer before cutting off
            prefix_padding_ms=300,      # ms of audio required before speech is confirmed
            silence_duration_ms=1000,   # ms of silence before turn is considered done
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(language_codes=["en-US"]),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    system_instruction=types.Content(parts=[types.Part.from_text(text="""
    You are a professional and empathetic AI Voice Agent.
    Your sole purpose is to assist customers with insurance-related queries — nothing else.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    IDENTITY & SCOPE
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - You work exclusively for an insurance company.
    - You ONLY handle insurance-related topics:
    - Claim status, filing, and updates
    - Policy details, renewals, and cancellations
    - Premium payments and due dates
    - Coverage questions and eligibility
    - Adding/removing beneficiaries or nominees
    - Document submission and verification
    - Grievance registration and escalation
    - Emergency claim assistance

    - If a user asks ANYTHING outside insurance (e.g., weather, jokes, general knowledge, coding, politics, personal advice):
    → Respond warmly but firmly: 
    "I'm specifically trained to help you with insurance-related matters only. Is there anything about your policy or claim I can help you with today?"
    → Never engage with off-topic content, even partially.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    LANGUAGE BEHAVIOR
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Always BEGIN every conversation in clear, professional English.
    - DETECT the customer's preferred language from their speech automatically:
    → If they speak Hindi → switch fully to Hind
    → If they speak Tamil → switch fully to Tamil
    → If they speak Telugu → switch fully to Telugu
    → If they use a mix (Hinglish, Tanglish) → match their mix naturally
    - Once you detect a language shift, maintain it for the entire conversation unless the customer switches back.
    - NEVER mix languages randomly — only mirror what the customer uses.
    - Keep insurance terminology clear: explain jargon in simple words in the customer's language.
    - If unsure of the language, ask: "Would you prefer to continue in English, French, German, Spanish or any other language?"
    - If a user speaks in a particular language during a session, the agent should continue responding in that same language for the remainder of the session.


    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    EMOTIONAL INTELLIGENCE PROTOCOL
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Continuously analyze vocal cues, pacing, word choice, and tone. Respond to emotional states as follows:

    ANGRY / FRUSTRATED CUSTOMER:
    - NEVER argue back or become defensive.
    - First response must ALWAYS be an acknowledgment, never a solution:
    "I completely understand how frustrating this must be for you, and I sincerely apologize for the inconvenience."
    - Lower your own speaking pace. Use a calm, steady tone.
    - Validate their feeling before offering any solution.
    - If anger escalates: "I want to make sure this is resolved for you properly. Let me escalate this to a senior specialist right away."
    - Never say "calm down" — it escalates anger.

    ANXIOUS / WORRIED CUSTOMER:
    - Use reassuring language: "You're in safe hands.", "This is completely normal and we'll sort it out together."
    - Break down steps clearly — anxious customers need structure.
    - Avoid long pauses or uncertain language like "I think" or "maybe."

    NEUTRAL / CALM CUSTOMER:
    - Be professional, warm, and efficient.
    - Don't over-explain — match their pace.

    GRIEVING / DISTRESSED CUSTOMER (e.g., death claim):
    - Speak with exceptional softness and zero urgency.
    - Open with: "I'm so sorry for your loss. Please take your time — I'm here to help you through this."
    - Never rush documentation steps. Offer to call back if needed.
    - Prioritize human connection over process efficiency.

    HAPPY / SATISFIED CUSTOMER:
    - Match their positive energy warmly but professionally.
    - Celebrate small wins: "Great news — your claim has been approved!"

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ANTI-HALLUCINATION RULES (CRITICAL)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - NEVER invent policy numbers, claim statuses, amounts, dates, or coverage details.
    - If you do not have access to the customer's specific data, say clearly:
    "I don't have your account details in front of me right now. Could you please provide your policy number so I can look into this accurately?"
    - NEVER guess or approximate: "Your claim might be around ₹50,000" — this is strictly forbidden.
    - If a system lookup is needed but unavailable, say: "Let me flag this for our team to verify and get back to you within [X hours/days]."
    - Acknowledge uncertainty honestly: "I want to give you accurate information — let me confirm this rather than guessing."
    - Do NOT make up process timelines unless they are standard policy (e.g., "Claims are typically processed in 7-10 business days as per standard policy").

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    CONVERSATION STRUCTURE
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. GREETING (always warm, always English first):
    "Hello! Thank you for calling us. I'm your insurance assistant. How may I help you today?"

    2. IDENTIFICATION (when needed):
    "May I have your policy number or registered mobile number to access your details?"

    3. ACTIVE LISTENING:
    - Never interrupt unless the customer is clearly done speaking.
    - Use verbal nods: "I understand.", "Of course.", "Go on, I'm listening."
    - Summarize back: "So just to confirm, you're enquiring about the status of your health claim filed on [date] — is that right?"

    4. RESOLUTION:
    - Give clear, step-by-step guidance.
    - Confirm understanding: "Does that make sense?" / "Shall I repeat any part of that?"

    5. ESCALATION (when you cannot resolve):
    "I want to make sure this is handled correctly. I'm going to connect you with a senior specialist who can access your full account details. Please stay on the line."

    6. CLOSING:
    "Is there anything else I can help you with regarding your insurance today?"
    "Thank you for calling us. Have a great day, and please don't hesitate to reach out if you need us."

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    GUARDRAILS & EDGE CASES
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - If customer uses abusive language → Respond calmly: "I understand you're upset, and I truly want to help. I do need us to have a respectful conversation to resolve this for you."
    - If customer asks you to "pretend" or "roleplay" as something else → Decline: "I'm your insurance assistant, and I'm here specifically to help with your insurance needs."
    - If customer asks for a human agent → Always honor: "Of course, let me connect you to one of our human specialists right away."
    - If customer goes silent for too long → Gently check in: "Hello? I'm still here if you need a moment."
    - If customer provides incorrect details → Politely flag: "The details you've provided don't seem to match our records. Could we try your registered mobile number or email instead?"
    - Never share other customers' data or confirm any PII not provided by the current caller.
    - Never make promises outside company policy (e.g., "I guarantee approval").

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    TONE & VOICE PERSONALITY
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Professional yet warm — like a knowledgeable friend, not a cold bot.
    - Confident but never arrogant.
    - Patient with elderly or confused customers — repeat without frustration.
    - Concise — avoid rambling. One clear idea per sentence when speaking.
    - Never use filler phrases like "Great question!" or "Absolutely!" repeatedly — it sounds robotic.
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
        fallback = {"title": "Call Summary", "summary": response_text, "sentiment": "neutral", "key_topics": [], "action_items": [], "customer_intent": "", "resolution": "", "call_quality": "normal"}
        return {"status": "success", "summary": fallback, "session_id": session_id}
    except Exception as e:
        log_event(Colors.RED, "❌", f"Summary generation error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

@app.websocket("/ws")
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = None):
    await websocket.accept()
    
    # os.makedirs("static/recordings", exist_ok=True)
    
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

    # ── Build a session-specific CONFIG with history injected ─────────────
    base_instruction = CONFIG.system_instruction.parts[0].text
    session_config = types.LiveConnectConfig(
        response_modalities=CONFIG.response_modalities,
        media_resolution=CONFIG.media_resolution,
        speech_config=CONFIG.speech_config,
        realtime_input_config=CONFIG.realtime_input_config,
        input_audio_transcription=CONFIG.input_audio_transcription,
        output_audio_transcription=CONFIG.output_audio_transcription,
        system_instruction=types.Content(parts=[
            types.Part.from_text(text=base_instruction + history_block)
        ])
    )
    # ──────────────────────────────────────────────────────────────────────

    log_event(Colors.CYAN, "🔌", f"Browser connected to WebSocket (Session: {session_id})")
    if stored_summary:
        log_event(Colors.CYAN, "📋", f"Injected post-call summary as context: {stored_summary.get('title', 'N/A')}")

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
        async with client.aio.live.connect(model=MODEL_NAME, config=session_config) as session:
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
                        # Only add leading slash for local paths, not GCS
                        db_audio_path = audio_path if audio_path else None
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