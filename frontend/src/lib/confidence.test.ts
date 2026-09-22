// T036, the interface half of quickstart C4.1.
//
// The backend test proves the server never claims certainty for a calibrated
// shutter mid-travel. This proves the wording in front of the user does not
// either — and, structurally, that no screen renders a percentage without the
// badge beside it.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ageText, confidenceLabel, percentText, tone } from './confidence';
import type { PositionEstimate } from './types';

const position = (over: Partial<PositionEstimate> = {}): PositionEstimate => ({
  percent: 50,
  confidence: 'estimated',
  certain_at: '2026-09-22T06:00:00Z',
  age_seconds: 7200,
  stale: false,
  source: 'command',
  ...over
});

describe('what a position is called', () => {
  it('calls an end stop certain', () => {
    const at = position({ percent: 100, confidence: 'certain', age_seconds: 0 });
    expect(confidenceLabel(at)).toBe('Endlage · sicher');
    expect(tone(at)).toBe('sure');
  });

  it('calls everything between the end stops an estimate, with its age', () => {
    const between = position();
    expect(confidenceLabel(between)).toContain('Schätzung');
    expect(confidenceLabel(between)).toContain('2 Std.');
    expect(tone(between)).toBe('estimated');
  });

  it('never calls an estimate certain, whatever its age', () => {
    for (const seconds of [0, 1, 60, 3600, 86400, 999999]) {
      const label = confidenceLabel(position({ age_seconds: seconds }));
      expect(label).not.toContain('sicher');
      expect(label).toContain('Schätzung');
    }
  });

  it('says outright when the position is unknown', () => {
    const lost = position({ percent: null, confidence: 'unknown', certain_at: null, age_seconds: null });
    expect(confidenceLabel(lost)).toBe('Position unbekannt');
    expect(tone(lost)).toBe('unsure');
  });

  it('de-emphasises a stale estimate without upgrading its wording', () => {
    const old = position({ stale: true, age_seconds: 86400 * 3 });
    expect(tone(old)).toBe('unsure');
    expect(confidenceLabel(old)).toContain('Schätzung');
  });
});

describe('the number itself', () => {
  it('shows a question mark rather than a figure for an unknown position', () => {
    expect(percentText(null)).toBe('?');
  });

  it('shows the percentage otherwise', () => {
    expect(percentText(62)).toBe('62 %');
    expect(percentText(0)).toBe('0 %');
  });
});

describe('age wording', () => {
  it.each([
    [0, '0 Min.'],
    [3540, '59 Min.'],
    [7200, '2 Std.'],
    [86400 * 3, '3 Tagen']
  ])('renders %i seconds as %s', (seconds, expected) => {
    expect(ageText(seconds)).toBe(expected);
  });

  it('says never when a position has never been certain', () => {
    expect(ageText(null)).toBe('nie');
  });
});

describe('no bare numbers on any screen', () => {
  // Constitution III, enforced structurally: if a component renders a
  // percentage it has to render the confidence beside it. A regression here
  // would be a screen that looks like it knows something it does not.
  const roots = ['src/components', 'src/routes'];

  const files = roots.flatMap((dir) =>
    readdirSync(dir)
      .filter((name) => name.endsWith('.svelte'))
      .map((name) => ({ path: join(dir, name), source: readFileSync(join(dir, name), 'utf8') }))
  );

  const showsPercent = files.filter(
    (f) => f.source.includes('percentText(') || f.source.includes('livePercent(')
  );

  it('finds the screens that show a position at all', () => {
    expect(showsPercent.map((f) => f.path).sort()).toEqual([
      'src/components/ShutterCard.svelte',
      'src/routes/CalibrationRun.svelte',
      'src/routes/Detail.svelte'
    ]);
  });

  it.each(['src/components/ShutterCard.svelte', 'src/routes/Detail.svelte'])(
    '%s puts the confidence beside the number',
    (path) => {
      const source = files.find((f) => f.path === path)!.source;
      expect(source).toContain('ConfidenceBadge');
    }
  );

  it('the calibration screen shows the graphic but never a bare percentage', () => {
    const source = files.find((f) => f.path === 'src/routes/CalibrationRun.svelte')!.source;
    expect(source).not.toContain('percentText(');
    expect(source).toContain('Kalibriert heißt nicht bekannt');
  });
});
