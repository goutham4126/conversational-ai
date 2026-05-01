let ws = null;
let inputProcessorNode = null;
let playbackProcessorNode = null;
let playbackContext = null;
let recordingContext = null;


let currentSessionId = null;
let currentVoice = 'Zephyr';
let lastRatedSessionId = null;
let selectedRating = null;

// Post-Call Flow Synchronization State
let summaryReady = false;
let ratingFinished = false;
let pendingSummary = null;
let currentRatingInHeader = null; // Track rating for the header display

// ── Voices Dataset ──────────────────────────────────────────────────────────
const voicesData = [
    {
        category: "Core Voices",
        voices: [
            { id: "Zephyr", name: "Zephyr", tone: "Bright, Higher pitch" },
            { id: "Puck", name: "Puck", tone: "Upbeat, Middle pitch" },
            { id: "Charon", name: "Charon", tone: "Informative, Lower pitch" },
            { id: "Kore", name: "Kore", tone: "Firm, Middle pitch" },
            { id: "Fenrir", name: "Fenrir", tone: "Excitable, Lower middle pitch" }
        ]
    },
    {
        category: "Additional Voices",
        voices: [
            { id: "Leda", name: "Leda", tone: "Youthful, Higher pitch" },
            { id: "Orus", name: "Orus", tone: "Firm, Lower middle pitch" },
            { id: "Aoede", name: "Aoede", tone: "Breezy, Middle pitch" },
            { id: "Callirrhoe", name: "Callirrhoe", tone: "Easy-going, Middle pitch" },
            { id: "Autonoe", name: "Autonoe", tone: "Bright, Middle pitch" }
        ]
    },
    {
        category: "Deeper / Softer",
        voices: [
            { id: "Enceladus", name: "Enceladus", tone: "Breathy, Lower pitch" },
            { id: "Iapetus", name: "Iapetus", tone: "Clear, Lower middle pitch" },
            { id: "Umbriel", name: "Umbriel", tone: "Easy-going, Lower middle pitch" },
            { id: "Algieba", name: "Algieba", tone: "Smooth, Lower pitch" },
            { id: "Despina", name: "Despina", tone: "Smooth, Middle pitch" }
        ]
    },
    {
        category: "Clear / Informative",
        voices: [
            { id: "Erinome", name: "Erinome", tone: "Clear, Middle pitch" },
            { id: "Rasalgethi", name: "Rasalgethi", tone: "Informative, Middle pitch" },
            { id: "Sadaltager", name: "Sadaltager", tone: "Knowledgeable, Middle pitch" }
        ]
    },
    {
        category: "Strong Personality",
        voices: [
            { id: "Algenib", name: "Algenib", tone: "Gravelly, Lower pitch" },
            { id: "Gacrux", name: "Gacrux", tone: "Mature, Middle pitch" },
            { id: "Pulcherrima", name: "Pulcherrima", tone: "Forward, Middle pitch" },
            { id: "Achird", name: "Achird", tone: "Friendly, Lower middle pitch" },
            { id: "Zubenelgenubi", name: "Zubenelgenubi", tone: "Casual, Lower middle pitch" }
        ]
    },
    {
        category: "Expressive / Emotional",
        voices: [
            { id: "Vindemiatrix", name: "Vindemiatrix", tone: "Gentle, Middle pitch" },
            { id: "Sadachbia", name: "Sadachbia", tone: "Lively, Lower pitch" },
            { id: "Sulafat", name: "Sulafat", tone: "Warm, Middle pitch" }
        ]
    },
    {
        category: "Energetic / Bright",
        voices: [
            { id: "Laomedeia", name: "Laomedeia", tone: "Upbeat, Higher pitch" },
            { id: "Achernar", name: "Achernar", tone: "Soft, Higher pitch" }
        ]
    },
    {
        category: "Balanced / Neutral",
        voices: [
            { id: "Alnilam", name: "Alnilam", tone: "Firm, Lower middle pitch" },
            { id: "Schedar", name: "Schedar", tone: "Even, Lower middle pitch" }
        ]
    }
];

