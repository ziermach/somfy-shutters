// How a position is described to a person.
//
// Kept out of the component so it can be tested: this is where the project's
// central promise either holds or quietly breaks. A calibrated shutter's
// position between end stops is still an estimate, and the wording has to keep
// saying so no matter how many runs the travel time rests on.

import type { PositionEstimate } from './types';

export type Tone = 'sure' | 'estimated' | 'unsure';

export function tone(position: PositionEstimate): Tone {
  if (position.confidence === 'certain') return 'sure';
  if (position.confidence === 'unknown' || position.stale) return 'unsure';
  return 'estimated';
}

export function ageText(seconds: number | null): string {
  if (seconds === null) return 'nie';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} Min.`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} Std.`;
  return `${Math.round(hours / 24)} Tagen`;
}

export function confidenceLabel(position: PositionEstimate): string {
  if (position.confidence === 'certain') return 'Endlage · sicher';
  if (position.confidence === 'unknown') return 'Position unbekannt';
  return `Schätzung · Sync vor ${ageText(position.age_seconds)}`;
}

/** What the big number shows. Never a bare figure for an unknown position. */
export function percentText(percent: number | null): string {
  return percent === null ? '?' : `${percent} %`;
}
