class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.port.onmessage = (event) => {
      if (event.data?.action === "clear") {
        this.queue = [];
      } else if (event.data?.length) {
        this.queue.push(event.data);
      }
    };
  }

  process(_inputs, outputs) {
    const channel = outputs[0][0];
    let offset = 0;

    while (offset < channel.length && this.queue.length > 0) {
      const chunk = this.queue[0];
      const count = Math.min(chunk.length, channel.length - offset);
      channel.set(chunk.subarray(0, count), offset);
      offset += count;
      if (count === chunk.length) this.queue.shift();
      else this.queue[0] = chunk.subarray(count);
    }

    if (offset < channel.length) channel.fill(0, offset);
    return true;
  }
}

registerProcessor("pcm-player", PCMPlayer);
