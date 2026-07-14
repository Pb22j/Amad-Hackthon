class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 2048;
    this._buffer = new Float32Array(this.bufferSize);
    this._framesWritten = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const channelData = input[0];
      for (let i = 0; i < channelData.length; i++) {
        this._buffer[this._framesWritten++] = channelData[i];
        if (this._framesWritten >= this.bufferSize) {
          this.flush();
        }
      }
    }
    return true;
  }

  flush() {
    // We have this._buffer full of 48kHz (usually) float32 audio.
    // Convert to 16kHz Int16.
    // A simple way to downsample from 48kHz to 16kHz is to take every 3rd sample.
    // Note: The main thread will need to handle actual resampling if the source is not exactly 48kHz,
    // but for simplicity, we just send Float32 chunks to main thread and let it resample/encode.
    
    const bufferCopy = new Float32Array(this._buffer);
    this.port.postMessage(bufferCopy);
    this._framesWritten = 0;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
