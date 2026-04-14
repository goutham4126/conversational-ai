let ws = null;
let inputContext = null;
let outputContext = null;
let mediaStream = null;
let inputProcessorNode = null;
let playbackProcessorNode = null;

let currentSessionId = null;

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

let currentSender = null;
let currentMessageContentDiv = null;
let visualizerInterval = null;

// Audio player state
let activeAudio = null;
let activeButton = null;

// Initialize Visualizer Bars
function initVisualizer() {
    visualizer.innerHTML = '';
    for (let i = 0; i < 20; i++) {
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
        bars.forEach(bar => {
            const height = Math.random() * 30 + 4;
            bar.style.height = `${height}px`;
        });
    }, 100);
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
            audioActionContainer.className = 'audio-action-container';

            const playBtn = document.createElement('button');
            playBtn.className = 'audio-play-btn';
            playBtn.innerHTML = icons.play;
            playBtn.onclick = () => playAudio(playBtn, audioPath);
            
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
                    <div class="welcome-icon">🎙️</div>
                    <h2>No messages yet</h2>
                    <p>Start a call to begin talking in this session.</p>
                </div>`;
        } else {
            messages.forEach(msg => appendMessage(msg.sender, msg.text, true, msg.audio_path));
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
            <div class="welcome-icon">🎙️</div>
            <h2>New Session</h2>
            <p>Ready for a fresh start. Start a call when you're ready.</p>
        </div>`;
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
    const url = currentSessionId ? `ws://${location.host}/ws/${currentSessionId}` : `ws://${location.host}/ws`;
    ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        connStatus.classList.add('connected');
        connText.innerText = 'Live';
        startRecording();
    };

    ws.onclose = () => {
        connStatus.classList.remove('connected');
        connText.innerText = 'Disconnected';
        stopRecording();
        fetchSessions(); // Refresh sessions to show the new one if it was created
    };

    ws.onmessage = async (event) => {
        if (typeof event.data === 'string') {
            const data = JSON.parse(event.data);
            if (data.type === 'clear_audio_queue') flushPlayback();
            else if (data.type === 'transcript') appendMessage(data.sender, data.text);
            else if (data.type === 'latency') {
                if (latencyInfo) {
                    latencyInfo.style.display = 'flex';
                    currentLatency.innerText = `${data.current}ms`;
                    avgLatency.innerText = `${data.avg}ms`;
                }
            }
        } else {
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

// Initial load
fetchSessions();