const micBtn = document.getElementById('micBtn');
const statusText = document.getElementById('statusText');
const transcriptArea = document.getElementById('transcriptArea');
const connStatus = document.getElementById('connStatus');
const connText = document.getElementById('connText');
const visualizer = document.getElementById('visualizer');
const micIcon = document.getElementById('micIcon');
const sessionList = document.getElementById('sessionList');
const newChatBtn = document.getElementById('newChatBtn');

const latencyInfo = document.getElementById('latencyInfo');
const currentLatency = document.getElementById('currentLatency');
const avgLatency = document.getElementById('avgLatency');
const syncBtn = document.getElementById('syncBtn');
const callingOverlay = document.getElementById('callingOverlay');
const ratingModal = document.getElementById('ratingModal');
const starsContainer = document.getElementById('starsContainer');
const skipRatingBtn = document.getElementById('skipRatingBtn');
const submitRatingBtn = document.getElementById('submitRatingBtn');
let agentOpeningComplete = false;


const voiceTrigger = document.getElementById('voiceTrigger');
const voiceDropdown = document.getElementById('voiceDropdown');
const activeVoiceName = document.getElementById('activeVoiceName');
const activeVoiceTone = document.getElementById('activeVoiceTone');
const voiceSelectorContainer = document.querySelector('.voice-selector-container');

// ── Custom Voice Selection Logic ────────────────────────────────────────────
function initVoiceSelector() {
    if (!voiceDropdown) return;

    voiceDropdown.innerHTML = '';
    voicesData.forEach(group => {
        const cat = document.createElement('div');
        cat.className = 'voice-category';
        cat.innerText = group.category;
        voiceDropdown.appendChild(cat);

        group.voices.forEach(v => {
            const opt = document.createElement('div');
            opt.className = `voice-option ${currentVoice === v.id ? 'active' : ''}`;
            opt.innerHTML = `
                <span class="voice-option-name">${v.name}</span>
                <span class="voice-option-tone">${v.tone}</span>
            `;
            opt.onclick = () => {
                selectVoice(v.id);
                toggleVoiceDropdown(false);
            };
            voiceDropdown.appendChild(opt);
        });
    });
}

function selectVoice(id) {
    currentVoice = id;
    const voiceObj = voicesData.flatMap(g => g.voices).find(v => v.id === id);
    if (voiceObj) {
        activeVoiceName.innerText = voiceObj.name;
        initVoiceSelector(); // Refresh active state
    }
}

function toggleVoiceDropdown(force) {
    const isVisible = force !== undefined ? force : voiceDropdown.style.display === 'none';
    voiceDropdown.style.display = isVisible ? 'block' : 'none';
}

if (voiceTrigger) {
    voiceTrigger.onclick = (e) => {
        e.stopPropagation();
        toggleVoiceDropdown();
    };
}

window.addEventListener('click', () => toggleVoiceDropdown(false));
initVoiceSelector();

// RingbackTone removed for maximum speed


// ── Rating Logic ──────────────────────────────────────────────────────────
function showRatingModal(sessionId) {
    if (!sessionId) {
        console.warn('[Rating] No sessionId provided to showRatingModal');
        return;
    }
    
    // Lazy-select if the global reference is missing
    const modal = ratingModal || document.getElementById('ratingModal');
    const container = starsContainer || document.getElementById('starsContainer');
    
    if (!modal || !container) {
        console.error('[Rating] Modal or Container elements not found in DOM!');
        return;
    }

    lastRatedSessionId = sessionId;
    selectedRating = null;
    console.log('[Rating] Displaying modal for session:', sessionId);
    
    // Explicitly set display and z-index to ensure it shows above everything
    modal.style.display = 'flex';
    modal.style.zIndex = '10000';
    
    // Reset buttons
    const submitBtn = document.getElementById('submitRatingBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'Submit Rating';
    }

    // Clear previous stars
    const stars = container.querySelectorAll('.star');
    stars.forEach(s => {
        s.classList.remove('active', 'hovered');
    });
}



