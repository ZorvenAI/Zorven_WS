/**
 * Picks which mic feeds STT at any moment (O-09 AC-3, AC-4).
 *
 * Separate mics in one room hear each other. Feeding all of them to STT
 * transcribes the same utterance several times, once per mic, and O-08 then
 * attributes each copy to a different speaker — so the record says two people
 * said the same sentence. The gate opens exactly one channel at a time.
 *
 * Pure so it can be tested without a real `AudioContext`: the caller supplies
 * per-channel RMS and a clock, and gets back the channel that should be open.
 */

/** RMS below this is treated as silence, not speech. */
export const MIN_RMS = 0.01;

/**
 * How long a channel stays open after another one gets louder.
 *
 * Overlapping speech makes the loudest channel flip several times a second.
 * Without a hold, the open channel would change mid-word and split one
 * utterance across two speakers.
 */
export const HOLD_MS = 300;

export interface GateDecision {
  /** The channel that should feed STT, or null before any speech. */
  active: number | null;
  /** True when this call changed the open channel. */
  changed: boolean;
}

export class EnergyGate {
  private active: number | null = null;
  private openedAt = 0;

  constructor(
    private readonly minRms: number = MIN_RMS,
    private readonly holdMs: number = HOLD_MS,
  ) {}

  /**
   * Decide which channel is open, given each channel's current RMS.
   *
   * During global silence the previously open channel stays open rather than
   * closing. A closed gate would starve the STT stream, and
   * `GoogleSTTAdapter` drives its rollover from arriving chunks — so a stream
   * fed nothing sails past Google's ~300 s cap without rolling over and is
   * dead when somebody finally speaks. Holding the last channel keeps the
   * stream fed with the near-silence a single mic would have sent anyway.
   */
  decide(rms: Map<number, number>, now: number): GateDecision {
    let loudest: number | null = null;
    let peak = 0;
    // Ascending, so an exact tie resolves to the lower index rather than to
    // whichever order the caller happened to build the map in.
    for (const channel of [...rms.keys()].sort((a, b) => a - b)) {
      const value = rms.get(channel) ?? 0;
      if (value > peak) {
        peak = value;
        loudest = channel;
      }
    }

    if (loudest === null || peak < this.minRms) {
      return { active: this.active, changed: false };
    }

    if (this.active === null) {
      this.active = loudest;
      this.openedAt = now;
      return { active: this.active, changed: true };
    }

    if (loudest === this.active) {
      // Re-arm the hold: a channel that keeps talking should not become
      // swappable just because it has been open a while.
      this.openedAt = now;
      return { active: this.active, changed: false };
    }

    if (now - this.openedAt < this.holdMs) {
      return { active: this.active, changed: false };
    }

    this.active = loudest;
    this.openedAt = now;
    return { active: this.active, changed: true };
  }

  /** The currently open channel, without re-deciding. */
  get current(): number | null {
    return this.active;
  }
}

/** RMS of a Web Audio time-domain byte buffer, where 128 is silence. */
export function rmsOf(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (const sample of samples) {
    const centred = (sample - 128) / 128;
    sum += centred * centred;
  }
  return Math.sqrt(sum / samples.length);
}
