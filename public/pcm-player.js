class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.queuedSamples = 0;
    this.playing = false;
    this.started = false;
    // Native audio arrives faster than realtime. Dropping the oldest chunks here
    // cuts words out of normal replies, so retain a bounded full response instead.
    this.maxQueuedSamples = Math.round(sampleRate * 60);
    this.prebufferSamples = Math.round(sampleRate * 0.12);
    this.port.onmessage = (event) => {
      if (event.data?.action === "clear") {
        this.queue = [];
        this.queuedSamples = 0;
        this.started = false;
        this.setPlaying(false);
      } else if (event.data?.action === "flush") {
        if (!this.started && this.queuedSamples > 0) {
          this.started = true;
          this.setPlaying(true);
        }
      } else if (event.data?.length) {
        if (this.queuedSamples + event.data.length > this.maxQueuedSamples) {
          this.queue = [];
          this.queuedSamples = 0;
          this.started = false;
          this.setPlaying(false);
          this.port.postMessage({ type: "playback-error", reason: "response-too-long" });
          return;
        }
        this.queue.push(event.data);
        this.queuedSamples += event.data.length;
        if (!this.started && this.queuedSamples >= this.prebufferSamples) {
          this.started = true;
          this.setPlaying(true);
        }
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

    if (!this.started) {
      channel.fill(0);
      return true;
    }

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
    if (this.queue.length === 0) {
      this.started = false;
      this.setPlaying(false);
    }
    return true;
  }
}

registerProcessor("pcm-player", PCMPlayer);
