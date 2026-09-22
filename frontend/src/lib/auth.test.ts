import { describe, expect, it } from 'vitest';
import { abilitiesText, formatCode, normaliseCode } from './auth';

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
