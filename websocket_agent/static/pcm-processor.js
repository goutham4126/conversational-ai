class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 512;
    this.buffer = new Int16Array(this.bufferSize);
    this.bufferIndex = 0;
    
    // Sliding Window VAD settings
    this.threshold = 0.004; // RMS energy threshold
    this.historySize = 3;  // Reduced from 5 to 3 for ultra-low latency
    this.energyHistory = [];
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
          // Only send the chunk to the WebSocket if the average energy is above threshold
          // This rejects impulsive noise (claps) and constant mic hiss
          if (avgEnergy > this.threshold) {
             this.port.postMessage(this.buffer.slice(0));
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