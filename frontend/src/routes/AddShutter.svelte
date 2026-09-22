<script lang="ts">
  // Feature 005, US2/US5: "Rolladen hinzufügen". The person works in Pi-Somfy, on the
  // remote and at the window; the app explains, then notices the new shutter by
  // itself (FR-008) and asks for a name. It never programs anything (FR-007).
  import { onMount } from 'svelte';
  import {
    NO_ANNOUNCEMENTS_HINT,
    POWER_WARNING,
    STALE_HINT,
    TIMEOUT_HINTS,
    TIMEOUT_MS,
    steps,
    type Route
  } from '../lib/roster';
  import { roster } from '../lib/roster.svelte';
  import type { NewShutter } from '../lib/types';

  interface Props {
    onback: () => void;
    oncalibrate: (id: string) => void;
  }
  let { onback, oncalibrate }: Props = $props();

  let route = $state<Route | null>(null);
  let startedAt = $state(Date.now());
  let now = $state(Date.now());
  // New shutters already waiting when the guide opened are not the one being added.
  let baseline = $state<Set<string> | null>(null);
  let name = $state('');
  let error = $state<string | null>(null);
  let added = $state<{ id: string; name: string } | null>(null);

  onMount(() => {
    const release = roster.watch();
    const timer = setInterval(() => (now = Date.now()), 5000);
    return () => {
      release();
      clearInterval(timer);
    };
  });

  $effect(() => {
    if (baseline === null && roster.data) baseline = new Set(roster.data.new.map((n) => n.address));
  });

  const found = $derived<NewShutter | undefined>(
    baseline && roster.data ? roster.data.new.find((n) => !baseline!.has(n.address)) : undefined
  );
  const waitingBefore = $derived(roster.data && baseline ? roster.data.new.filter((n) => baseline!.has(n.address)) : []);
  const timedOut = $derived(route !== null && !found && now - startedAt >= TIMEOUT_MS);
  const webUrl = $derived(roster.data?.bridge.web_url ?? null);

  let prefilledFor = '';
  $effect(() => {
    if (found && prefilledFor !== found.address) {
      prefilledFor = found.address;
      name = found.suggested_name;
    }
  });

  function choose(chosen: Route) {
    route = chosen;
    startedAt = Date.now();
    now = startedAt;
  }

  function keepWaiting() {
    startedAt = Date.now();
    now = startedAt;
  }

  async function confirm() {
    if (!found) return;
    const result = await roster.confirm(found.address, name);
    if (result.ok) {
      added = { id: result.value.id, name: result.value.name };
      error = null;
    } else {
      error = result.message;
    }
  }
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Rolladen hinzufügen</h1>
      <p class="sub">Angelernt wird in Pi-Somfy. Die App erklärt und merkt, wenn es geklappt hat.</p>
    </div>
  </div>

  {#if added}
    <div class="card done" role="status">
      <strong>{added.name} ist im Haus.</strong>
      <span>Laufzeit nicht gemessen — bis dahin rechnet die App mit einem Standardwert.</span>
    </div>
    <button type="button" class="primary" onclick={() => oncalibrate(added!.id)}>Jetzt Laufzeit messen</button>
    <button type="button" class="ghost" onclick={onback}>Später</button>
  {:else if found}
    <form class="card found" onsubmit={(e) => { e.preventDefault(); confirm(); }}>
      <strong>Neuer Rolladen gefunden: {found.bridge_name}</strong>
      <label class="field">
        <span>Name im Haus</span>
        <input maxlength="40" bind:value={name} />
      </label>
      {#if error}
        <p class="error" role="alert">{error}</p>
      {/if}
      <button type="submit" class="primary">Übernehmen</button>
    </form>
  {:else if route === null}
    <p class="lead">Funktioniert die alte Fernbedienung dieses Rolladens noch?</p>
    <button type="button" class="choice" onclick={() => choose('remote')}>
      <strong>Ja, Fernbedienung vorhanden</strong>
      <span>Anlernen mit der PROG-Taste.</span>
    </button>
    <button type="button" class="choice" onclick={() => choose('power')}>
      <strong>Keine Fernbedienung mehr</strong>
      <span>Anlernen über kurzes Ausschalten der Sicherung.</span>
    </button>
    {#if waitingBefore.length}
      <p class="note">
        {waitingBefore.length === 1 ? 'Ein gemeldeter Rolladen wartet' : `${waitingBefore.length} gemeldete Rolladen warten`}
        schon auf einen Namen — unter „Rolladen“.
      </p>
    {/if}
  {:else}
    {#if route === 'power'}
      <div class="warning" role="alert">
        <strong>Achtung, gemeinsamer Stromkreis</strong>
        <p>{POWER_WARNING}</p>
      </div>
    {/if}

    <ol class="steps">
      {#each steps(route) as step, i (step.id)}
        <li class="step">
          <span class="num">{i + 1}</span>
          <div class="body">
            <span class="where">{step.where}</span>
            <strong>{step.title}</strong>
            <p>{step.text}</p>
            <p class="ok">✓ {step.success}</p>
            {#if step.id === 'create' && webUrl}
              <a class="link" href={webUrl} target="_blank" rel="noopener noreferrer">Pi-Somfy öffnen ↗</a>
            {/if}
          </div>
        </li>
      {/each}
    </ol>

    {#if roster.data && !roster.data.bridge.announcements_seen}
      <p class="note">{NO_ANNOUNCEMENTS_HINT}</p>
    {/if}

    {#if timedOut}
      <div class="card hints" role="status">
        <strong>Seit zehn Minuten kein neuer Rolladen. Meistens liegt es daran:</strong>
        <ul>
          {#each TIMEOUT_HINTS as hint (hint)}
            <li>{hint}</li>
          {/each}
        </ul>
        <div class="actions">
          <button type="button" class="ghost" onclick={onback}>Abbrechen</button>
          <button type="button" class="primary" onclick={keepWaiting}>Weiter warten</button>
        </div>
      </div>
    {:else}
      <p class="waiting" role="status"><span class="dot" aria-hidden="true"></span> Warte auf die Meldung der Funkbrücke …</p>
    {/if}

    <p class="note">{STALE_HINT}</p>
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
    font-size: 13px;
    color: var(--muted);
  }
  .lead {
    margin: 0;
    font-size: 15px;
  }
  .card,
  .choice {
    border-radius: 14px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    text-align: left;
  }
  .choice span,
  .done span {
    font-size: 13px;
    color: var(--muted);
  }
  .found {
    border-color: var(--amber-line);
  }
  .warning {
    border-radius: 14px;
    border: 1px solid var(--amber-line);
    background: var(--amber-soft);
    color: var(--amber);
    padding: 14px;
    font-size: 13px;
  }
  .warning p {
    margin: 6px 0 0;
  }
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .step {
    display: flex;
    gap: 12px;
    border-radius: 14px;
    border: 1px solid var(--line);
    background: var(--surface);
    padding: 12px 14px;
  }
  .num {
    width: 26px;
    height: 26px;
    flex-shrink: 0;
    border-radius: 50%;
    border: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    color: var(--muted);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .body p {
    margin: 0;
    font-size: 14px;
  }
  .where {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--faint);
  }
  .ok {
    color: var(--muted);
    font-size: 13px !important;
  }
  .link {
    font-size: 14px;
    color: var(--text);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }
  input {
    height: 42px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
    padding: 0 12px;
    font-size: 15px;
  }
  .hints ul {
    margin: 0;
    padding-left: 18px;
    font-size: 13px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .primary,
  .ghost {
    flex: 1 1 0;
    min-height: 44px;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 500;
  }
  .primary {
    border: 1px solid var(--text);
    background: var(--text);
    color: var(--surface);
  }
  .ghost {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
  }
  .waiting {
    margin: 0;
    font-size: 14px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.25;
    }
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
</style>