function closeRatingModal() {
    ratingModal.style.display = 'none';
    lastRatedSessionId = null;
}

async function submitRating(sessionId, rating) {
    try {
        const response = await fetch(`/api/sessions/${sessionId}/rating`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating })
        });
        const result = await response.json();
        console.log('[Rating] Result:', result);
    } catch (err) {
        console.error('[Rating] Error:', err);
    }
}

// Event Listeners for Rating
function initRatingListeners() {
    const container = document.getElementById('starsContainer');
    const skipBtn = document.getElementById('skipRatingBtn');
    const submitBtn = document.getElementById('submitRatingBtn');
    
    if (!container) {
        console.warn('[Rating] starsContainer not found yet, retrying...');
        return;
    }

    const stars = container.querySelectorAll('.star');
    stars.forEach(star => {
        // Remove existing to prevent duplicates
        const newStar = star.cloneNode(true);
        star.replaceWith(newStar);
    });

    // Re-select after clone
    const freshStars = container.querySelectorAll('.star');
    freshStars.forEach(star => {
        star.addEventListener('mouseover', () => {
            if (selectedRating !== null) return;
            const val = parseInt(star.dataset.value);
            freshStars.forEach(s => {
                if (parseInt(s.dataset.value) <= val) s.classList.add('hovered');
                else s.classList.remove('hovered');
            });
        });

        star.addEventListener('mouseout', () => {
            if (selectedRating !== null) return;
            freshStars.forEach(s => s.classList.remove('hovered'));
        });

        star.addEventListener('click', () => {
            selectedRating = parseInt(star.dataset.value);
            console.log('[Rating] Stars selected:', selectedRating);
            
            // Highlight stars up to selection
            freshStars.forEach(s => {
                if (parseInt(s.dataset.value) <= selectedRating) {
                    s.classList.add('active');
                    s.classList.remove('hovered');
                } else {
                    s.classList.remove('active', 'hovered');
                }
            });

            // Enable submit button
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.classList.add('active-ready');
            }
        });
    });

    if (submitBtn) {
        submitBtn.onclick = async () => {
            if (lastRatedSessionId && selectedRating) {
                console.log('[Rating] Final Submission:', selectedRating, 'stars for', lastRatedSessionId);
                submitBtn.disabled = true;
                submitBtn.innerText = 'Submitting...';
                
                await submitRating(lastRatedSessionId, selectedRating);
                
                // Update flow state
                ratingFinished = true;
                currentRatingInHeader = selectedRating;
                
                // If summary is already ready, show it now
                if (summaryReady && pendingSummary) {
                    showSummaryCard({ summary: pendingSummary, rating: currentRatingInHeader });
                } else {
                    // Otherwise show loading until background fetch finishes
                    showSummaryCard({ loading: true });
                }
                
                submitBtn.innerText = 'Submitted! ✅';
                setTimeout(closeRatingModal, 800);
            }
        };
    }

    if (skipBtn) {
        skipBtn.onclick = () => {
            ratingFinished = true;
            currentRatingInHeader = null;
            if (summaryReady && pendingSummary) {
                showSummaryCard({ summary: pendingSummary, rating: null });
            } else {
                showSummaryCard({ loading: true });
            }
            closeRatingModal();
        };
    }
}



// ── Eager Initialization logic ──────────────────────────────────────────────

async function ensureAudioContexts() {
    if (!playbackContext) {
        console.log("[Audio] Initializing playback context @ 24kHz...");
        playbackContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        await playbackContext.audioWorklet.addModule('/static/playback-processor.js');
        playbackProcessorNode = new AudioWorkletNode(playbackContext, 'playback-processor');
        playbackProcessorNode.connect(playbackContext.destination);
    }

    if (!recordingContext) {
        console.log("[Audio] Initializing recording context @ 16kHz...");
        recordingContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        await recordingContext.audioWorklet.addModule('/static/pcm-processor.js');
    }

    if (playbackContext.state === 'suspended') await playbackContext.resume();
    if (recordingContext.state === 'suspended') await recordingContext.resume();
    console.log("[Audio] Audio contexts ready (Input: 16kHz, Output: 24kHz).");
}

