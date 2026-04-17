let ws = null;
let inputContext = null;
let outputContext = null;
let mediaStream = null;
let inputProcessorNode = null;
let playbackProcessorNode = null;

let currentSessionId = null;
let currentVoice = 'Zephyr';

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

let ringbackTone = null;

class RingbackTone {
    constructor() {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.osc1 = null;
        this.osc2 = null;
        this.gain = null;
        this.isPlaying = false;
    }

    start() {
        if (this.isPlaying) return;
        this.isPlaying = true;
        this.playSequence();
    }

    playSequence() {
        if (!this.isPlaying) return;

        this.osc1 = this.ctx.createOscillator();
        this.osc2 = this.ctx.createOscillator();
        this.gain = this.ctx.createGain();

        this.osc1.frequency.value = 440;
        this.osc2.frequency.value = 480;
        this.gain.gain.value = 0.1;

        this.osc1.connect(this.gain);
        this.osc2.connect(this.gain);
        this.gain.connect(this.ctx.destination);

        this.osc1.start();
        this.osc2.start();

        // US Ringback: 2s on, 4s off
        setTimeout(() => {
            if (this.isPlaying) this.stopCurrent();
            this.timerId = setTimeout(() => this.playSequence(), 4000);
        }, 2000);
    }

    stopCurrent() {
        if (this.osc1) { this.osc1.stop(); this.osc1.disconnect(); }
        if (this.osc2) { this.osc2.stop(); this.osc2.disconnect(); }
        if (this.gain) { this.gain.disconnect(); }
        this.osc1 = null; this.osc2 = null; this.gain = null;
    }

    stop() {
        this.isPlaying = false;
        this.stopCurrent();
        if (this.timerId) clearTimeout(this.timerId);
    }
}

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

function appendMessage(sender, text, isHistory = false, audioPath = null) {
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
            durationLabel.innerText = '...';
            
            // Fetch duration
            const tempAudio = new Audio(audioPath);
            tempAudio.onloadedmetadata = () => {
                const secs = Math.round(tempAudio.duration);
                durationLabel.innerText = `${secs}s`;
            };

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
        item.onclick = () => selectSession(session.id);

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

async function selectSession(id) {
    if (ws) {
        ws.close();
    }

    currentSessionId = id;
    fetchSessions(); // Refresh list to show active state

    // Show sync button for historical session
    if (syncBtn) syncBtn.style.display = 'flex';

    transcriptArea.innerHTML = '<div class="session-skeleton"></div><div class="session-skeleton"></div>';

    try {
        const response = await fetch(`/api/sessions/${id}/messages`);
        const messages = await response.json();

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
            messages.forEach(msg => appendMessage(msg.sender, msg.text, true, msg.audio_path));
        }

        // Restore cached summary if available
        const cached = getSavedSummary(id);
        if (cached) {
            showSummaryCard({ summary: cached });
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

    // Show connecting UI and start sound
    if (callingOverlay) callingOverlay.style.display = 'flex';
    if (!ringbackTone) ringbackTone = new RingbackTone();
    ringbackTone.start();

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
        if (ringbackTone) ringbackTone.stop();
        // Capture session id before stopRecording can reset state
        const closedSessionId = currentSessionId;
        stopRecording();
        fetchSessions();

        // Generate post-call summary for whatever session just ended
        if (closedSessionId) {
            await generateAndStoreSummary(closedSessionId);
        }
    };

    ws.onmessage = async (event) => {
        if (typeof event.data === 'string') {
            const data = JSON.parse(event.data);
            if (data.type === 'session_init') {
                // Server tells us the real session id (critical for new sessions)
                currentSessionId = data.session_id;
                console.log('[WS] Session ID received from server:', currentSessionId);
            } else if (data.type === 'clear_audio_queue') {
                flushPlayback();
                // When interrupted, ensure next AI response starts a new bubble
                currentSender = null;
                currentMessageContentDiv = null;
            } else if (data.type === 'transcript') {
                // As soon as we get the first transcript or response, stop the ringing
                if (callingOverlay) callingOverlay.style.display = 'none';
                if (ringbackTone) ringbackTone.stop();
                
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
            if (ringbackTone) ringbackTone.stop();

            processAudioChunk(event.data);
        }
    };
}

async function startRecording() {
    if (!outputContext) {
        outputContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        await outputContext.audioWorklet.addModule('/static/playback-processor.js');
        playbackProcessorNode = new AudioWorkletNode(outputContext, 'playback-processor');
        playbackProcessorNode.connect(outputContext.destination);
    }
    if (!inputContext) {
        inputContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        await inputContext.audioWorklet.addModule('/static/pcm-processor.js');
    }

    if (outputContext.state === 'suspended') await outputContext.resume();
    if (inputContext.state === 'suspended') await inputContext.resume();

    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const source = inputContext.createMediaStreamSource(mediaStream);

        inputProcessorNode = new AudioWorkletNode(inputContext, 'pcm-processor');
        inputProcessorNode.port.onmessage = (e) => {
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data.buffer);
        };

        source.connect(inputProcessorNode);
        inputProcessorNode.connect(inputContext.destination);

        micBtn.classList.add('active');
        statusText.innerText = 'End Call';
        if (voiceSelectorContainer) voiceSelectorContainer.style.display = 'none';
        updateVisualizer(true);
    } catch (err) { console.error(err); }
}

function stopRecording() {
    flushPlayback();

    if (inputProcessorNode) { inputProcessorNode.disconnect(); inputProcessorNode = null; }
    if (mediaStream) { mediaStream.getTracks().forEach(track => track.stop()); mediaStream = null; }

    if (inputContext) inputContext.suspend();
    if (outputContext) outputContext.suspend();

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
        // Brief delay to let DB writes finish
        await new Promise(r => setTimeout(r, 1500));
        showSummaryCard({ loading: true });

        const res = await fetch(`/api/sessions/${sessionId}/summary`, { method: 'POST' });
        const data = await res.json();

        if (data.status === 'success' && data.summary) {
            // Persist in localStorage keyed by session id
            localStorage.setItem(`summary_${sessionId}`, JSON.stringify(data.summary));
            showSummaryCard({ summary: data.summary });
        } else {
            hideSummaryCard();
        }
    } catch (err) {
        console.error('Summary generation failed:', err);
        hideSummaryCard();
    }
}

function getSavedSummary(sessionId) {
    try {
        const raw = localStorage.getItem(`summary_${sessionId}`);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function showSummaryCard({ loading = false, summary = null } = {}) {
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

    if (!summary) { hideSummaryCard(); return; }

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

    card.className = 'summary-card';
    card.innerHTML = `
        <div class="summary-header">
            <div class="summary-icon">📋</div>
            <div class="summary-title-text">${summary.title || 'Call Summary'}</div>
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