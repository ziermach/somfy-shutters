import { describe, expect, it } from 'vitest';
import { interpolate, toLevel, toPercent } from './animate';
import type { Movement } from './types';

const movement = (curve_a: number): Movement => ({
  from_percent: 0,
  target_percent: 100,
  direction: 'up',
  started_at: '2026-09-22T10:00:00.000Z',
  expected_arrival: '2026-09-22T10:00:10.000Z',
  origin: 'local',
  curve_a
});
const at = (s: number) => Date.parse('2026-09-22T10:00:00.000Z') + s * 1000;

describe('interpolate', () => {
  it('is a straight line when the curve is neutral', () => {
    expect(interpolate(movement(1), at(5))).toBe(50);
  });

  it('follows the curve mid-travel, like the server does', () => {
    // Server: to_percent(50, 1.3) = 40.6 — a stop here must not jump.
    expect(interpolate(movement(1.3), at(5))).toBe(41);
  });

  it('leaves the end points exact', () => {
    expect(interpolate(movement(1.3), at(0))).toBe(0);
    expect(interpolate(movement(1.3), at(10))).toBe(100);
  });

  it('level and percent are inverse', () => {
    for (const p of [0, 12, 50, 87, 100]) expect(toPercent(toLevel(p, 0.8), 0.8)).toBeCloseTo(p);
  });
});
