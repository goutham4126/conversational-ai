class PlaybackProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.port.onmessage = (event) => {
            if (event.data.type === 'samples') {
                this.buffer.push(...event.data.samples);
            } else if (event.data.type === 'flush') {
                this.buffer = [];
            }
        };
    }

    process(inputs, outputs, parameters) {
        const output = outputs[0];
        const channel = output[0];

        if (this.buffer.length >= channel.length) {
            const samples = this.buffer.splice(0, channel.length);
            for (let i = 0; i < channel.length; i++) {
                channel[i] = samples[i];
            }
        } else {
            // Underrun: not enough samples in buffer
            for (let i = 0; i < channel.length; i++) {
                channel[i] = this.buffer.shift() || 0;
            }
        }

        return true;
    }
}

registerProcessor('playback-processor', PlaybackProcessor);
