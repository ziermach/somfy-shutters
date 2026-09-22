<script lang="ts">
  // Feature 008: which devices may talk to the house. Pair a phone with a code read
  // out across the room, issue a token for a script, revoke what was lost. Only a
  // device that may manage devices sees this screen.
  import { onDestroy, onMount } from 'svelte';
  import {
    ABILITIES,
    abilitiesText,
    abilityText,
    countdownText,
    lastUsedText,
    originText,
    stateText,
    type Ability,
    type CredentialView,
    type OutstandingCode
  } from '../lib/auth';
  import { auth } from '../lib/auth.svelte';

  interface Props {
    onback: () => void;
  }
  let { onback }: Props = $props();

  let credentials = $state<CredentialView[]>([]);
  let message = $state<string | null>(null);
  let now = $state(Date.now());

  /** Only what this device holds itself can be handed on (FR-011). */
  const offerable = $derived(ABILITIES.filter((a) => a !== 'watch' && auth.can(a)));

  async function refresh() {
    const result = await auth.credentials();
    if (result.ok) credentials = result.value.credentials;
    else message = result.message;
  }

  let timer: ReturnType<typeof setInterval> | undefined;
  onMount(() => {
    void refresh();
    timer = setInterval(() => {
      now = Date.now();
      // A code being redeemed shows up as a new device without anyone reloading.
      if (pairing && Math.floor(now / 1000) % 3 === 0) void refresh();
    }, 1000);
  });
  onDestroy(() => clearInterval(timer));

  // --- pairing ------------------------------------------------------------------

  let pairAbilities = $state<Ability[]>(['command']);
  let pairing = $state<OutstandingCode | null>(null);

  function toggle(list: Ability[], ability: Ability): Ability[] {
    return list.includes(ability) ? list.filter((a) => a !== ability) : [...list, ability];
  }

  async function mint() {
    message = null;
    const result = await auth.mint(['watch', ...pairAbilities]);
    if (result.ok) pairing = result.value;
    else message = result.message;
  }

  async function cancelPairing() {
    if (pairing) await auth.cancel(pairing.id);
    pairing = null;
  }

  // --- tokens -------------------------------------------------------------------

  let tokenName = $state('');
  let tokenAbilities = $state<Ability[]>(['command']);
  let issued = $state<{ name: string; token: string } | null>(null);
  let copied = $state(false);

  async function issue() {
    message = null;
    const result = await auth.issue(tokenName.trim(), ['watch', ...tokenAbilities]);
    if (!result.ok) {
      message = result.message;
      return;
    }
    issued = { name: result.value.name, token: result.value.token };
    tokenName = '';
    copied = false;
    await refresh();
  }

  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.token);
      copied = true;
    } catch {
      copied = false; // no clipboard over plain HTTP in some browsers; select it by hand
    }
  }

  // --- revoking -----------------------------------------------------------------

  let confirming = $state<string | null>(null);
  let lockout = $state<{ id: string; message: string } | null>(null);

  async function revoke(id: string, confirmLockout = false) {
    message = null;
    const result = await auth.revoke(id, confirmLockout);
    if (!result.ok && result.status === 409) {
      lockout = { id, message: result.message };
      return;
    }
    confirming = null;
    lockout = null;
    if (!result.ok) message = result.message;
    await refresh();
  }
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Geräte</h1>
      <p class="sub">Jedes Gerät hat seinen eigenen Zugang und lässt sich einzeln widerrufen.</p>
    </div>
  </div>

  <div class="card">
    <h2>Gerät koppeln</h2>
    {#if pairing}
      <p class="code" aria-live="polite">{pairing.code}</p>
      <p class="meta">
        {abilitiesText(pairing.abilities)} · gültig noch {countdownText(pairing.expires_at, now)} · einmal verwendbar
      </p>
      <p class="hint">Auf dem neuen Gerät die App öffnen, Code eingeben, Gerät benennen.</p>
      <button type="button" class="btn" onclick={cancelPairing}>Abbrechen</button>
    {:else}
      <div class="chips" role="group" aria-label="Das neue Gerät darf">
        {#each offerable as ability (ability)}
          <button type="button" class="chip" class:on={pairAbilities.includes(ability)} aria-pressed={pairAbilities.includes(ability)} onclick={() => (pairAbilities = toggle(pairAbilities, ability))}>{abilityText(ability)}</button>
        {/each}
      </div>
      <p class="meta">Zusehen darf jedes Gerät.</p>
      <button type="button" class="primary" onclick={mint}>Code erzeugen</button>
    {/if}
  </div>

  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}

  <ul class="list">
    {#each credentials as c (c.id)}
      <li class:gone={c.state !== 'active'}>
        <div class="row">
          <span class="name">{c.name}{#if c.is_me}<span class="me"> · dieses Gerät</span>{/if}</span>
          <span class="state">{stateText(c.state)}</span>
        </div>
        <div class="meta">{abilitiesText(c.abilities)} · {originText(c.origin)} · {lastUsedText(c.last_used_at, new Date(now))}</div>
        {#if c.state === 'active'}
          {#if lockout?.id === c.id}
            <p class="warn" role="alert">{lockout.message}</p>
            <div class="row gap">
              <button type="button" class="btn danger" onclick={() => revoke(c.id, true)}>Trotzdem widerrufen</button>
              <button type="button" class="btn" onclick={() => (lockout = null)}>Abbrechen</button>
            </div>
          {:else if confirming === c.id}
            <div class="row gap">
              <button type="button" class="btn danger" onclick={() => revoke(c.id)}>Wirklich widerrufen</button>
              <button type="button" class="btn" onclick={() => (confirming = null)}>Abbrechen</button>
            </div>
          {:else}
            <button type="button" class="link" onclick={() => (confirming = c.id)}>Widerrufen</button>
          {/if}
        {/if}
      </li>
    {/each}
  </ul>

  <details class="card">
    <summary>Zugang für ein Skript (Token)</summary>
    {#if issued}
      <p class="meta">Token für „{issued.name}“ — wird nur jetzt angezeigt:</p>
      <input class="token" readonly value={issued.token} onfocus={(e) => e.currentTarget.select()} />
      <button type="button" class="btn" onclick={copy}>{copied ? 'Kopiert' : 'Kopieren'}</button>
      <button type="button" class="link" onclick={() => (issued = null)}>Fertig</button>
    {:else}
      <input type="text" bind:value={tokenName} placeholder="z. B. Kurzbefehl Nacht" maxlength="40" />
      <div class="chips" role="group" aria-label="Das Skript darf">
        {#each offerable as ability (ability)}
          <button type="button" class="chip" class:on={tokenAbilities.includes(ability)} aria-pressed={tokenAbilities.includes(ability)} onclick={() => (tokenAbilities = toggle(tokenAbilities, ability))}>{abilityText(ability)}</button>
        {/each}
      </div>
      <button type="button" class="btn" disabled={!tokenName.trim()} onclick={issue}>Token erzeugen</button>
    {/if}
  </details>
</section>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .back {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  h1 {
    margin: 0;
    font-family: var(--display);
    font-size: 26px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .sub {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 14px;
    padding: 14px;
  }
  summary {
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
  }
  details[open] summary {
    margin-bottom: 10px;
  }
  .code {
    margin: 0;
    font-family: var(--mono);
    font-size: 40px;
    letter-spacing: 0.12em;
    text-align: center;
  }
  .meta {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .hint {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
  }
  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .chip {
    border-radius: 9px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--surface-2);
    background: transparent;
    color: var(--faint);
  }
  .chip.on {
    background: var(--amber-soft);
    border-color: var(--amber-line);
    color: var(--amber);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .list li {
    display: flex;
    flex-direction: column;
    gap: 6px;
    border: 1px solid var(--surface-2);
    border-radius: 12px;
    padding: 12px;
  }
  .list li.gone {
    opacity: 0.55;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
  }
  .row.gap {
    justify-content: flex-start;
  }
  .name {
    font-size: 15px;
    font-weight: 500;
  }
  .me {
    font-weight: 400;
    color: var(--muted);
  }
  .state {
    font-size: 12px;
    color: var(--muted);
  }
  input {
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--bg, var(--surface));
    color: var(--text);
    padding: 0 12px;
    font-size: 15px;
  }
  .token {
    font-family: var(--mono);
    font-size: 12px;
  }
  .primary {
    height: 48px;
    border-radius: 12px;
    border: 1px solid var(--amber);
    background: var(--amber);
    color: var(--ink);
    font-size: 15px;
    font-weight: 600;
  }
  .btn {
    height: 40px;
    border-radius: 11px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    padding: 0 14px;
  }
  .btn:disabled {
    opacity: 0.4;
  }
  .btn.danger {
    border-color: var(--amber-line);
    background: var(--amber-soft);
    color: var(--amber);
  }
  .link {
    all: unset;
    cursor: pointer;
    align-self: flex-start;
    font-size: 12px;
    color: var(--muted);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .warn,
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
</style>
