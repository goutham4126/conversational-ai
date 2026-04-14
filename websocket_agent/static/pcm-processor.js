class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // FIX: Increased buffer size to 4096 for smoother audio streaming
    // 2048 was too small and caused choppy audio on slower connections
    this.bufferSize = 1024;
    this.buffer = new Int16Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      for (let i = 0; i < channelData.length; i++) {
        // FIX: Clamp float to [-1.0, 1.0] then convert to Int16
        const s = Math.max(-1, Math.min(1, channelData[i]));
        this.buffer[this.bufferIndex] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        this.bufferIndex++;

        if (this.bufferIndex >= this.bufferSize) {
          // FIX: Send a copy of the buffer — not the same reference
          // Original code reused the same Int16Array which caused race conditions
          // where the buffer was cleared before it was sent over the WebSocket
          this.port.postMessage(this.buffer.slice(0));
          this.buffer = new Int16Array(this.bufferSize);
          this.bufferIndex = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);