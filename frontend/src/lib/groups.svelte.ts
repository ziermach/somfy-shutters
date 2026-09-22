// Feature 004: groups of shutters. The list only ever arrives over the WebSocket —
// in the snapshot and in every `groups` frame, always complete — so every open
// client shows the same groups without reloading. Calls here change the server's
// list and let the frame bring the result back.

import type { CommandResult, Group, GroupConflict } from './types';

/** The server's message when a call failed, null when it went through. */
export type CallResult = string | null;

export type SaveResult = { ok: true; conflicts: GroupConflict[] } | { ok: false; message: string };

interface Reply {
  message?: string;
  results?: CommandResult[];
  conflicts?: GroupConflict[];
}

async function call(url: string, method: string, body?: unknown): Promise<{ response: Response; body: Reply }> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  return { response, body: await response.json().catch(() => ({})) };
}

class Groups {
  groups = $state<Group[]>([]);

  set(list: Group[]): void {
    this.groups = list;
  }

  byId(id: string): Group | undefined {
    return this.groups.find((g) => g.id === id);
  }

  /** Create (no id) or replace. A saved group may bring rule conflicts it created (FR-028). */
  async save(name: string, members: string[], id?: string): Promise<SaveResult> {
    const { response, body } = await call(id ? `/api/groups/${id}` : '/api/groups', id ? 'PUT' : 'POST', {
      name,
      members
    });
    if (!response.ok) return { ok: false, message: body.message ?? 'Die Gruppe konnte nicht gespeichert werden.' };
    return { ok: true, conflicts: body.conflicts ?? [] };
  }

  async remove(id: string): Promise<CallResult> {
    const { response, body } = await call(`/api/groups/${id}`, 'DELETE');
    return response.ok ? null : (body.message ?? 'Die Gruppe konnte nicht gelöscht werden.');
  }

  async reorder(ids: string[]): Promise<CallResult> {
    const { response, body } = await call('/api/groups/order', 'PUT', { ids });
    return response.ok ? null : (body.message ?? 'Die Reihenfolge konnte nicht gespeichert werden.');
  }
}

export const groups = new Groups();
