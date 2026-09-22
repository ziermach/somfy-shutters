// Feature 003: rules, pause and clock state. The rules are fetched over REST by the
// automations screen; pause and clock state arrive with every WebSocket snapshot,
// because the overview's banner needs them without anyone opening that screen.

import type { AutomationState, Conflict, Firing, HomeLocation, Rule, RuleDraft } from './automations';

export type SaveResult = { ok: true; rule: Rule; conflicts: Conflict[] } | { ok: false; message: string };

class Automations {
  rules = $state<Rule[]>([]);
  location = $state<HomeLocation | null>(null);
  state = $state<AutomationState>({ paused: false, until: null, clock_reliable: true, clock_reason: null });
  loaded = $state(false);
  #watching = false;

  /** The automations screen is open: keep the list fresh from frames. */
  watch(on: boolean): void {
    this.#watching = on;
    if (on) void this.load();
  }

  async load(): Promise<void> {
    const response = await fetch('/api/automations');
    if (!response.ok) return;
    const body = await response.json();
    this.rules = body.rules;
    this.location = body.location;
    this.state = {
      paused: body.pause.paused,
      until: body.pause.until,
      clock_reliable: body.clock.reliable,
      clock_reason: body.clock.reason
    };
    this.loaded = true;
  }

  byId(id: string): Rule | undefined {
    return this.rules.find((r) => r.id === id);
  }

  /** From the WebSocket: snapshot and `automations` frames. */
  setState(state: AutomationState): void {
    this.state = state;
  }

  /** From the WebSocket: something about the rules changed or a rule fired. */
  changed(): void {
    if (this.#watching) void this.load();
  }

  async save(draft: RuleDraft, id?: string): Promise<SaveResult> {
    const response = await fetch(id ? `/api/automations/${id}` : '/api/automations', {
      method: id ? 'PUT' : 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(draft)
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return { ok: false, message: body.message ?? 'Speichern fehlgeschlagen.' };
    await this.load();
    return { ok: true, rule: body, conflicts: body.conflicts ?? [] };
  }

  async remove(id: string): Promise<void> {
    await fetch(`/api/automations/${id}`, { method: 'DELETE' });
    await this.load();
  }

  async firings(id: string): Promise<Firing[]> {
    const response = await fetch(`/api/automations/${id}/firings`);
    if (!response.ok) return [];
    return (await response.json()).firings;
  }
}

export const automations = new Automations();
