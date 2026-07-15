class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 512 samples is 32ms at the 16kHz input rate. Small, regular chunks keep
    // realtime VAD responsive without flooding the websocket with tiny frames.
    this.bufferSize = 512;
    this.buffer = new Float32Array(this.bufferSize);
    this.framesWritten = 0;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;

    for (let index = 0; index < channel.length; index += 1) {
      this.buffer[this.framesWritten] = channel[index];
      this.framesWritten += 1;
      if (this.framesWritten === this.bufferSize) {
        this.port.postMessage(new Float32Array(this.buffer));
        this.framesWritten = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