// Use a one-time click listener to unlock AudioContext early
window.addEventListener('click', () => {
    ensureAudioContexts().catch(console.error);
}, { once: true });

let currentSender = null;
let currentMessageContentDiv = null;
let visualizerInterval = null;

// Audio player state
let activeAudio = null;
let activeButton = null;

// Initialize Visualizer Bars
function initVisualizer() {
    visualizer.innerHTML = '';
    for (let i = 0; i < 24; i++) {
        const bar = document.createElement('div');
        bar.className = 'bar';
        visualizer.appendChild(bar);
    }
}
initVisualizer();

function updateVisualizer(active) {
    const bars = visualizer.querySelectorAll('.bar');
    if (!active) {
        bars.forEach(bar => bar.style.height = '4px');
        if (visualizerInterval) clearInterval(visualizerInterval);
        return;
    }

    visualizerInterval = setInterval(() => {
        const center = bars.length / 2;
        bars.forEach((bar, index) => {
            const distance = Math.abs(center - index);
            const factor = 1 - (distance / center);
            const height = Math.random() * (32 * factor) + 4;
            bar.style.height = `${height}px`;
        });
    }, 80);
}

function appendMessage(sender, text, isHistory = false, audioPath = null, msg = {}) {
    // Clear welcome screen if it exists
    if (transcriptArea.querySelector('.welcome-screen')) {
        transcriptArea.innerHTML = '';
    }

    if (!isHistory && currentSender === sender && currentMessageContentDiv) {
        currentMessageContentDiv.innerText += text;
    } else {
        const wrapper = document.createElement('div');
        wrapper.className = `message-wrapper ${sender === 'User' ? 'user' : 'assistant'}`;

        const senderLabel = document.createElement('div');
        senderLabel.className = 'message-sender';
        senderLabel.innerText = sender;

        currentMessageContentDiv = document.createElement('div');
        currentMessageContentDiv.className = 'message-content';
        currentMessageContentDiv.innerText = text;

        wrapper.appendChild(senderLabel);
        wrapper.appendChild(currentMessageContentDiv);

        if (audioPath) {
            const audioActionContainer = document.createElement('div');
            audioActionContainer.className = 'audio-player-pill';

            const playBtn = document.createElement('button');
            playBtn.className = 'audio-play-btn';
            playBtn.innerHTML = icons.play;
            playBtn.onclick = () => playAudio(playBtn, audioPath);

            const waveforms = document.createElement('div');
            waveforms.className = 'audio-waveforms';
            for (let i = 0; i < 20; i++) {
                const waveform = document.createElement('div');
                waveform.className = 'waveform-bar';
                if (Math.random() > 0.5) waveform.style.height = `${Math.random() * 8 + 4}px`;
                waveforms.appendChild(waveform);
            }

            const durationLabel = document.createElement('span');
            durationLabel.className = 'audio-duration';
            
            // Use server-provided duration if available, otherwise show placeholder
            if (msg.duration_ms) {
                const secs = Math.round(msg.duration_ms / 1000);
                durationLabel.innerText = `${secs}s`;
            } else {
                durationLabel.innerText = '...';
                // Fallback for new messages where duration isn't in the object yet
                const tempAudio = new Audio(audioPath);
                tempAudio.onloadedmetadata = () => {
                    durationLabel.innerText = `${Math.round(tempAudio.duration)}s`;
                };
            }

            audioActionContainer.appendChild(playBtn);
            audioActionContainer.appendChild(waveforms);
            audioActionContainer.appendChild(durationLabel);
            wrapper.appendChild(audioActionContainer);
        }

        transcriptArea.appendChild(wrapper);
        currentSender = sender;
    }
    // Smooth scroll to bottom
    if (!isHistory) {
        transcriptArea.scrollTo({
            top: transcriptArea.scrollHeight,
            behavior: 'smooth'
        });
    } else {
        transcriptArea.scrollTop = transcriptArea.scrollHeight;
    }
}

