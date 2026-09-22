// Feature 004: what a group looks like on the overview. Kept pure so it can be
// tested — a group summary is where the project's promise of honest positions
// could quietly break, by averaging or by sounding surer than its members.

import { tone, type Tone } from './confidence';
import type { CommandResult, Group, Shutter } from './types';

// --- summary (research §9) -----------------------------------------------------

type Bucket = 'open' | 'closed' | 'between' | 'moving' | 'unknown';

/** The fixed order counts are read in (FR-012). */
const ORDER: Bucket[] = ['open', 'closed', 'between', 'moving', 'unknown'];

/** The word when every member agrees. */
const ALL: Record<Bucket, string> = {
  open: 'offen',
  closed: 'zu',
  between: 'dazwischen',
  moving: 'fährt',
  unknown: 'Position unbekannt'
};

function word(bucket: Bucket, count: number): string {
  if (bucket === 'moving') return count === 1 ? 'fährt' : 'fahren';
  if (bucket === 'unknown') return 'unbekannt';
  return ALL[bucket];
}

function bucketOf(shutter: Shutter): Bucket {
  if (shutter.movement) return 'moving';
  const percent = shutter.position.percent;
  if (percent === null) return 'unknown';
  if (percent === 100) return 'open';
  if (percent === 0) return 'closed';
  return 'between';
}

const RANK: Record<Tone, number> = { sure: 0, estimated: 1, unsure: 2 };

/** As the card's badge says it: an end stop being left is no longer certain. */
function memberTone(shutter: Shutter): Tone {
  const own = tone(shutter.position);
  return shutter.movement && own === 'sure' ? 'estimated' : own;
}

export interface Summary {
  text: string;
  /** The least confident member's tone: a summary is never surer than that. */
  tone: Tone;
}

/** Counts, never a percent: an average of 0 and 100 is 50, which no window is (FR-013). */
export function summarize(members: Shutter[]): Summary {
  if (members.length === 0) return { text: 'leer', tone: 'unsure' };

  const counts = new Map<Bucket, number>();
  for (const member of members) {
    const bucket = bucketOf(member);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  const worst = members.map(memberTone).reduce((a, b) => (RANK[b] > RANK[a] ? b : a));

  const present = ORDER.filter((b) => counts.has(b));
  if (present.length === 1) return { text: ALL[present[0]], tone: worst };

  const parts = present.map((bucket, i) => {
    const n = counts.get(bucket)!;
    return i === 0 ? `${n} von ${members.length} ${word(bucket, n)}` : `${n} ${word(bucket, n)}`;
  });
  return { text: parts.join(' · '), tone: worst };
}

// --- what a group command did -----------------------------------------------------

const REASON: Record<string, string> = {
  measurement_in_progress: 'Messung läuft',
  bridge_unreachable: 'Funkbrücke antwortet nicht'
};

/** null when every member took the command; otherwise who did not, and why (FR-018). */
export function commandText(results: CommandResult[], nameOf: (id: string) => string): string | null {
  const refused = results.filter((r) => !r.accepted);
  if (refused.length === 0) return null;
  if (refused.length === results.length) return 'Kein Rolladen konnte erreicht werden.';
  return refused.map((r) => `${nameOf(r.id)}: ${REASON[r.error ?? ''] ?? 'nicht erreicht'}`).join(' · ');
}

// --- sections of the overview ------------------------------------------------------

export interface Section {
  group: Group;
  /** The store's own shutter objects, so a shutter shown twice animates identically. */
  members: Shutter[];
}

export function sections(groups: Group[], shutters: Shutter[]): { grouped: Section[]; ungrouped: Shutter[] } {
  const byId = new Map(shutters.map((s) => [s.id, s]));
  const grouped = groups.map((group) => ({
    group,
    members: group.members.map((id) => byId.get(id)).filter((s): s is Shutter => s !== undefined)
  }));
  const inSome = new Set(groups.flatMap((g) => g.members));
  return { grouped, ungrouped: shutters.filter((s) => !inSome.has(s.id)) };
}

// --- view preference, per device (research §10) ------------------------------------

const KEY = 'somfy.view';

export interface View {
  /** null: nobody chose yet — grouped when any group exists. */
  mode: 'grouped' | 'flat' | null;
  collapsed: string[];
}

type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>;

function local(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null; // some browsers throw on mere access in a private window
  }
}

/** Never throws: without storage the defaults apply and the page still works. */
export function loadView(storage: Storage | null = local()): View {
  const fallback: View = { mode: null, collapsed: [] };
  try {
    const raw = storage?.getItem(KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    const mode = parsed?.mode === 'grouped' || parsed?.mode === 'flat' ? parsed.mode : null;
    const collapsed = Array.isArray(parsed?.collapsed) ? parsed.collapsed.filter((x: unknown) => typeof x === 'string') : [];
    return { mode, collapsed };
  } catch {
    return fallback;
  }
}

export function saveView(view: View, storage: Storage | null = local()): void {
  try {
    storage?.setItem(KEY, JSON.stringify(view));
  } catch {
    // A convenience, not state: losing it costs one tap next time.
  }
}
