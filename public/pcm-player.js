class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.queuedSamples = 0;
    this.playing = false;
    this.maxQueuedSamples = Math.round(sampleRate * 3);
    this.port.onmessage = (event) => {
      if (event.data?.action === "clear") {
        this.queue = [];
        this.queuedSamples = 0;
        this.setPlaying(false);
      } else if (event.data?.length) {
        this.queue.push(event.data);
        this.queuedSamples += event.data.length;
        // Do not play an ever-growing stale response after a slow frame. Keep
        // the newest audio and cap the added latency to three seconds.
        while (this.queuedSamples > this.maxQueuedSamples && this.queue.length > 1) {
          const dropped = this.queue.shift();
          this.queuedSamples -= dropped.length;
        }
        this.setPlaying(true);
      }
    };
  }

  setPlaying(active) {
    if (this.playing === active) return;
    this.playing = active;
    this.port.postMessage({ type: "playback-state", active });
  }

  process(_inputs, outputs) {
    const channel = outputs[0][0];
    let offset = 0;

    while (offset < channel.length && this.queue.length > 0) {
      const chunk = this.queue[0];
      const count = Math.min(chunk.length, channel.length - offset);
      channel.set(chunk.subarray(0, count), offset);
      offset += count;
      this.queuedSamples -= count;
      if (count === chunk.length) this.queue.shift();
      else this.queue[0] = chunk.subarray(count);
    }

    if (offset < channel.length) channel.fill(0, offset);
    if (this.queue.length === 0) this.setPlaying(false);
    return true;
  }
}

registerProcessor("pcm-player", PCMPlayer);
