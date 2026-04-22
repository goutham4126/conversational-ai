class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 256;

    this.buffer = new Int16Array(this.bufferSize);
    this.bufferIndex = 0;
    
    // Sliding Window VAD settings
    this.threshold = 0.004; // RMS energy threshold
    this.historySize = 2;   // Reduced from 3 to 2 for even faster trigger
    this.energyHistory = [];

    // Pre-roll buffer: stores audio during "silence" to prevent clipping the start of speech
    this.preRollCapacity = 10; // Store last ~320ms of audio
    this.preRollBuffer = [];
    this.isSpeaking = false;
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
             // Voice detected!
             if (!this.isSpeaking) {
                // Flush pre-roll buffer first so Gemini gets the start of the sentence
                while (this.preRollBuffer.length > 0) {
                   this.port.postMessage(this.preRollBuffer.shift());
                }
                this.isSpeaking = true;
             }
             this.port.postMessage(chunk);
          } else {
             // Silence: store in pre-roll
             this.isSpeaking = false;
             this.preRollBuffer.push(chunk);
             if (this.preRollBuffer.length > this.preRollCapacity) {
                this.preRollBuffer.shift();
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