// Feature 008: is this device paired, and what may it do. The credential itself is
// an HttpOnly cookie the browser keeps and sends; script never sees it. The only
// sign of a missing or revoked one is a 401 from any call or a 4401 close of the
// live feed — either one shows the pairing screen.

import type { Ability, CredentialView, Me, OutstandingCode } from './auth';

type Result<T> = { ok: true; value: T } | { ok: false; status: number; message: string };

async function call<T>(url: string, method = 'GET', body?: unknown): Promise<Result<T>> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const parsed = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) return { ok: false, status: response.status, message: parsed?.message ?? 'Das hat nicht geklappt.' };
  return { ok: true, value: parsed as T };
}

class Auth {
  /** Unknown until the first answer; false shows the pairing screen. */
  paired = $state<boolean | null>(null);
  me = $state<Me | null>(null);
  #installed = false;

  can(ability: Ability): boolean {
    return this.me?.abilities.includes(ability) ?? false;
  }

  /** From anywhere that learned the device is not (or no longer) paired. */
  lost(): void {
    this.paired = false;
    this.me = null;
  }

  async load(): Promise<void> {
    const response = await fetch('/api/auth/me');
    if (!response.ok) return; // a 401 has already called lost()
    this.me = await response.json();
    this.paired = true;
  }

  /** Exchange a pairing code; the server sets the cookie. Null, or what to show. */
  async pair(code: string, name: string): Promise<string | null> {
    const response = await fetch('/api/auth/pair', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ code, name })
    });
    if (response.status === 401) return 'Dieser Code gilt nicht (mehr). Bitte einen neuen erzeugen.';
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return body.message ?? 'Koppeln ist fehlgeschlagen.';
    await this.load();
    return null;
  }

  // --- devices (manage) ---------------------------------------------------------

  credentials(): Promise<Result<{ credentials: CredentialView[] }>> {
    return call('/api/auth/credentials');
  }

  issue(name: string, abilities: Ability[]): Promise<Result<CredentialView & { token: string }>> {
    return call('/api/auth/credentials', 'POST', { name, abilities });
  }

  /** A 409 means this would lock everyone out; ask, then call again with confirm. */
  revoke(id: string, confirmLockout = false): Promise<Result<null>> {
    return call(`/api/auth/credentials/${id}`, 'DELETE', confirmLockout ? { confirm_lockout: true } : undefined);
  }

  codes(): Promise<Result<{ codes: OutstandingCode[] }>> {
    return call('/api/auth/pairing');
  }

  mint(abilities: Ability[]): Promise<Result<OutstandingCode>> {
    return call('/api/auth/pairing', 'POST', { abilities });
  }

  cancel(id: string): Promise<Result<null>> {
    return call(`/api/auth/pairing/${id}`, 'DELETE');
  }

  /**
   * Notice a 401 from any call, wherever it was made. One wrapper instead of a
   * check at forty call sites, each of which would sooner or later be forgotten.
   * The pairing call itself is left alone: a wrong code is its own answer.
   */
  install(): void {
    if (this.#installed) return;
    this.#installed = true;
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const response = await original(input, init);
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (response.status === 401 && url.includes('/api/') && !url.includes('/api/auth/pair')) this.lost();
      return response;
    };
  }
}

export const auth = new Auth();
