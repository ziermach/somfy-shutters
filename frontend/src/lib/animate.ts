// The animation runs here, on the client's own clock, from the timestamps the
// server sent once. It never waits for a frame from the bridge — that is the
// whole point of FR-012, and why a travelling shutter needs no network traffic.

import type { Movement } from './types';

export function interpolate(movement: Movement, now: number = Date.now()): number {
  const start = Date.parse(movement.started_at);
  const end = Date.parse(movement.expected_arrival);
  if (!(end > start)) return movement.target_percent;
  const progress = Math.min(1, Math.max(0, (now - start) / (end - start)));
  const span = movement.target_percent - movement.from_percent;
  return Math.round(movement.from_percent + span * progress);
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
