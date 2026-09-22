// Feature 008: the words for who may do what, and the pairing code as people type
// it. Kept pure so it can be tested — "darf fahren" on a phone that may only watch
// is the kind of mistake nobody notices until it matters.

export type Ability = 'watch' | 'command' | 'configure' | 'calibrate' | 'manage';

export const ABILITIES: Ability[] = ['watch', 'command', 'configure', 'calibrate', 'manage'];

const WORDS: Record<Ability, string> = {
  watch: 'zusehen',
  command: 'fahren',
  configure: 'einstellen',
  calibrate: 'kalibrieren',
  manage: 'Geräte verwalten'
};

export function abilityText(ability: Ability): string {
  return WORDS[ability];
}

/** "darf zusehen, fahren" — in the fixed order, whatever order they arrived in. */
export function abilitiesText(abilities: Ability[]): string {
  const words = ABILITIES.filter((a) => abilities.includes(a)).map(abilityText);
  return `darf ${words.join(', ')}`;
}

export interface Me {
  id: string | null;
  name: string;
  abilities: Ability[];
  origin: string;
  expires_at: string | null;
  mode: 'required' | 'open';
}

const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/** What a person typed, as the six characters it means — or null. Mirrors the server. */
export function normaliseCode(typed: string): string | null {
  const cleaned = typed.replace(/[-\s]/g, '').toUpperCase();
  if (cleaned.length !== 6 || [...cleaned].some((c) => !ALPHABET.includes(c))) return null;
  return cleaned;
}

/** "K7Q-9XM", also while typing: the dash appears after the third character. */
export function formatCode(typed: string): string {
  const cleaned = typed.replace(/[-\s]/g, '').toUpperCase().slice(0, 6);
  return cleaned.length > 3 ? `${cleaned.slice(0, 3)}-${cleaned.slice(3)}` : cleaned;
}

export interface CredentialView {
  id: string;
  name: string;
  abilities: Ability[];
  origin: 'issued' | 'paired' | 'recovery';
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  state: 'active' | 'revoked' | 'expired';
  is_me: boolean;
}

export interface OutstandingCode {
  id: string;
  abilities: Ability[];
  expires_at: string;
  /** Only in the response that minted it; never listed again. */
  code?: string;
}

const STATES: Record<CredentialView['state'], string> = {
  active: 'aktiv',
  revoked: 'widerrufen',
  expired: 'abgelaufen'
};

const ORIGINS: Record<CredentialView['origin'], string> = {
  issued: 'Token',
  paired: 'gekoppelt',
  recovery: 'Wiederherstellung'
};

export function stateText(state: CredentialView['state']): string {
  return STATES[state];
}

export function originText(origin: CredentialView['origin']): string {
  return ORIGINS[origin];
}

/** "zuletzt vor 3 Min." — or "noch nie benutzt". */
export function lastUsedText(iso: string | null, now: Date = new Date()): string {
  if (!iso) return 'noch nie benutzt';
  const minutes = Math.max(0, Math.round((now.getTime() - Date.parse(iso)) / 60000));
  if (minutes < 1) return 'gerade eben benutzt';
  if (minutes < 60) return `zuletzt vor ${minutes} Min.`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `zuletzt vor ${hours} Std.`;
  return `zuletzt vor ${Math.round(hours / 24)} Tagen`;
}

/** "4:59" until a code runs out; "abgelaufen" after. */
export function countdownText(expiresAt: string, now: number = Date.now()): string {
  const seconds = Math.floor((Date.parse(expiresAt) - now) / 1000);
  if (seconds <= 0) return 'abgelaufen';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export interface RecordEntry {
  id: number;
  at: string;
  clock_ok: boolean;
  actor: { kind: string; id: string | null; name: string | null; state?: string };
  action: string;
  shutter_id: string | null;
  target: string | null;
  outcome: string;
  detail: Record<string, unknown>;
}

const DOING: Record<string, string> = { open: 'auf', close: 'zu', stop: 'stopp' };

const OUTCOMES: Record<string, string> = {
  accepted: 'ausgeführt',
  refused_permission: 'abgelehnt — keine Berechtigung',
  refused_throttle: 'abgelehnt — zu viele Befehle',
  refused_auth: 'abgelehnt — nicht angemeldet',
  skipped: 'übersprungen — Messung läuft',
  failed: 'nicht gesendet — Funkbrücke antwortet nicht'
};

const ACTIONS: Record<string, string> = {
  resync: 'Resync',
  refused: 'Versuch',
  throttled: 'Befehl',
  rule_changed: 'Regel geändert',
  pause_changed: 'Pause geändert',
  group_changed: 'Gruppe geändert',
  location_changed: 'Standort geändert',
  calibration: 'Kalibrierung',
  shutter_added: 'Rolladen übernommen',
  shutter_changed: 'Rolladen geändert',
  credential_issued: 'Zugang ausgegeben',
  credential_revoked: 'Zugang widerrufen',
  credential_expired: 'Zugang abgelaufen',
  pairing_minted: 'Kopplungscode erzeugt',
  pairing_redeemed: 'Gerät gekoppelt',
  pairing_failed: 'Kopplung fehlgeschlagen',
  pairing_cancelled: 'Kopplungscode verworfen',
  pairing_expired: 'Kopplungscode abgelaufen',
  recovery: 'Wiederherstellung am Pi',
  auth_failed: 'Anmeldung fehlgeschlagen'
};

/** Who: the device's name as it was then, marked if it has since been revoked. */
export function actorText(actor: RecordEntry['actor']): string {
  if (actor.kind === 'automation') return `Regel „${actor.name ?? '?'}“`;
  if (actor.kind === 'bridge') return 'bemerkt, nicht von der App';
  if (actor.kind === 'anonymous') return 'unbekanntes Gerät';
  if (actor.kind === 'system') return 'System';
  const name = actor.name ?? actor.kind;
  if (!actor.state || actor.state === 'active') return name;
  return `${name} (${STATES[actor.state as CredentialView['state']] ?? actor.state})`;
}

/** What: "Wohnzimmer zu", "Wohnzimmer auf 30 %", "Gruppe geändert". */
export function whatText(entry: RecordEntry, nameOf: (id: string) => string): string {
  const shutter = entry.shutter_id ? nameOf(entry.shutter_id) : null;
  if (entry.action === 'command' || entry.action === 'movement_observed') {
    const asked = entry.detail.action;
    const percent = entry.detail.percent;
    const doing =
      entry.action === 'command' && typeof asked === 'string' && asked in DOING
        ? DOING[asked]
        : typeof percent === 'number'
          ? `auf ${percent} %`
          : '';
    return [shutter ?? 'Rolladen', doing].filter(Boolean).join(' ');
  }
  const label = ACTIONS[entry.action] ?? entry.action;
  return shutter ? `${label} · ${shutter}` : label;
}

export function outcomeWord(outcome: string): string {
  return OUTCOMES[outcome] ?? outcome;
}
