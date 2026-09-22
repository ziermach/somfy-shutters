import { describe, expect, it } from 'vitest';
import { actionText, daysText, lastText, nextText, outcomeText, targetsText, triggerText, WEEKDAYS } from './automations';

// 2026-09-22 10:00 in Berlin (UTC+2)
const NOW = new Date('2026-09-22T08:00:00Z');

describe('when a rule fires next', () => {
  it('says today, tomorrow, or the weekday and date', () => {
    expect(nextText({ at: '2026-09-22T17:12:00+02:00', reason: null }, NOW)).toBe('heute 17:12');
    expect(nextText({ at: '2026-09-23T06:45:00+02:00', reason: null }, NOW)).toBe('morgen 06:45');
    expect(nextText({ at: '2026-09-28T06:45:00+02:00', reason: null }, NOW)).toBe('Mo 28.09. 06:45');
  });

  it('reads the server wall clock, not the browser timezone', () => {
    // 23:30 local in Berlin is already the next day in UTC.
    expect(nextText({ at: '2026-09-22T23:30:00+02:00', reason: null }, NOW)).toBe('heute 23:30');
  });

  it('says why a rule will not fire', () => {
    expect(nextText({ at: null, reason: 'disabled' }, NOW)).toBe('ausgeschaltet');
    expect(nextText({ at: null, reason: 'no_location' }, NOW)).toBe('kein Standort gesetzt');
    expect(nextText({ at: null, reason: 'no_targets' }, NOW)).toBe('kein Rolladen mehr');
  });
});

describe('what a rule does', () => {
  it('names triggers, including offsets and bounds', () => {
    expect(triggerText({ kind: 'time', time: '06:45' })).toBe('06:45');
    expect(triggerText({ kind: 'sunset', offset_minutes: -30, not_before: null, not_after: '21:00' })).toBe(
      'Sonnenuntergang −30 Min (nicht nach 21:00)'
    );
    expect(triggerText({ kind: 'sunrise', offset_minutes: 0, not_before: null, not_after: null })).toBe('Sonnenaufgang');
  });

  it('names actions, days and targets', () => {
    expect(actionText({ kind: 'position', percent: 30 })).toBe('30 %');
    expect(actionText({ kind: 'close' })).toBe('zu');
    expect(daysText(WEEKDAYS)).toBe('werktags');
    expect(daysText([true, false, true, false, true, false, false])).toBe('Mo Mi Fr');
    expect(targetsText('all', {})).toBe('Alle Rolladen');
    expect(targetsText(['a', 'gone'], { a: 'Küche' })).toBe('Küche');
    expect(targetsText(['gone'], {})).toBe('kein Rolladen mehr');
  });
});

describe('what happened', () => {
  it('summarises the last firing with how many shutters were reached', () => {
    expect(lastText({ planned_at: '2026-09-22T06:45:00+02:00', status: 'partial', commanded: 3, total: 4 })).toContain(
      'teilweise ausgeführt · 3 von 4'
    );
  });

  it('gives a reason for every shutter that did not move', () => {
    expect(outcomeText({ shutter_id: 'x', result: 'skipped', reason: 'measurement_in_progress' })).toBe(
      'übersprungen — Messung läuft'
    );
    expect(outcomeText({ shutter_id: 'x', result: 'failed', reason: 'bridge_unreachable' })).toContain('Funkbrücke');
  });
});
