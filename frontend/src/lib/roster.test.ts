import { describe, expect, it } from 'vitest';
import {
  NO_ANNOUNCEMENTS_HINT,
  POWER_WARNING,
  STALE_HINT,
  TIMEOUT_HINTS,
  TIMEOUT_MS,
  steps,
  uniqueName
} from './roster';

describe('the guide (US2)', () => {
  const remote = steps('remote');

  it('says what, where and how to tell it worked, for every step', () => {
    for (const step of remote) {
      expect(step.title.length).toBeGreaterThan(0);
      expect(step.text.length).toBeGreaterThan(0);
      expect(step.success.length).toBeGreaterThan(0);
      expect(['App', 'Funkbrücke', 'Fernbedienung', 'Fenster', 'Sicherung']).toContain(step.where);
    }
    expect(remote.find((s) => s.id === 'learn')?.success).toBe('Der Rolladen wackelt kurz.');
  });

  it('uses Pi-Somfy\'s own labels', () => {
    const text = remote.map((s) => s.text).join(' ');
    expect(text).toContain('„Add shutter“');
    expect(text).toContain('„Program“');
    expect(text).toContain('PROG');
  });

  it('restarts the bridge after programming, because only then it announces the shutter', () => {
    const ids = remote.map((s) => s.id);
    expect(ids).toEqual(['create', 'learn', 'program', 'restart', 'wait']);
    expect(ids.indexOf('restart')).toBeGreaterThan(ids.indexOf('program'));
  });

  it('gives up waiting after ten minutes with the usual causes, restart first', () => {
    expect(TIMEOUT_MS).toBe(600_000);
    expect(TIMEOUT_HINTS).toHaveLength(4);
    expect(TIMEOUT_HINTS[0]).toMatch(/neu gestartet/);
    expect(TIMEOUT_HINTS[1]).toMatch(/PROG/);
    expect(TIMEOUT_HINTS[2]).toMatch(/Anlernmodus ist abgelaufen/);
    expect(TIMEOUT_HINTS[3]).toMatch(/EnableDiscovery/);
  });

  it('explains a bridge that never announced anything, and stale announcements', () => {
    expect(NO_ANNOUNCEMENTS_HINT).toMatch(/EnableDiscovery/);
    expect(STALE_HINT).toMatch(/beiseite/);
  });
});

describe('without a working remote (US5)', () => {
  const power = steps('power');

  it('replaces only the PROG step with the power cycle', () => {
    expect(power.map((s) => s.id)).toEqual(['create', 'power', 'program', 'restart', 'wait']);
    expect(power.map((s) => s.text).join(' ')).not.toContain('PROG');
  });

  it('gives the timing', () => {
    const cycle = power.find((s) => s.id === 'power')!;
    expect(cycle.text).toMatch(/mindestens 5 Sekunden/);
    expect(cycle.text).toMatch(/wieder ein/);
    expect(cycle.text).toMatch(/zwei Minuten/);
  });

  it('warns that every motor on the circuit learns the same sender', () => {
    expect(POWER_WARNING).toMatch(/Alle Motoren am selben Stromkreis/);
    expect(POWER_WARNING).toMatch(/denselben Sender/);
  });
});

describe('uniqueName', () => {
  it('keeps a free name', () => {
    expect(uniqueName('Bad', ['Küche'])).toBe('Bad');
  });
  it('numbers a taken one, ignoring case', () => {
    expect(uniqueName('Küche', ['küche'])).toBe('Küche 2');
    expect(uniqueName('Küche', ['Küche', 'Küche 2'])).toBe('Küche 3');
  });
  it('trims and never returns an empty name', () => {
    expect(uniqueName('  Bad ', [])).toBe('Bad');
    expect(uniqueName('   ', [])).toBe('Rolladen');
  });
});
