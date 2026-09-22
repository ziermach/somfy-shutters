import { describe, expect, it } from 'vitest';
import { pauseText, tomorrowMidnight, actionText, daysText, groupMembersText, lastText, nextText, outcomeText, targetsText, triggerText, viaText, WEEKDAYS } from './automations';

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
    expect(targetsText({ shutters: ['a', 'gone'], groups: [] }, { a: 'Küche' })).toBe('Küche');
    expect(targetsText({ shutters: ['gone'], groups: [] }, {})).toBe('kein Rolladen mehr');
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
    expect(outcomeText({ shutter_id: 'x', result: 'skipped', reason: 'forgotten' })).toBe(
      'übersprungen — Funkbrücke kennt ihn nicht mehr'
    );
  });
});

describe('pausing', () => {
  it('says until when, or that it waits for someone', () => {
    expect(pauseText('2026-09-23T00:00:00+02:00', NOW)).toBe('Automationen pausiert bis morgen 00:00');
    expect(pauseText(null, NOW)).toBe('Automationen pausiert');
  });

  it('offers tomorrow at midnight in local time', () => {
    expect(tomorrowMidnight(new Date(2026, 8, 30, 15, 0))).toBe('2026-10-01T00:00');
  });
});

describe('groups as targets (feature 004)', () => {
  const names = { bad: 'Bad', kind: 'Kind', buero: 'Büro' };
  const groups = [
    { id: 'g_og', name: 'Obergeschoss', members: ['bad', 'kind'] },
    { id: 'g_leer', name: 'Keller', members: [] }
  ];

  it('names groups first, then shutters', () => {
    expect(targetsText({ shutters: ['buero'], groups: ['g_og'] }, names, groups)).toBe('Obergeschoss, Büro');
  });

  it('a deleted group leaves nothing to name', () => {
    expect(targetsText({ shutters: [], groups: ['g_gone'] }, names, groups)).toBe('kein Rolladen mehr');
  });

  it('says what each group currently means', () => {
    expect(groupMembersText({ shutters: ['buero'], groups: ['g_og', 'g_leer'] }, names, groups)).toEqual([
      'Obergeschoss: Bad, Kind',
      'Keller: leer'
    ]);
    expect(groupMembersText('all', names, groups)).toEqual([]);
  });

  it('says through which group a shutter was reached', () => {
    expect(outcomeText({ shutter_id: 'bad', result: 'skipped', reason: 'measurement_in_progress', via: ['Obergeschoss'] })).toBe(
      'übersprungen — Messung läuft (über Obergeschoss)'
    );
    expect(outcomeText({ shutter_id: 'bad', result: 'commanded', reason: null })).toBe('gefahren');
    expect(
      viaText([
        { shutter_id: 'a', result: 'commanded', reason: null, via: ['EG', 'Süd'] },
        { shutter_id: 'b', result: 'commanded', reason: null, via: ['EG'] },
        { shutter_id: 'c', result: 'commanded', reason: null, via: [] }
      ])
    ).toBe('über EG, Süd');
    expect(viaText([{ shutter_id: 'c', result: 'commanded', reason: null }])).toBeNull();
  });
});
