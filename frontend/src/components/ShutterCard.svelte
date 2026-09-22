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
  const busy = $derived(!shutters.bridge.connected);

  const state = $derived(
    shutter.movement
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

<div class="card" class:stale={shutter.position.stale}>
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
      <ConfidenceBadge position={shutter.position} />
      {#if !shutter.calibrated}
        <span class="warn">Laufzeit nicht gemessen</span>
      {/if}
    </div>
    <span class="pct">{percentText(live)}</span>
  </div>
  <div class="row">
    <button type="button" class="btn" disabled={busy} onclick={() => shutters.command(shutter.id, 'open')}>auf</button>
    <button type="button" class="btn" disabled={busy} onclick={() => shutters.command(shutter.id, 'stop')}>stop</button>
    <button type="button" class="btn" disabled={busy} onclick={() => shutters.command(shutter.id, 'close')}>zu</button>
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