// Session Management Logic
async function fetchSessions() {
    try {
        const response = await fetch('/api/sessions');
        const sessions = await response.json();
        renderSessions(sessions);
    } catch (err) {
        console.error('Failed to fetch sessions:', err);
    }
}

function renderSessions(sessions) {
    sessionList.innerHTML = '';
    sessions.forEach(session => {
        const item = document.createElement('div');
        item.className = `session-item ${currentSessionId === session.id ? 'active' : ''}`;
        item.onclick = () => selectSession(session.id, session.rating);

        const date = new Date(session.created_at).toLocaleDateString(undefined, {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });

        item.innerHTML = `
            <div class="session-title">${session.title}</div>
            <div class="session-meta">
                <span class="session-date">${date}</span>
                <span class="session-id">#${session.id}</span>
            </div>
            <button class="delete-session-btn" title="Delete Session">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18m-2 0v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
            </button>
        `;

        const deleteBtn = item.querySelector('.delete-session-btn');
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            if (confirm('Are you sure you want to delete this session?')) {
                deleteSession(session.id);
            }
        };

        sessionList.appendChild(item);
    });
}

async function deleteSession(id) {
    try {
        const response = await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        if (response.ok) {
            if (currentSessionId === id) {
                newChatBtn.click();
            } else {
                fetchSessions();
            }
        }
    } catch (err) {
        console.error('Failed to delete session:', err);
    }
}

async function selectSession(id, rating = null) {
    if (ws) {
        ws.close();
    }

    currentSessionId = id;
    fetchSessions(); // Refresh list to show active state

    // Show sync button for historical session
    if (syncBtn) syncBtn.style.display = 'flex';

    transcriptArea.innerHTML = '<div class="session-skeleton"></div><div class="session-skeleton"></div>';

    try {
        // Fetch absolute latest session info (including rating & summary)
        const sessRes = await fetch(`/api/sessions/${id}`);
        const session = await sessRes.json();
        const latestRating = session.rating;

        const msgRes = await fetch(`/api/sessions/${id}/messages`);
        const messages = await msgRes.json();
 
        transcriptArea.innerHTML = ''; // Clear skeleton
        currentSender = null;
        currentMessageContentDiv = null;
 
        if (messages.length === 0) {
            transcriptArea.innerHTML = `
                <div class="welcome-screen">
                    <div class="welcome-orb"></div>
                    <h2>No messages yet</h2>
                    <p>Start a call to begin talking in this session.</p>
                </div>`;
        } else {
            messages.forEach(msg => appendMessage(msg.sender, msg.text, true, msg.audio_path, msg));
        }
 
        // Restore summary from DB or cache
        const summaryToUse = session.summary || getSavedSummary(id);
        if (summaryToUse) {
            showSummaryCard({ summary: summaryToUse, rating: latestRating });
        } else {
            hideSummaryCard();
        }

    } catch (err) {
        console.error('Failed to load history:', err);
    }
}

const icons = {
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>'
};

function playAudio(btn, url) {
    if (activeAudio && activeAudio.src.includes(url)) {
        if (activeAudio.paused) {
            activeAudio.play();
            btn.innerHTML = icons.pause;
            btn.classList.add('playing');
        } else {
            activeAudio.pause();
            btn.innerHTML = icons.play;
            btn.classList.remove('playing');
        }
        return;
    }

    // Stop current audio if any
    if (activeAudio) {
        activeAudio.pause();
        if (activeButton) {
            activeButton.innerHTML = icons.play;
            activeButton.classList.remove('playing');
        }
    }

    // Start new audio
    activeAudio = new Audio(url);
    activeButton = btn;

    activeAudio.play();
    btn.innerHTML = icons.pause;
    btn.classList.add('playing');

    activeAudio.onended = () => {
        btn.innerHTML = icons.play;
        btn.classList.remove('playing');
        activeAudio = null;
        activeButton = null;
    };
}

