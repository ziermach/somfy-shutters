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
