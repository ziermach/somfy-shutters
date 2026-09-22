// Feature 005: the household's shutters and what the bridge announces beyond them.
//
// The counts arrive over the WebSocket (snapshot and `roster` frames), so the overview
// can say "Neuer Rolladen gefunden" at once. The full list is only fetched by the
// screens that need it, and re-fetched whenever a frame says something changed.

import type { RemovalPreview, Roster, RosterCounts, Shutter } from './types';

export type Outcome<T = null> = { ok: true; value: T } | { ok: false; message: string };

async function call<T>(url: string, method = 'GET', body?: unknown): Promise<Outcome<T>> {
  try {
    const response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) return { ok: false, message: data.message ?? 'Das hat nicht geklappt.' };
    return { ok: true, value: data as T };
  } catch {
    return { ok: false, message: 'Keine Verbindung zum Haus.' };
  }
}

class RosterState {
  counts = $state<RosterCounts>({ new: 0, forgotten: [] });
  /** Null until a screen asked for it. */
  data = $state<Roster | null>(null);
  #watching = 0;

  setCounts(counts: RosterCounts): void {
    this.counts = counts;
    // Something changed; a screen showing the list must not show the old one.
    if (this.#watching > 0) void this.load();
  }

  isForgotten(id: string): boolean {
    return this.counts.forgotten.includes(id);
  }

  /** A screen showing the roster keeps it fresh while it is open. Returns the release. */
  watch(): () => void {
    this.#watching += 1;
    void this.load();
    return () => {
      this.#watching -= 1;
    };
  }

  async load(): Promise<void> {
    const result = await call<Roster>('/api/roster');
    if (result.ok) this.data = result.value;
  }

  async confirm(address: string, name: string): Promise<Outcome<Shutter>> {
    const result = await call<Shutter>(`/api/roster/new/${address}`, 'POST', { name });
    await this.load();
    return result;
  }

  async rename(id: string, name: string): Promise<Outcome<Shutter>> {
    const result = await call<Shutter>(`/api/shutters/${id}`, 'PATCH', { name });
    await this.load();
    return result;
  }

  async preview(id: string): Promise<Outcome<RemovalPreview>> {
    return call<RemovalPreview>(`/api/shutters/${id}/removal`);
  }

  async remove(id: string): Promise<Outcome<{ removed: string; set_aside: boolean }>> {
    const result = await call<{ removed: string; set_aside: boolean }>(`/api/shutters/${id}`, 'DELETE');
    await this.load();
    return result;
  }

  async restore(address: string): Promise<Outcome<unknown>> {
    const result = await call<unknown>(`/api/roster/set-aside/${address}/restore`, 'POST');
    await this.load();
    return result;
  }
}

export const roster = new RosterState();
