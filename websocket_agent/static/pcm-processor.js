class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 1024 samples @ 16kHz is 64ms per chunk (reduces packet frequency and network overhead)
    this.bufferSize = 1024;

    this.buffer = new Int16Array(this.bufferSize);
    this.bufferIndex = 0;
    
    // Sliding Window VAD settings
    this.threshold = 0.01;  // Ignore low-level background static/noise
    this.historySize = 4;    // Averaging over ~256ms of history for stability
    this.energyHistory = [];

    // Pre-roll buffer: stores audio during "silence" to prevent clipping the start of speech
    this.preRollCapacity = 4; // Store last ~256ms of audio
    this.preRollBuffer = [];
    this.isSpeaking = false;

    // Hangover settings: keeps sending chunks for a short duration after energy drops below threshold
    this.hangoverCapacity = 6; // Keep sending for ~384ms of silence
    this.hangoverCounter = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      
      // Calculate RMS energy for the current chunk
      let sumSquares = 0;
      for (let i = 0; i < channelData.length; i++) {
        sumSquares += channelData[i] * channelData[i];
      }
      const currentEnergy = Math.sqrt(sumSquares / channelData.length);
      
      // Update sliding history
      this.energyHistory.push(currentEnergy);
      if (this.energyHistory.length > this.historySize) {
        this.energyHistory.shift();
      }
      
      // Calculate average energy over the window
      const avgEnergy = this.energyHistory.reduce((a, b) => a + b, 0) / this.energyHistory.length;

      for (let i = 0; i < channelData.length; i++) {
        const s = Math.max(-1, Math.min(1, channelData[i]));
        this.buffer[this.bufferIndex] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        this.bufferIndex++;

        if (this.bufferIndex >= this.bufferSize) {
          const chunk = this.buffer.slice(0);
          
          if (avgEnergy > this.threshold) {
             // Voice detected! Reset hangover counter and mark as speaking
             this.hangoverCounter = this.hangoverCapacity;
             
             if (!this.isSpeaking) {
                // Flush pre-roll buffer first so Gemini gets the start of the sentence
                while (this.preRollBuffer.length > 0) {
                   this.port.postMessage(this.preRollBuffer.shift());
                }
                this.isSpeaking = true;
             }
             this.port.postMessage(chunk);
          } else {
             // Silence detected: check if we are in hangover period
             if (this.isSpeaking && this.hangoverCounter > 0) {
                this.hangoverCounter--;
                this.port.postMessage(chunk); // Keep sending during hangover
             } else {
                // Hangover ended: instead of dropping packets (which causes WebSocket stalls/latencies 
                // on the server's jitter buffer), we stream clean absolute silence (all zeros).
                // This keeps the server's clock ticking and allows the model's VAD to work instantly.
                this.isSpeaking = false;
                
                const silentChunk = new Int16Array(this.bufferSize); // automatically 0-filled
                this.port.postMessage(silentChunk);

                this.preRollBuffer.push(chunk);
                if (this.preRollBuffer.length > this.preRollCapacity) {
                   this.preRollBuffer.shift();
                }
             }
          }
          
          this.buffer = new Int16Array(this.bufferSize);
          this.bufferIndex = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);