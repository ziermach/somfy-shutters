<script lang="ts">
  import { onMount } from 'svelte';
  import { calibration, stateLabel, timesLabel } from '../lib/calibration.svelte';

  interface Props {
    onopen: (id: string) => void;
    onback: () => void;
  }
  let { onopen, onback }: Props = $props();

  onMount(() => {
    calibration.loadList();
  });

  const tone = (state: string) =>
    state === 'calibrated' ? 'sure' : state === 'uncalibrated' ? 'grey' : 'est';
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Kalibrierung</h1>
      <p class="sub">Laufzeit je Rolladen und Richtung. Ohne sie rät die App.</p>
    </div>
  </div>

  <div class="rows">
    {#each calibration.shutters as shutter (shutter.id)}
      <button type="button" class="row" class:due={shutter.state !== 'calibrated'} onclick={() => onopen(shutter.id)}>
        <div class="meta">
          <span class="name">{shutter.name}</span>
          <span class="times">{timesLabel(shutter)}</span>
          <span class="state"><span class="dot {tone(shutter.state)}"></span>{stateLabel(shutter)}</span>
        </div>
        <svg class="chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 6l6 6-6 6" />
        </svg>
      </button>
    {/each}
  </div>

  <p class="note">
    Gemessen wird von Hand: zwei Knopfdrücke je Fahrt. Es gibt nichts im System, das
    beobachtet, wann eine Fahrt endet — der Motor meldet nichts zurück.
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
  .rows {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .row {
    width: 100%;
    text-align: left;
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    gap: 12px;
    align-items: center;
    color: var(--text);
  }
  .row:hover {
    border-color: var(--line);
  }
  .row.due {
    border-color: var(--amber-line);
  }
  .meta {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .name {
    font-size: 16px;
    font-weight: 600;
  }
  .times {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .state {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--grey-dot);
  }
  .dot.sure {
    background: var(--teal);
  }
  .dot.est {
    background: var(--amber);
  }
  .chev {
    color: var(--faint);
    flex-shrink: 0;
  }
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
    line-height: 1.5;
  }
</style>
