/**
 * AudioManager handles:
 * 1. Initializing Web Audio API AudioContext & AnalyserNode
 * 2. Connecting microphone input for visualizer
 * 3. Connecting audio playback element for visualizer
 * 4. Cleaning up resources to prevent memory leaks
 */
export class AudioManager {
  constructor() {
    this.audioContext = null;
    this.analyser = null; // For playback
    this.micAnalyser = null; // For microphone
    
    this.micStream = null;
    this.micSource = null;
    
    this.audioElement = null;
    this.playbackSource = null;
    this.dataArray = null;
    this.micDataArray = null;
  }

  init() {
    if (this.audioContext) return;

    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      this.analyser = this.audioContext.createAnalyser();
      this.micAnalyser = this.audioContext.createAnalyser();
      
      // FFT size determines wave detail. 256 or 512 is great for visualizers
      this.analyser.fftSize = 256;
      this.micAnalyser.fftSize = 256;
      
      const bufferLength = this.analyser.frequencyBinCount;
      this.dataArray = new Uint8Array(bufferLength);
      this.micDataArray = new Uint8Array(bufferLength);
    } catch (e) {
      console.error("Web Audio API is not supported in this browser:", e);
    }
  }

  async startMicAnalysis() {
    this.init();
    this.stopMicAnalysis(); // Reset if already running

    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      if (this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      this.micSource = this.audioContext.createMediaStreamSource(this.micStream);
      // Connect to micAnalyser ONLY. Do NOT connect to destination to prevent echo loopback.
      this.micSource.connect(this.micAnalyser);
      return this.micStream;
    } catch (err) {
      console.error("Error accessing microphone:", err);
      throw err;
    }
  }

  stopMicAnalysis() {
    if (this.micSource) {
      this.micSource.disconnect();
      this.micSource = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach(track => track.stop());
      this.micStream = null;
    }
  }

  connectPlayback(audioElement) {
    this.init();
    
    // Only connect if it's a new audio element and not already connected
    if (this.audioElement === audioElement && this.playbackSource) {
      return;
    }

    this.disconnectPlayback();
    this.audioElement = audioElement;

    try {
      this.playbackSource = this.audioContext.createMediaElementSource(audioElement);
      this.playbackSource.connect(this.analyser);
      this.analyser.connect(this.audioContext.destination);
    } catch (e) {
      console.error("Failed to connect audio element to Web Audio API:", e);
      // Fallback: connect directly if createMediaElementSource fails
    }
  }

  disconnectPlayback() {
    if (this.playbackSource) {
      try {
        this.playbackSource.disconnect();
      } catch (e) {
        // ignore
      }
      this.playbackSource = null;
    }
    this.audioElement = null;
  }

  getByteFrequencyData() {
    if (!this.analyser || !this.dataArray) return null;
    
    this.analyser.getByteFrequencyData(this.dataArray);
    
    if (this.micAnalyser && this.micSource) {
      this.micAnalyser.getByteFrequencyData(this.micDataArray);
      // Merge the mic data and playback data for the visualizer
      for(let i = 0; i < this.dataArray.length; i++) {
        this.dataArray[i] = Math.max(this.dataArray[i], this.micDataArray[i]);
      }
    }
    
    return this.dataArray;
  }

  getByteTimeDomainData() {
    if (!this.analyser || !this.dataArray) return null;

    this.analyser.getByteTimeDomainData(this.dataArray);
    
    if (this.micAnalyser && this.micSource) {
      this.micAnalyser.getByteTimeDomainData(this.micDataArray);
      // Merge the mic data and playback data for the visualizer
      for(let i = 0; i < this.dataArray.length; i++) {
        // For time domain, 128 is silence. Take whichever is further from 128.
        const diff1 = Math.abs(this.dataArray[i] - 128);
        const diff2 = Math.abs(this.micDataArray[i] - 128);
        if (diff2 > diff1) {
          this.dataArray[i] = this.micDataArray[i];
        }
      }
    }

    return this.dataArray;
  }

  close() {
    this.stopMicAnalysis();
    this.disconnectPlayback();
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
      this.analyser = null;
      this.micAnalyser = null;
      this.dataArray = null;
      this.micDataArray = null;
    }
  }
}