newChatBtn.onclick = () => {
    if (ws) ws.close();
    currentSessionId = null;
    currentSender = null;
    currentMessageContentDiv = null;
    if (syncBtn) syncBtn.style.display = 'none';
    transcriptArea.innerHTML = `
        <div class="welcome-screen">
            <div class="welcome-orb"></div>
            <h2>Conversational AI</h2>
            <p>Click start to begin a real-time voice conversation</p>
            <div class="feature-pills">
                <div class="feature-pill">Real-time Audio</div>
                <div class="feature-pill">Auto Transcription</div>
                <div class="feature-pill">Cloud Backup</div>
            </div>
        </div>
        `;
    fetchSessions();
};

// Optimized 16-bit PCM to Float32 conversion for 24kHz stream
function processAudioChunk(arrayBuffer) {
    if (!playbackProcessorNode) return;

    const view = new DataView(arrayBuffer);
    const numSamples = arrayBuffer.byteLength / 2;
    const float32Data = new Float32Array(numSamples);

    for (let i = 0; i < numSamples; i++) {
        const val = view.getInt16(i * 2, true);
        float32Data[i] = val / 32768.0;
    }

    playbackProcessorNode.port.postMessage({
        type: 'samples',
        samples: float32Data
    });
}

function flushPlayback() {
    if (playbackProcessorNode) {
        playbackProcessorNode.port.postMessage({ type: 'flush' });
    }
    if (currentSender === 'Assistant' && currentMessageContentDiv) {
        if (!currentMessageContentDiv.innerText.endsWith(' [Interrupted]')) {
            currentMessageContentDiv.innerText += ' [Interrupted]';
            currentMessageContentDiv.style.opacity = '0.6';
        }
    }
}

function connectWebSocket() {
    console.log("Connecting to WebSocket...");
    const selectedVoice = currentVoice;
    const baseUrl = currentSessionId ? `ws://${location.host}/ws/${currentSessionId}` : `ws://${location.host}/ws`;
    const url = `${baseUrl}?voice=${selectedVoice}`;
    console.log("[WS] Connecting to:", url);

    // UI feedback: Show the selected voice in the status badge while connecting
    if (connText) connText.innerText = `Connecting (${selectedVoice})...`;

    ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';

    // Force a new message bubble for the new connection
    currentSender = null;
    currentMessageContentDiv = null;

    // Show connecting UI (briefly, until WS opens)
    console.log("[UI] Attempting to show callingOverlay:", callingOverlay);
    if (callingOverlay) {
        callingOverlay.style.display = 'flex';
        console.log("[UI] callingOverlay display set to flex");
    } else {
        console.error("[UI] callingOverlay element NOT found!");
        // Try to find it again just in case
        const retryOverlay = document.getElementById('callingOverlay');
        if (retryOverlay) retryOverlay.style.display = 'flex';
    }


    ws.onopen = () => {
        connStatus.classList.add('connected');
        connText.innerText = 'Live';
        startRecording();
    };

    ws.onclose = async () => {
        connStatus.classList.remove('connected');
        connText.innerText = 'Disconnected';

        // Clear connecting state if it was still active
        if (callingOverlay) callingOverlay.style.display = 'none';

        // Capture session id before stopRecording can reset state
        const closedSessionId = currentSessionId;
        stopRecording();
        fetchSessions();
        
        // Reorder Post-Call Flow: Rating First, Summary in background
        if (closedSessionId) {
            console.log('[SEQUENCE] 1. Triggering Rating Modal First');
            summaryReady = false;
            ratingFinished = false;
            pendingSummary = null;
            currentRatingInHeader = null;
            
            showRatingModal(closedSessionId);
            
            console.log('[SEQUENCE] 2. Generating Summary in Background');
            generateAndStoreSummary(closedSessionId);
        }




    };

    ws.onmessage = async (event) => {
        if (typeof event.data === 'string') {
            const data = JSON.parse(event.data);
            if (data.type === 'session_init') {
                // Server tells us the real session id (critical for new sessions)
                currentSessionId = data.session_id;
                console.log('[WS] Session ID received from server:', currentSessionId);
            } else if (data.type === 'greeting_complete') {
                agentOpeningComplete = true;
                console.log('[Audio] AI Greeting finished. User microphone transmission enabled.');
            } else if (data.type === 'clear_audio_queue') {
                flushPlayback(); // Mark current as interrupted
                currentSender = null;
                currentMessageContentDiv = null;
            } else if (data.type === 'new_bubble') {
                // Just break the bubble link, don't mark as interrupted
                currentSender = null;
                currentMessageContentDiv = null;
                console.log('[UI] Forcing new message bubble');
            } else if (data.type === 'transcript') {

                // As soon as we get the first transcript or response, stop the ringing
                if (callingOverlay) callingOverlay.style.display = 'none';


                appendMessage(data.sender, data.text);
            } else if (data.type === 'latency') {
                if (latencyInfo) {
                    latencyInfo.style.display = 'flex';
                    currentLatency.innerText = `${data.current}ms`;
                    avgLatency.innerText = `${data.avg}ms`;
                }
            }
        } else {
            // First audio chunk also stops the ringing
            if (callingOverlay) callingOverlay.style.display = 'none';


            processAudioChunk(event.data);
        }
    };
}

