<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import AutomationBanner from '../components/AutomationBanner.svelte';
  import LocationCard from '../components/LocationCard.svelte';
  import RuleCard from '../components/RuleCard.svelte';
  import { tomorrowMidnight } from '../lib/automations';
  import { automations } from '../lib/automations.svelte';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    onedit: (id?: string) => void;
    onback: () => void;
  }
  let { onedit, onback }: Props = $props();

  onMount(() => automations.watch(true));
  onDestroy(() => automations.watch(false));

  let pauseUntil = $state('');
  let pauseMessage = $state<string | null>(null);
  async function pause(until: string | null) {
    pauseMessage = await automations.pause(until);
  }

  const names = $derived(Object.fromEntries(shutters.shutters.map((s) => [s.id, s.name])));
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Automationen</h1>
      <p class="sub">Regeln laufen auf dem Pi — auch wenn kein Handy an ist.</p>
    </div>
  </div>

  <AutomationBanner />

  {#if !automations.state.paused && automations.rules.length}
    <div class="pause">
      <span class="label">Pausieren</span>
      <div class="pause-row">
        <button type="button" class="chip" onclick={() => pause(tomorrowMidnight())}>bis morgen</button>
        <button type="button" class="chip" onclick={() => pause(null)}>bis ich fortsetze</button>
        <input type="datetime-local" bind:value={pauseUntil} aria-label="Pausieren bis" />
        <button type="button" class="chip" disabled={!pauseUntil} onclick={() => pause(pauseUntil)}>bis Datum</button>
      </div>
      {#if pauseMessage}<p class="error" role="alert">{pauseMessage}</p>{/if}
    </div>
  {/if}

  <div class="rules">
    {#each automations.rules as rule (rule.id)}
      <RuleCard {rule} {names} onedit={(id) => onedit(id)} />
    {:else}
      {#if automations.loaded}
        <p class="empty">Noch keine Regel.</p>
      {/if}
    {/each}
  </div>

  <button type="button" class="add" onclick={() => onedit()}>+ Neue Regel</button>

  {#if automations.loaded}
    <LocationCard />
  {/if}

  <p class="note">
    Eine Regel schickt Befehle — ob der Rolladen angekommen ist, kann niemand melden. Zwischenpositionen bleiben
    Schätzungen.
  </p>
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
  .sub {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .pause {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .label {
    font-size: 13px;
    color: var(--muted);
  }
  .pause-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
  }
  .chip {
    border-radius: 9px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
  }
  .chip:disabled {
    opacity: 0.4;
  }
  input[type='datetime-local'] {
    height: 34px;
    border-radius: 9px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 0 8px;
    font-size: 12px;
  }
  .error {
    margin: 0;
    font-size: 12px;
    color: var(--amber);
  }
  .rules {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .empty {
    margin: 0;
    font-size: 14px;
    color: var(--faint);
  }
  .add {
    height: 48px;
    border-radius: 14px;
    border: 1px dashed var(--slat-a);
    background: transparent;
    color: var(--muted);
    font-size: 15px;
    font-weight: 500;
  }
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
  }
</style>
