// Feature 003: the words a person reads about a rule. Kept out of the components so
// they can be tested — "heute 06:45" versus "morgen" is exactly the kind of thing
// that is wrong for a day before anyone notices.

export type Trigger =
  | { kind: 'time'; time: string }
  | { kind: 'sunrise' | 'sunset'; offset_minutes: number; not_before: string | null; not_after: string | null };

export type RuleAction = { kind: 'open' | 'close'; percent?: null } | { kind: 'position'; percent: number };

export type FiringStatus = 'fired' | 'partial' | 'failed' | 'skipped' | 'paused' | 'held' | 'missed' | 'no_sun';

/** "all", or shutters and groups picked by hand (feature 004). Groups are resolved
 *  when the rule fires, so a shutter added to a group is included from then on. */
export type RuleTargets = 'all' | { shutters: string[]; groups: string[] };

export interface RuleDraft {
  name: string;
  enabled: boolean;
  days: boolean[];
  trigger: Trigger;
  targets: RuleTargets;
  action: RuleAction;
}

export interface Conflict {
  rule_id: string;
  rule_name: string;
  shutter_id: string;
  /** The group through which the rule being edited reaches that shutter, if any. */
  via?: string | null;
  first_at: string;
  winner: string;
}

export interface Rule extends RuleDraft {
  id: string;
  skip_next: boolean;
  next: { at: string | null; reason: string | null };
  last: { planned_at: string; status: FiringStatus; commanded: number; total: number } | null;
  created_at: string;
}

export interface Outcome {
  shutter_id: string;
  result: 'commanded' | 'skipped' | 'failed';
  reason: 'measurement_in_progress' | 'removed' | 'bridge_unreachable' | 'forgotten' | null;
  /** Names of the groups it was reached through, as they were then (feature 004). */
  via?: string[];
}

export interface Firing {
  planned_at: string;
  fired_at: string | null;
  status: FiringStatus;
  outcomes: Outcome[];
}

export interface AutomationState {
  paused: boolean;
  until: string | null;
  clock_reliable: boolean;
  clock_reason: string | null;
}

export interface HomeLocation {
  latitude: number;
  longitude: number;
  sunrise: string | null;
  sunset: string | null;
}

export const WEEKDAYS = [true, true, true, true, true, false, false];
export const WEEKEND = [false, false, false, false, false, true, true];
export const EVERY_DAY = [true, true, true, true, true, true, true];
export const DAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

const same = (a: boolean[], b: boolean[]) => a.every((v, i) => v === b[i]);

export function daysText(days: boolean[]): string {
  if (same(days, EVERY_DAY)) return 'täglich';
  if (same(days, WEEKDAYS)) return 'werktags';
  if (same(days, WEEKEND)) return 'am Wochenende';
  if (!days.some(Boolean)) return 'an keinem Tag';
  return DAY_LABELS.filter((_, i) => days[i]).join(' ');
}

function offsetText(minutes: number): string {
  if (!minutes) return '';
  return ` ${minutes < 0 ? '−' : '+'}${Math.abs(minutes)} Min`;
}

export function triggerText(trigger: Trigger): string {
  if (trigger.kind === 'time') return trigger.time;
  const base = trigger.kind === 'sunrise' ? 'Sonnenaufgang' : 'Sonnenuntergang';
  const bounds = [
    trigger.not_before ? `nicht vor ${trigger.not_before}` : null,
    trigger.not_after ? `nicht nach ${trigger.not_after}` : null
  ].filter(Boolean);
  return base + offsetText(trigger.offset_minutes) + (bounds.length ? ` (${bounds.join(', ')})` : '');
}

export function actionText(action: RuleAction): string {
  if (action.kind === 'open') return 'auf';
  if (action.kind === 'close') return 'zu';
  return `${action.percent} %`;
}

export function targetsText(
  targets: RuleTargets,
  names: Record<string, string>,
  groups: { id: string; name: string }[] = []
): string {
  if (targets === 'all') return 'Alle Rolladen';
  const groupNames = targets.groups.map((id) => groups.find((g) => g.id === id)?.name).filter(Boolean);
  const shutterNames = targets.shutters.map((id) => names[id]).filter(Boolean);
  const known = [...groupNames, ...shutterNames];
  return known.length ? known.join(', ') : 'kein Rolladen mehr';
}