async function startRecording() {
    await ensureAudioContexts();

    try {
        const constraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
                sampleRate: 16000
            }
        };
        mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        const source = recordingContext.createMediaStreamSource(mediaStream);

        inputProcessorNode = new AudioWorkletNode(recordingContext, 'pcm-processor');
        inputProcessorNode.port.onmessage = (e) => {
            if (ws && ws.readyState === WebSocket.OPEN && agentOpeningComplete) {
                ws.send(e.data.buffer);
            }
        };

        source.connect(inputProcessorNode);
        inputProcessorNode.connect(recordingContext.destination);

        micBtn.classList.add('active');

        statusText.innerText = 'End Call';
        if (voiceSelectorContainer) voiceSelectorContainer.style.display = 'none';
        updateVisualizer(true);
    } catch (err) { console.error(err); }
}

function stopRecording() {
    flushPlayback();
    agentOpeningComplete = false;

    if (inputProcessorNode) { inputProcessorNode.disconnect(); inputProcessorNode = null; }
    if (mediaStream) { mediaStream.getTracks().forEach(track => track.stop()); mediaStream = null; }

    if (recordingContext) recordingContext.suspend();
    if (playbackContext) playbackContext.suspend();

    micBtn.classList.remove('active');
    statusText.innerText = 'Start Support Call';
    if (voiceSelectorContainer) voiceSelectorContainer.style.display = 'flex';
    if (latencyInfo) latencyInfo.style.display = 'none';
    updateVisualizer(false);


    // Reset sender state so the next call starts a new bubble
    currentSender = null;
    currentMessageContentDiv = null;
}

micBtn.onclick = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
    } else if (micBtn.classList.contains('active')) {
        stopRecording();
        ws.close();
    } else {
        startRecording();
    }
};

async function syncFromCloud() {
    if (!currentSessionId || !syncBtn) return;

    syncBtn.classList.add('syncing');
    try {
        const response = await fetch(`/api/sessions/${currentSessionId}/sync`, { method: 'POST' });
        const result = await response.json();
        if (result.status === 'success') {
            await selectSession(currentSessionId); // Reload
        }
    } catch (err) {
        console.error('Sync failed:', err);
    } finally {
        syncBtn.classList.remove('syncing');
    }
}

if (syncBtn) syncBtn.onclick = syncFromCloud;

// ── Post-Call Summary ─────────────────────────────────────────────────────────

async function generateAndStoreSummary(sessionId) {
    try {
        // Fetch from API in background
        const res = await fetch(`/api/sessions/${sessionId}/summary`, { method: 'POST' });
        const data = await res.json();
 
        if (data.status === 'success' && data.summary) {
            pendingSummary = data.summary;
            summaryReady = true;
            localStorage.setItem(`summary_${sessionId}`, JSON.stringify(data.summary));
            console.log('[SEQUENCE] Summary Ready in background. Rating from DB:', data.rating);
 
            // If user already finished rating, show the card now
            // We use the rating from the DB response to ensure accuracy
            if (ratingFinished) {
                showSummaryCard({ summary: pendingSummary, rating: data.rating || currentRatingInHeader });
            }
        }
    } catch (err) {
        console.error('[CRITICAL] Summary background fetch failed:', err);
        summaryReady = true; // Mark as "done" but with null pendingSummary
        if (ratingFinished) hideSummaryCard();
    }
}




