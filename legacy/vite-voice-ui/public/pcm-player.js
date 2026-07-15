class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.port.onmessage = (e) => {
      if (e.data && e.data.action === 'clear') {
        this.buffer = [];
        return;
      }
      // Receive Float32Array from main thread
      if (e.data && e.data.length > 0) {
        this.buffer.push(e.data);
      }
    };
  }

  process(inputs, outputs) {
    const output = outputs[0];
    const channel = output[0];
    
    let channelIndex = 0;
    while (channelIndex < channel.length && this.buffer.length > 0) {
      const currentChunk = this.buffer[0];
      const spaceLeft = channel.length - channelIndex;
      
      if (currentChunk.length <= spaceLeft) {
        channel.set(currentChunk, channelIndex);
        channelIndex += currentChunk.length;
        this.buffer.shift();
      } else {
        channel.set(currentChunk.subarray(0, spaceLeft), channelIndex);
        this.buffer[0] = currentChunk.subarray(spaceLeft);
        channelIndex += spaceLeft;
      }
    }
    
    // Fill the rest with silence if buffer is empty
    if (channelIndex < channel.length) {
      channel.fill(0, channelIndex);
    }
    
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayer);