/** What each group target currently means: "Obergeschoss: Bad, Kind" (US4 scenario 5). */
export function groupMembersText(
  targets: RuleTargets,
  names: Record<string, string>,
  groups: { id: string; name: string; members: string[] }[]
): string[] {
  if (targets === 'all') return [];
  return targets.groups.flatMap((id) => {
    const group = groups.find((g) => g.id === id);
    if (!group) return [];
    const members = group.members.map((m) => names[m] ?? m);
    return [`${group.name}: ${members.length ? members.join(', ') : 'leer'}`];
  });
}

/** The groups a firing reached shutters through, once each: "über Erdgeschoss, Südseite". */
export function viaText(outcomes: Outcome[]): string | null {
  const all = [...new Set(outcomes.flatMap((o) => o.via ?? []))];
  return all.length ? `über ${all.join(', ')}` : null;
}

const REASONS: Record<string, string> = {
  disabled: 'ausgeschaltet',
  no_days: 'kein Wochentag gewählt',
  no_targets: 'kein Rolladen mehr',
  no_location: 'kein Standort gesetzt',
  no_sun: 'die Sonne geht in dieser Zeit nicht auf oder unter'
};

/** Parts of an ISO timestamp with offset, read as written — the server's wall clock,
 *  not this browser's, which may be set to another timezone. */
function wallParts(iso: string): { date: string; time: string; offsetMin: number } {
  const match = iso.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}).*?([+-]\d{2}):?(\d{2})$/);
  if (!match) return { date: iso.slice(0, 10), time: iso.slice(11, 16), offsetMin: 0 };
  const sign = match[3].startsWith('-') ? -1 : 1;
  return {
    date: match[1],
    time: match[2],
    offsetMin: sign * (Math.abs(Number(match[3])) * 60 + Number(match[4]))
  };
}

function dateIn(offsetMin: number, now: Date, addDays = 0): string {
  const shifted = new Date(now.getTime() + offsetMin * 60_000 + addDays * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

/** "heute 06:45", "morgen 06:45", "Mi 24.09. 06:45" — or why it will not fire. */
export function nextText(next: { at: string | null; reason: string | null }, now: Date = new Date()): string {
  if (!next.at) return REASONS[next.reason ?? ''] ?? 'wird nicht ausgeführt';
  const { date, time, offsetMin } = wallParts(next.at);
  if (date === dateIn(offsetMin, now)) return `heute ${time}`;
  if (date === dateIn(offsetMin, now, 1)) return `morgen ${time}`;
  const [y, m, d] = date.split('-').map(Number);
  const weekday = DAY_LABELS[(new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7];
  return `${weekday} ${String(d).padStart(2, '0')}.${String(m).padStart(2, '0')}. ${time}`;
}

export function wallTime(iso: string): string {
  return wallParts(iso).time;
}

const STATUS: Record<FiringStatus, string> = {
  fired: 'ausgeführt',
  partial: 'teilweise ausgeführt',
  failed: 'fehlgeschlagen',
  skipped: 'übersprungen',
  paused: 'pausiert',
  held: 'angehalten — Uhrzeit unsicher',
  missed: 'verpasst — System war aus',
  no_sun: 'keine Sonne an diesem Tag'
};

export function statusText(status: FiringStatus): string {
  return STATUS[status];
}

export function lastText(last: Rule['last']): string | null {
  if (!last) return null;
  const when = nextText({ at: last.planned_at, reason: null });
  const count = last.total ? ` · ${last.commanded} von ${last.total}` : '';
  return `${when}: ${statusText(last.status)}${count}`;
}

export function outcomeText(outcome: Outcome): string {
  const via = outcome.via?.length ? ` (über ${outcome.via.join(', ')})` : '';
  return outcomeReason(outcome) + via;
}

function outcomeReason(outcome: Outcome): string {
  if (outcome.result === 'commanded') return 'gefahren';
  if (outcome.reason === 'measurement_in_progress') return 'übersprungen — Messung läuft';
  if (outcome.reason === 'removed') return 'übersprungen — nicht mehr konfiguriert';
  if (outcome.reason === 'bridge_unreachable') return 'nicht gefahren — Funkbrücke nicht erreichbar';
  if (outcome.reason === 'forgotten') return 'übersprungen — Funkbrücke kennt ihn nicht mehr';
  return outcome.result;
}

/** "Automationen pausiert bis morgen 00:00" — or until resumed. */
export function pauseText(until: string | null, now: Date = new Date()): string {
  return until ? `Automationen pausiert bis ${nextText({ at: until, reason: null }, now)}` : 'Automationen pausiert';
}

/** Tomorrow at midnight, as the local "YYYY-MM-DDTHH:MM" the pause endpoint takes. */
export function tomorrowMidnight(now: Date = new Date()): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T00:00`;
}