function getSavedSummary(sessionId) {
    try {
        const raw = localStorage.getItem(`summary_${sessionId}`);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function showSummaryCard({ loading = false, summary = null, rating = null } = {}) {
    let card = document.getElementById('summaryCard');
    const transcriptArea = document.getElementById('transcriptArea');

    if (!card) {
        card = document.createElement('div');
        card.id = 'summaryCard';
        card.className = 'summary-card';
        // Insert at the very top of the transcript area so it scrolls with history
        transcriptArea.prepend(card);
    }

    if (loading) {
        card.className = 'summary-card loading';
        card.innerHTML = `
            <div class="summary-header">
                <div class="summary-spinner"></div>
                <span class="summary-title-text">Generating call summary…</span>
            </div>`;
        card.style.display = 'block';
        return;
    }

    if (!summary) { 
        console.warn('[Summary] showSummaryCard called with null summary');
        hideSummaryCard(); 
        return; 
    }

    const sentimentEmoji = { positive: '😊', neutral: '😐', negative: '😟', escalated: '🚨' };
    const sentimentClass = { positive: 'sentiment-positive', neutral: 'sentiment-neutral', negative: 'sentiment-negative', escalated: 'sentiment-escalated' };
    const emoji = sentimentEmoji[summary.sentiment] || '😐';
    const sClass = sentimentClass[summary.sentiment] || 'sentiment-neutral';

    const keyTopicsHTML = (summary.key_topics || []).map(t =>
        `<span class="summary-tag">${t}</span>`
    ).join('');

    const actionItemsHTML = (summary.action_items || []).length > 0
        ? `<div class="summary-section">
                <div class="summary-section-label">Action Items</div>
                <ul class="summary-action-list">${(summary.action_items || []).map(a => `<li>${a}</li>`).join('')}</ul>
           </div>`
        : '';

    // Handle Rating Display
    let ratingHTML = '';
    if (rating) {
        const stars = '⭐'.repeat(rating);
        ratingHTML = `<span class="summary-rating-header">${stars} ${rating}/5</span>`;
    }

    card.className = 'summary-card';
    card.innerHTML = `
        <div class="summary-header">
            <div class="summary-icon">📋</div>
            <div class="summary-title-text">${summary.title || 'Call Summary'}</div>
            ${ratingHTML}
            <span class="summary-sentiment-badge ${sClass}">${emoji} ${summary.sentiment || 'neutral'}</span>
            <button class="summary-close-btn" onclick="hideSummaryCard()" title="Dismiss">✕</button>
        </div>
        <div class="summary-body">
            ${summary.language ? `<div class="summary-section">
                <div class="summary-section-label">Language</div>
                <p class="summary-text">${summary.language}</p>
            </div>` : ''}
            ${summary.customer_intent ? `<div class="summary-section">
                <div class="summary-section-label">Customer Intent</div>
                <p class="summary-text">${summary.customer_intent}</p>
            </div>` : ''}
            <div class="summary-section">
                <div class="summary-section-label">Summary</div>
                <p class="summary-text">${summary.summary || ''}</p>
            </div>
            ${summary.resolution ? `<div class="summary-section">
                <div class="summary-section-label">Resolution</div>
                <p class="summary-text">${summary.resolution}</p>
            </div>` : ''}
            ${actionItemsHTML}
            ${keyTopicsHTML ? `<div class="summary-topics">${keyTopicsHTML}</div>` : ''}
        </div>`;
    card.style.display = 'block';
}

function hideSummaryCard() {
    const card = document.getElementById('summaryCard');
    if (card) card.style.display = 'none';
}

// Initial load
fetchSessions();
initRatingListeners();