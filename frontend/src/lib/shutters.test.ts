import { describe, expect, it } from 'vitest';
import { shutters } from './shutters.svelte';
import type { Movement, Shutter } from './types';

const position = (percent: number | null) => ({
  percent,
  confidence: percent === null ? 'unknown' : 'certain',
  certain_at: null,
  age_seconds: null,
  stale: false,
  source: 'command'
}) as Shutter['position'];

const shutter = (percent: number | null, movement: Movement | null = null): Shutter => ({
  id: 'x',
  name: 'X',
  calibrated: true,
  travel_up_seconds: 10,
  travel_down_seconds: 10,
  position: position(percent),
  movement,
  measuring: false
});

const opening: Movement = {
  from_percent: 0,
  target_percent: 100,
  direction: 'up',
  started_at: '2026-09-22T10:00:00.000Z',
  expected_arrival: '2026-09-22T10:00:10.000Z',
  origin: 'local',
  curve_a: 1
};

describe('which buttons make sense', () => {
  it('an open shutter cannot be opened, a closed one cannot be closed', () => {
    expect(shutters.canOpen(shutter(100))).toBe(false);
    expect(shutters.canClose(shutter(100))).toBe(true);
    expect(shutters.canOpen(shutter(0))).toBe(true);
    expect(shutters.canClose(shutter(0))).toBe(false);
  });

  it('a shutter already opening cannot be opened again', () => {
    expect(shutters.canOpen(shutter(0, opening))).toBe(false);
    expect(shutters.canClose(shutter(0, opening))).toBe(true);
  });

  it('stop is on offer only while a travel is under way', () => {
    expect(shutters.canStop(shutter(40))).toBe(false);
    expect(shutters.canStop(shutter(0, opening))).toBe(true);
  });

  it('an unknown position leaves both on offer — that is how it becomes known', () => {
    expect(shutters.canOpen(shutter(null))).toBe(true);
    expect(shutters.canClose(shutter(null))).toBe(true);
  });
});

describe('the animation clock', () => {
  it('livePercent follows the store clock, not a Date.now() nobody tracks', () => {
    shutters.now = Date.parse('2026-09-22T10:00:05.000Z');
    expect(shutters.livePercent(shutter(0, opening))).toBe(50);
    shutters.now = Date.parse('2026-09-22T10:00:08.000Z');
    expect(shutters.livePercent(shutter(0, opening))).toBe(80);
  });
});
