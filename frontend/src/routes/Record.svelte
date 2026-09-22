<script lang="ts">
  // Feature 008: who did what. Newest first, filterable by shutter and by device.
  // A command here means it was sent, never that the shutter arrived — the motors
  // report nothing.
  import { onMount } from 'svelte';
  import { wallTime } from '../lib/automations';
  import { actorText, outcomeWord, whatText, type CredentialView, type RecordEntry } from '../lib/auth';
  import { auth } from '../lib/auth.svelte';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    onback: () => void;
  }
  let { onback }: Props = $props();

  let entries = $state<RecordEntry[]>([]);
  let nextBefore = $state<number | null>(null);
  let devices = $state<CredentialView[]>([]);
  let shutter = $state('');
  let device = $state('');
  let message = $state<string | null>(null);

  const nameOf = (id: string) => shutters.byId(id)?.name ?? id;

  async function load(more = false) {
    const query = new URLSearchParams();
    if (shutter) query.set('shutter', shutter);
    if (device) query.set('actor', device);
    if (more && nextBefore !== null) query.set('before', String(nextBefore));
    const response = await fetch(`/api/audit?${query}`);
    if (!response.ok) {
      message = 'Das Protokoll konnte nicht geladen werden.';
      return;
    }
    const body = await response.json();
    entries = more ? [...entries, ...body.entries] : body.entries;
    nextBefore = body.next_before;
    message = null;
  }

  function day(iso: string): string {
    return iso.slice(0, 10).split('-').reverse().join('.');
  }

  onMount(async () => {
    const listed = await auth.credentials();
    if (listed.ok) devices = listed.value.credentials;
    await load();
  });
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Protokoll</h1>
      <p class="sub">Wer hat was ausgelöst. Gesendet heißt nicht angekommen.</p>
    </div>
  </div>

  <div class="filters">
    <select bind:value={shutter} onchange={() => load()} aria-label="Rolladen">
      <option value="">Alle Rolladen</option>
      {#each shutters.shutters as s (s.id)}
        <option value={s.id}>{s.name}</option>
      {/each}
    </select>
    <select bind:value={device} onchange={() => load()} aria-label="Gerät">
      <option value="">Alle Geräte</option>
      {#each devices as d (d.id)}
        <option value={d.id}>{d.name}</option>
      {/each}
    </select>
  </div>
  <p class="note">Ein Gerät steht hier für jeden, der seinen Zugang benutzt — teilen sich zwei Handys einen, sieht man sie als eins.</p>

  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}

  <ul class="list">
    {#each entries as e, i (e.id)}
      {#if i === 0 || day(e.at) !== day(entries[i - 1].at)}
        <li class="day">{day(e.at)}</li>
      {/if}
      <li class:refused={e.outcome.startsWith('refused')} class:observed={e.actor.kind === 'bridge'}>
        <span class="time mono">{wallTime(e.at)}{#if !e.clock_ok}<span title="Die Uhr des Pi war unsicher"> ?</span>{/if}</span>
        <span class="what">{whatText(e, nameOf)}</span>
        <span class="who">{actorText(e.actor)} · {outcomeWord(e.outcome)}</span>
      </li>
    {:else}
      <li class="empty">Noch nichts aufgezeichnet.</li>
    {/each}
  </ul>

  {#if nextBefore !== null}
    <button type="button" class="more" onclick={() => load(true)}>Ältere laden</button>
  {/if}
</section>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 14px;
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
  .sub,
  .note {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--muted);
  }
  .note {
    color: var(--faint);
  }
  .filters {
    display: flex;
    gap: 8px;
  }
  select {
    flex: 1 1 0;
    min-width: 0;
    height: 40px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 0 8px;
    font-size: 14px;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .list li {
    display: grid;
    grid-template-columns: 52px 1fr;
    column-gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid var(--surface-2);
  }
  .list li.day {
    display: block;
    border: none;
    padding: 14px 0 4px;
    font-size: 12px;
    color: var(--muted);
  }
  .list li.empty {
    display: block;
    color: var(--faint);
    font-size: 14px;
    border: none;
  }
  .time {
    grid-row: span 2;
    font-size: 13px;
    color: var(--muted);
  }
  .mono {
    font-family: var(--mono);
  }
  .what {
    font-size: 14px;
  }
  .who {
    font-size: 12px;
    color: var(--muted);
  }
  .refused .who {
    color: var(--amber);
  }
  .observed .what {
    font-style: italic;
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
  .more {
    height: 44px;
    border-radius: 12px;
    border: 1px dashed var(--slat-a);
    background: transparent;
    color: var(--muted);
    font-size: 14px;
  }
</style>
