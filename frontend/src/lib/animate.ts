// The animation runs here, on the client's own clock, from the timestamps the
// server sent once. It never waits for a frame from the bridge — that is the
// whole point of FR-012, and why a travelling shutter needs no network traffic.

import type { Movement } from './types';

// The motor runs linearly in time — the bridge's "level" — and the window does
// not respond linearly to it. Same transform as the server's calibration.to_level,
// so a stop mid-travel settles where the animation already is.
const clamp = (v: number) => Math.min(100, Math.max(0, v));
export const toLevel = (percent: number, a: number) => 100 * (clamp(percent) / 100) ** (1 / a);
export const toPercent = (level: number, a: number) => 100 * (clamp(level) / 100) ** a;

export function interpolate(movement: Movement, now: number = Date.now()): number {
  const start = Date.parse(movement.started_at);
  const end = Date.parse(movement.expected_arrival);
  if (!(end > start)) return movement.target_percent;
  const progress = Math.min(1, Math.max(0, (now - start) / (end - start)));
  const a = movement.curve_a ?? 1;
  if (a === 1) {
    const span = movement.target_percent - movement.from_percent;
    return Math.round(movement.from_percent + span * progress);
  }
  const from = toLevel(movement.from_percent, a);
  const to = toLevel(movement.target_percent, a);
  return Math.round(toPercent(from + (to - from) * progress, a));
}

export function hasArrived(movement: Movement, now: number = Date.now()): boolean {
  return now >= Date.parse(movement.expected_arrival);
}

/** Drives a callback every animation frame while something is moving. */
export function ticker(onFrame: () => void): () => void {
  let handle = 0;
  const loop = () => {
    onFrame();
    handle = requestAnimationFrame(loop);
  };
  handle = requestAnimationFrame(loop);
  return () => cancelAnimationFrame(handle);
}
