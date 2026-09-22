<script lang="ts">
  import { percentText } from '../lib/confidence';
  import { shutters } from '../lib/shutters.svelte';
  import type { Shutter } from '../lib/types';
  import ConfidenceBadge from './ConfidenceBadge.svelte';
  import WindowGraphic from './WindowGraphic.svelte';

  interface Props {
    shutter: Shutter;
    onopen: (id: string) => void;
  }
  let { shutter, onopen }: Props = $props();

  const live = $derived(shutters.livePercent(shutter));
  const busy = $derived(!shutters.bridge.connected || shutter.measuring);

  const state = $derived(
    shutter.forgotten
      ? 'Funkbrücke kennt ihn nicht mehr'
      : shutter.measuring
      ? 'wird gemessen …'
      : shutter.movement
      ? shutter.movement.direction === 'up'
        ? 'fährt auf …'
        : 'fährt zu …'
      : live === null
        ? 'unbekannt'
        : live === 100
          ? 'offen'
          : live === 0
            ? 'geschlossen'
            : 'Teilposition'
  );
</script>

<div class="card" class:stale={shutter.position.stale} class:measuring={shutter.measuring}>
  <div class="top">
    <WindowGraphic
      percent={live}
      dim={shutter.position.stale}
      unknown={shutter.position.confidence === 'unknown'}
      easeMs={shutters.easing[shutter.id] ?? 0}
    />
    <div class="meta">
      <button type="button" class="name" onclick={() => onopen(shutter.id)}>{shutter.name}</button>
      <span class="sub">{state}</span>
      <ConfidenceBadge position={shutter.position} moving={shutter.movement !== null} />
      {#if shutter.forgotten}
        <span class="warn">Befehle gehen nicht mehr raus</span>
      {:else if shutter.measuring}
        <span class="measuring"><span class="pulse"></span>Messung läuft</span>
      {:else if !shutter.calibrated}
        <span class="warn">Laufzeit nicht gemessen</span>
      {/if}
    </div>
    <span class="pct">{percentText(live)}</span>
  </div>
  <div class="row">
    <button type="button" class="btn" disabled={busy || !shutters.canOpen(shutter)} onclick={() => shutters.command(shutter.id, 'open')}>auf</button>
    <button type="button" class="btn" disabled={busy || !shutters.canStop(shutter)} onclick={() => shutters.command(shutter.id, 'stop')}>stop</button>
    <button type="button" class="btn" disabled={busy || !shutters.canClose(shutter)} onclick={() => shutters.command(shutter.id, 'close')}>zu</button>
  </div>
</div>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .card.stale {
    opacity: 0.7;
  }
  .top {
    display: flex;
    gap: 14px;
    align-items: center;
  }
  .meta {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .name {
    all: unset;
    cursor: pointer;
    font-size: 17px;
    font-weight: 600;
    color: var(--text);
  }
  .name:hover {
    color: var(--amber);
  }
  .name:focus-visible {
    outline: 2px solid var(--amber);
    outline-offset: 2px;
    border-radius: 4px;
  }
  .sub {
    font-size: 13px;
    color: var(--muted);
  }
  .warn {
    font-size: 12px;
    color: var(--faint);
  }
  .card.measuring {
    border-color: var(--amber-line);
  }
  .measuring {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--amber);
  }
  .pulse {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--amber);
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.25;
    }
  }
  .pct {
    font-family: var(--mono);
    font-size: 22px;
    font-variant-numeric: tabular-nums;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  .btn {
    flex: 1 1 0;
    height: 44px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    color: var(--text);
    font-size: 14px;
    font-weight: 500;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
