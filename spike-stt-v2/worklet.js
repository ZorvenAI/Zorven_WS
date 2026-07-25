/**
 * AudioWorklet processor for STT v2 spike (A-01).
 *
 * Responsibilities:
 * - Detect utterance onset (first frame above noise floor after silence)
 * - Chunk audio into ~100ms LINEAR16 PCM frames at 16kHz
 * - Handle sample rate mismatch (48kHz → 16kHz decimation)
 * - Post onset timestamps and audio chunks to the main thread
 */
class STTWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Onset detection state
    this._silenceFrames = 0;
    this._silenceThresholdFrames = 10; // ~200ms at 128 samples/frame, ~48kHz
    this._noiseFloorDb = -40;
    this._inUtterance = false;

    // Audio buffering
    this._buffer = [];
    this._bufferSamples = 0;
    this._targetSamplesPerChunk = 1600; // 100ms at 16kHz

    // Sample rate handling — AudioWorklet always runs at AudioContext.sampleRate
    // We need 16kHz output; if the context is 48kHz, we decimate by 3
    this._decimationFactor = 1; // Set by main thread via message
    this._inputSampleRate = 48000; // Default assumption

    this.port.onmessage = (event) => {
      if (event.data.type === 'configure') {
        this._inputSampleRate = event.data.sampleRate || 48000;
        this._decimationFactor = Math.round(this._inputSampleRate / 16000);
        if (this._decimationFactor < 1) this._decimationFactor = 1;

        // Recalculate silence threshold based on actual sample rate
        // 200ms of silence = 200ms / (128 samples / sampleRate)
        const samplesPerFrame = 128;
        const msPerFrame = (samplesPerFrame / this._inputSampleRate) * 1000;
        this._silenceThresholdFrames = Math.ceil(200 / msPerFrame);
      }
    };
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) {
      return true;
    }

    const samples = input[0]; // Float32, mono

    // Compute RMS for onset detection
    let sumSq = 0;
    for (let i = 0; i < samples.length; i++) {
      sumSq += samples[i] * samples[i];
    }
    const rms = Math.sqrt(sumSq / samples.length);
    const rmsDb = rms > 0 ? 20 * Math.log10(rms) : -100;

    const aboveFloor = rmsDb > this._noiseFloorDb;

    if (aboveFloor) {
      this._silenceFrames = 0;

      if (!this._inUtterance) {
        // Utterance onset detected
        this._inUtterance = true;
        this.port.postMessage({
          type: 'onset',
          timestamp: currentTime * 1000, // AudioContext currentTime in ms
          performanceNow: Date.now(),     // Wall-clock for correlation
        });
      }
    } else {
      this._silenceFrames++;
      if (this._silenceFrames >= this._silenceThresholdFrames && this._inUtterance) {
        this._inUtterance = false;
        this.port.postMessage({ type: 'silence' });
      }
    }

    // Decimate to 16kHz and convert to LINEAR16 PCM
    const decimated = [];
    for (let i = 0; i < samples.length; i += this._decimationFactor) {
      // Clamp and convert float32 [-1, 1] to int16 [-32768, 32767]
      const s = Math.max(-1, Math.min(1, samples[i]));
      decimated.push(Math.round(s * 32767));
    }

    // Accumulate into buffer
    for (const s of decimated) {
      this._buffer.push(s);
    }
    this._bufferSamples += decimated.length;

    // Flush when we have ~100ms worth of 16kHz audio
    if (this._bufferSamples >= this._targetSamplesPerChunk) {
      const pcm = new Int16Array(this._buffer);
      const bytes = new Uint8Array(pcm.buffer);
      this.port.postMessage(
        { type: 'audio', data: bytes },
        [bytes.buffer] // Transfer ownership for zero-copy
      );
      this._buffer = [];
      this._bufferSamples = 0;
    }

    return true;
  }
}

registerProcessor('stt-worklet-processor', STTWorkletProcessor);
