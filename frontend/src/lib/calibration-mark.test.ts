// A failed "Fertig" press must end in a message, never in silence with the timer
// still running — that is what a person saw on the Pi.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { calibration } from './calibration.svelte';

function answer(status: number, body: string): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain' } });
}

beforeEach(() => {
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
  calibration.phase = 'timing';
  calibration.message = '';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('marking arrival when it fails', () => {
  it('ends the run with the status when the server answers without JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => answer(500, 'Internal Server Error')));
    await calibration.mark('flink', 'arrived');
    expect(calibration.phase).toBe('idle');
    expect(calibration.message).toContain('500');
  });

  it('shows the server message when there is one', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ message: 'Für diesen Rolladen läuft keine Messung.' }), { status: 409 })
      )
    );
    await calibration.mark('flink', 'arrived');
    expect(calibration.phase).toBe('idle');
    expect(calibration.message).toBe('Für diesen Rolladen läuft keine Messung.');
  });

  it('keeps the run and asks to press again when the house is not reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    await calibration.mark('flink', 'arrived');
    expect(calibration.phase).toBe('timing');
    expect(calibration.message).toContain('Keine Verbindung');
  });
});
