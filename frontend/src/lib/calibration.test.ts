// T037, the interface half: the app has to say when a hand-written value is
// overriding a measurement. Silence there looks like the app ignoring what you
// just measured.

import { describe, expect, it } from 'vitest';
import { overriddenDirections, overrideNotice, stateLabel, timesLabel } from './calibration.svelte';
import type { CalibrationShutter, DirectionValue } from './calibration.svelte';

const value = (over: Partial<DirectionValue> = {}): DirectionValue => ({
  travel_seconds: 12,
  dead_seconds: 0.6,
  runs: 0,
  curve_a: 1,
  source: 'default',
  updated_at: null,
  ...over
});

const shutter = (up: DirectionValue, down: DirectionValue): CalibrationShutter => ({
  id: 'flink',
  name: 'Flink',
  state: 'calibrated',
  up,
  down
});

describe('override notice', () => {
  it('says nothing when nothing is overridden', () => {
    const s = shutter(value({ source: 'measured', runs: 3 }), value({ source: 'measured', runs: 3 }));
    expect(overrideNotice(s)).toBeNull();
    expect(overriddenDirections(s)).toEqual([]);
  });

  it('names the one direction that is overridden', () => {
    const s = shutter(value({ source: 'manual', travel_seconds: 25 }), value({ source: 'measured' }));
    expect(overriddenDirections(s)).toEqual(['auf']);
    expect(overrideNotice(s)).toContain('die Richtung „auf"');
    expect(overrideNotice(s)).toContain('shutters.toml');
  });

  it('says both when both are overridden', () => {
    const s = shutter(value({ source: 'manual' }), value({ source: 'manual' }));
    expect(overriddenDirections(s)).toEqual(['auf', 'zu']);
    expect(overrideNotice(s)).toContain('beide Richtungen');
  });

  it('promises the measurements are kept, and counts them', () => {
    const s = shutter(value({ source: 'manual', runs: 3 }), value({ source: 'measured', runs: 2 }));
    expect(overrideNotice(s)).toContain('5 gemessenen Läufe');
    expect(overrideNotice(s)).toContain('bleiben gespeichert');
  });

  it('does not promise kept measurements when there are none', () => {
    const s = shutter(value({ source: 'manual' }), value({ source: 'default' }));
    expect(overrideNotice(s)).not.toContain('bleiben gespeichert');
  });
});

describe('list labels', () => {
  it('marks an uncalibrated shutter as such', () => {
    expect(stateLabel({ ...shutter(value(), value()), state: 'uncalibrated' })).toBe(
      'nicht kalibriert'
    );
  });

  it('shows a dash for a direction that was never measured', () => {
    const s = shutter(value({ source: 'measured', travel_seconds: 12.4 }), value());
    expect(timesLabel(s)).toBe('12.4 s auf · — zu');
  });
});
