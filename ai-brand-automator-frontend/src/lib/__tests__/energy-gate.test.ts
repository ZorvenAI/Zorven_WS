/**
 * O-09 · the energy gate.
 *
 * The behaviour these pin down is what stops the same utterance being
 * transcribed once per mic and attributed to a different person each time.
 */

import { EnergyGate, HOLD_MS, MIN_RMS, rmsOf } from '@/lib/energy-gate';

describe('O-09 AC-3 · one channel feeds STT at a time', () => {
  it('opens the loudest channel above the threshold', () => {
    const gate = new EnergyGate();

    const decision = gate.decide(
      new Map([
        [0, 0.02],
        [1, 0.31],
      ]),
      0,
    );

    expect(decision.active).toBe(1);
    expect(decision.changed).toBe(true);
  });

  it('suppresses bleed: the quieter mic hearing the same voice stays shut', () => {
    const gate = new EnergyGate();

    // Both mics hear the participant; mic 1 is the one in front of them.
    const decision = gate.decide(
      new Map([
        [0, 0.04],
        [1, 0.28],
      ]),
      0,
    );

    expect(decision.active).toBe(1);
  });

  it('opens nothing while every channel is below the threshold', () => {
    const gate = new EnergyGate();

    const decision = gate.decide(
      new Map([
        [0, MIN_RMS / 2],
        [1, 0],
      ]),
      0,
    );

    expect(decision.active).toBeNull();
  });

  it('resolves an exact tie to the lower index, not to map order', () => {
    const gate = new EnergyGate();

    const decision = gate.decide(
      new Map([
        [2, 0.2],
        [0, 0.2],
      ]),
      0,
    );

    expect(decision.active).toBe(0);
  });
});

describe('O-09 AC-4 · a hold period prevents mid-word switching', () => {
  it('keeps the open channel while the hold is still running', () => {
    const gate = new EnergyGate();
    gate.decide(new Map([[0, 0.3]]), 0);

    // The other speaker briefly gets louder during overlap.
    const decision = gate.decide(
      new Map([
        [0, 0.1],
        [1, 0.4],
      ]),
      HOLD_MS - 50,
    );

    expect(decision.active).toBe(0);
    expect(decision.changed).toBe(false);
  });

  it('switches once the hold has elapsed', () => {
    const gate = new EnergyGate();
    gate.decide(new Map([[0, 0.3]]), 0);

    const decision = gate.decide(
      new Map([
        [0, 0.1],
        [1, 0.4],
      ]),
      HOLD_MS + 1,
    );

    expect(decision.active).toBe(1);
    expect(decision.changed).toBe(true);
  });

  it('re-arms the hold while the same channel keeps talking', () => {
    // Otherwise a channel that had been open a long time would become
    // swappable on the first flicker from another mic.
    const gate = new EnergyGate();
    gate.decide(new Map([[0, 0.3]]), 0);
    gate.decide(new Map([[0, 0.3]]), 5000);

    const decision = gate.decide(
      new Map([
        [0, 0.1],
        [1, 0.4],
      ]),
      5100,
    );

    expect(decision.active).toBe(0);
  });

  it('reports a change only when the open channel actually changes', () => {
    const gate = new EnergyGate();
    const first = gate.decide(new Map([[1, 0.3]]), 0);
    const second = gate.decide(new Map([[1, 0.3]]), 100);

    expect(first.changed).toBe(true);
    expect(second.changed).toBe(false);
  });
});

describe('O-09 · silence holds the channel open rather than closing it', () => {
  /**
   * A closed gate starves the STT stream, and `GoogleSTTAdapter` drives its
   * rollover from arriving chunks — so a stream fed nothing sails past
   * Google's ~300 s cap without rolling over and is dead when somebody
   * finally speaks. Holding the last channel keeps it fed with the
   * near-silence a single mic would have sent anyway.
   */
  it('keeps the last speaker open through a pause', () => {
    const gate = new EnergyGate();
    gate.decide(new Map([[1, 0.3]]), 0);

    const decision = gate.decide(
      new Map([
        [0, 0.001],
        [1, 0.002],
      ]),
      10_000,
    );

    expect(decision.active).toBe(1);
    expect(decision.changed).toBe(false);
  });

  it('a long pause does not make the next speaker wait for the hold', () => {
    const gate = new EnergyGate();
    gate.decide(new Map([[0, 0.3]]), 0);
    gate.decide(new Map([[0, 0.001]]), 30_000);

    const decision = gate.decide(
      new Map([
        [0, 0.001],
        [1, 0.4],
      ]),
      30_100,
    );

    expect(decision.active).toBe(1);
  });
});

describe('rmsOf', () => {
  it('reads a flat 128 buffer as silence', () => {
    expect(rmsOf(new Uint8Array(64).fill(128))).toBe(0);
  });

  it('reads full deflection as close to one', () => {
    expect(rmsOf(new Uint8Array(64).fill(255))).toBeCloseTo(0.992, 2);
  });

  it('is zero for an empty buffer rather than NaN', () => {
    // A NaN would compare false against the threshold and silently wedge the
    // gate shut for that channel.
    expect(rmsOf(new Uint8Array(0))).toBe(0);
  });

  it('rises with amplitude', () => {
    const quiet = rmsOf(new Uint8Array(64).fill(132));
    const loud = rmsOf(new Uint8Array(64).fill(200));

    expect(loud).toBeGreaterThan(quiet);
  });
});
