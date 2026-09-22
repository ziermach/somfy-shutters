import { describe, expect, it } from 'vitest';
import { commandText, loadView, saveView, sections, summarize } from './groups';
import type { Group, Movement, Shutter } from './types';

type Conf = Shutter['position']['confidence'];

const make = (id: string, percent: number | null, opts: { confidence?: Conf; stale?: boolean; moving?: boolean } = {}): Shutter => ({
  id,
  name: id,
  calibrated: true,
  travel_up_seconds: 10,
  travel_down_seconds: 10,
  position: {
    percent,
    confidence: opts.confidence ?? (percent === null ? 'unknown' : percent === 0 || percent === 100 ? 'certain' : 'estimated'),
    certain_at: null,
    age_seconds: null,
    stale: opts.stale ?? false,
    source: 'command'
  },
  movement: opts.moving ? (moving as Movement) : null,
  measuring: false,
  origin: 'config',
  forgotten: false
});

const moving: Movement = {
  from_percent: 0,
  target_percent: 100,
  direction: 'up',
  started_at: '2026-09-22T10:00:00.000Z',
  expected_arrival: '2026-09-22T10:00:10.000Z',
  origin: 'local',
  curve_a: 1
};

describe('the group summary', () => {
  it('says one word when every member agrees', () => {
    expect(summarize([make('a', 100), make('b', 100)]).text).toBe('offen');
    expect(summarize([make('a', 0), make('b', 0)]).text).toBe('zu');
    expect(summarize([make('a', 0, { moving: true }), make('b', 100, { moving: true })]).text).toBe('fährt');
    expect(summarize([make('a', null), make('b', null)]).text).toBe('Position unbekannt');
  });

  it('counts in the fixed order offen, zu, dazwischen, fährt, unbekannt', () => {
    const members = [make('a', null), make('b', 30), make('c', 0, { moving: true }), make('d', 0), make('e', 100)];
    expect(summarize(members).text).toBe('1 von 5 offen · 1 zu · 1 dazwischen · 1 fährt · 1 unbekannt');
  });

  it('leaves empty buckets out', () => {
    expect(summarize([make('a', 100), make('b', 0)]).text).toBe('1 von 2 offen · 1 zu');
    expect(summarize([make('a', 0), make('b', 0, { moving: true }), make('c', 0, { moving: true })]).text).toBe(
      '1 von 3 zu · 2 fahren'
    );
  });

  it('never shows a percent — an average of 0 and 100 is no window', () => {
    const members = [make('a', 0), make('b', 100), make('c', 30), make('d', 70)];
    expect(summarize(members).text).not.toMatch(/%|\d+ ?%/);
    expect(summarize(members).text).not.toMatch(/50/);
  });

  it('is never more confident than its least confident member', () => {
    expect(summarize([make('a', 100), make('b', 0)]).tone).toBe('sure');
    expect(summarize([make('a', 100), make('b', 40)]).tone).toBe('estimated');
    expect(summarize([make('a', 100), make('b', 40, { stale: true })]).tone).toBe('unsure');
    expect(summarize([make('a', 100), make('b', null)]).tone).toBe('unsure');
  });

  it('a member leaving an end stop is no longer certain, as on its card', () => {
    expect(summarize([make('a', 100, { moving: true })]).tone).toBe('estimated');
  });

  it('an empty group says so', () => {
    expect(summarize([])).toEqual({ text: 'leer', tone: 'unsure' });
  });
});

describe('sections of the overview', () => {
  const house = [make('wohnzimmer', 0), make('kueche', 0), make('schlafzimmer', 0), make('buero', 0)];
  const groups: Group[] = [
    { id: 'g1', name: 'Südseite', members: ['schlafzimmer', 'wohnzimmer'] },
    { id: 'g2', name: 'Erdgeschoss', members: ['wohnzimmer', 'kueche'] },
    { id: 'g3', name: 'Leer', members: [] }
  ];

  it('keeps group order and member order, and shows a shared shutter in both', () => {
    const { grouped } = sections(groups, house);
    expect(grouped.map((s) => s.group.name)).toEqual(['Südseite', 'Erdgeschoss', 'Leer']);
    expect(grouped[0].members.map((m) => m.id)).toEqual(['schlafzimmer', 'wohnzimmer']);
    expect(grouped[1].members.map((m) => m.id)).toEqual(['wohnzimmer', 'kueche']);
  });

  it('lists shutters in no group last, in configuration order', () => {
    expect(sections(groups, house).ungrouped.map((s) => s.id)).toEqual(['buero']);
  });

  it('keeps an empty group, with no members', () => {
    expect(sections(groups, house).grouped[2].members).toEqual([]);
  });

  it('hands out the same shutter object in every place, so it animates identically', () => {
    const { grouped } = sections(groups, house);
    expect(grouped[0].members[1]).toBe(grouped[1].members[0]);
  });

  it('ignores a member it does not know', () => {
    const { grouped } = sections([{ id: 'g', name: 'G', members: ['keller', 'kueche'] }], house);
    expect(grouped[0].members.map((m) => m.id)).toEqual(['kueche']);
  });
});

describe('the view preference', () => {
  const memory = (initial: Record<string, string> = {}) => {
    const data = { ...initial };
    return {
      data,
      getItem: (k: string) => data[k] ?? null,
      setItem: (k: string, v: string) => {
        data[k] = v;
      }
    };
  };
  const broken = {
    getItem: () => {
      throw new Error('denied');
    },
    setItem: () => {
      throw new Error('denied');
    }
  };

  it('round-trips mode and collapsed groups', () => {
    const store = memory();
    saveView({ mode: 'flat', collapsed: ['g1'] }, store);
    expect(loadView(store)).toEqual({ mode: 'flat', collapsed: ['g1'] });
  });

  it('falls back to defaults when storage throws, and saving does not throw', () => {
    expect(loadView(broken)).toEqual({ mode: null, collapsed: [] });
    expect(() => saveView({ mode: 'grouped', collapsed: [] }, broken)).not.toThrow();
  });

  it('falls back to defaults on garbage', () => {
    expect(loadView(memory({ 'somfy.view': '{not json' }))).toEqual({ mode: null, collapsed: [] });
    expect(loadView(memory({ 'somfy.view': '{"mode":"sideways","collapsed":"x"}' }))).toEqual({
      mode: null,
      collapsed: []
    });
  });

  it('works with no storage at all', () => {
    expect(loadView(null)).toEqual({ mode: null, collapsed: [] });
  });
});

describe('what a group command did', () => {
  const nameOf = (id: string) => ({ kueche: 'Küche', bad: 'Bad' })[id] ?? id;

  it('says nothing when every member took it', () => {
    expect(commandText([{ id: 'kueche', accepted: true }], nameOf)).toBeNull();
  });

  it('names each member not reached, with the reason', () => {
    const text = commandText(
      [
        { id: 'wohnzimmer', accepted: true },
        { id: 'kueche', accepted: false, error: 'measurement_in_progress' },
        { id: 'bad', accepted: false, error: 'bridge_unreachable' }
      ],
      nameOf
    );
    expect(text).toBe('Küche: Messung läuft · Bad: Funkbrücke antwortet nicht');
  });

  it('says so plainly when none was reached', () => {
    expect(commandText([{ id: 'kueche', accepted: false, error: 'bridge_unreachable' }], nameOf)).toBe(
      'Kein Rolladen konnte erreicht werden.'
    );
  });
});
