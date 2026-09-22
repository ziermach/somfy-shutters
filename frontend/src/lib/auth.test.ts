import { describe, expect, it } from 'vitest';
import { abilitiesText, actorText, formatCode, normaliseCode, outcomeWord, whatText, type RecordEntry } from './auth';

describe('pairing codes as people type them', () => {
  it('reads upper, lower, dashes and spaces the same', () => {
    for (const typed of ['k7q-9xm', ' K7Q9XM ', 'k7q 9xm', 'K7Q-9XM']) expect(normaliseCode(typed)).toBe('K7Q9XM');
  });

  it('refuses what cannot be a code', () => {
    for (const typed of ['K7Q9X', 'K7Q9XMM', 'K7Q9XI', 'K7Q9XO', '']) expect(normaliseCode(typed)).toBeNull();
  });

  it('shows the dash while typing, and stops at six characters', () => {
    expect(formatCode('k7')).toBe('K7');
    expect(formatCode('k7q9')).toBe('K7Q-9');
    expect(formatCode('k7q9xmzz')).toBe('K7Q-9XM');
  });
});

describe('what a device may do, in words', () => {
  it('lists abilities in a fixed order', () => {
    expect(abilitiesText(['command', 'watch'])).toBe('darf zusehen, fahren');
    expect(abilitiesText(['manage', 'watch', 'calibrate', 'configure', 'command'])).toBe(
      'darf zusehen, fahren, einstellen, kalibrieren, Geräte verwalten'
    );
  });
});

describe('the record, in words', () => {
  const entry = (over: Partial<RecordEntry>): RecordEntry => ({
    id: 1,
    at: '2026-09-23T11:02:14+02:00',
    clock_ok: true,
    actor: { kind: 'credential', id: 'c_1', name: 'Küche', state: 'active' },
    action: 'command',
    shutter_id: 'wohnzimmer',
    target: null,
    outcome: 'accepted',
    detail: { action: 'close' },
    ...over
  });
  const nameOf = (id: string) => ({ wohnzimmer: 'Wohnzimmer' })[id] ?? id;

  it('says who, keeping the name a revoked device had', () => {
    expect(actorText(entry({}).actor)).toBe('Küche');
    expect(actorText({ kind: 'credential', id: 'c_2', name: 'Anna', state: 'revoked' })).toBe('Anna (widerrufen)');
    expect(actorText({ kind: 'automation', id: 'r_1', name: 'Abends zu' })).toBe('Regel „Abends zu“');
    expect(actorText({ kind: 'bridge', id: null, name: 'Funkbrücke' })).toBe('bemerkt, nicht von der App');
  });

  it('says what was asked', () => {
    expect(whatText(entry({}), nameOf)).toBe('Wohnzimmer zu');
    expect(whatText(entry({ detail: { action: 'position', percent: 30 } }), nameOf)).toBe('Wohnzimmer auf 30 %');
    expect(whatText(entry({ action: 'movement_observed', detail: { percent: 70 } }), nameOf)).toBe('Wohnzimmer auf 70 %');
    expect(whatText(entry({ action: 'group_changed', shutter_id: null }), nameOf)).toBe('Gruppe geändert');
  });

  it('says what came of it', () => {
    expect(outcomeWord('accepted')).toBe('ausgeführt');
    expect(outcomeWord('refused_permission')).toBe('abgelehnt — keine Berechtigung');
  });
});
