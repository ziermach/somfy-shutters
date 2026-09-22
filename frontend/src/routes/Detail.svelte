<script lang="ts">
  import { auth } from '../lib/auth.svelte';
  import ConfidenceBadge from '../components/ConfidenceBadge.svelte';
  import MeasuringBanner from '../components/MeasuringBanner.svelte';
  import WindowGraphic from '../components/WindowGraphic.svelte';
  import { percentText } from '../lib/confidence';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    id: string;
    onback: () => void;
    oncalibrate: (id: string) => void;
  }
  let { id, onback, oncalibrate }: Props = $props();

  const shutter = $derived(shutters.byId(id));
  const live = $derived(shutter ? shutters.livePercent(shutter) : null);
  const busy = $derived(!shutters.bridge.connected || (shutter?.measuring ?? false));

  let sliderValue = $state(0);
  let dragging = $state(false);
  $effect(() => {
    if (!dragging && live !== null) sliderValue = live;
  });

  const travel = $derived(
    !shutter
      ? ''
      : shutter.calibrated
        ? `Laufzeit ${shutter.travel_up_seconds} s auf · ${shutter.travel_down_seconds} s zu`
        : 'Laufzeit nicht kalibriert — geschätzt'
  );
</script>

{#if shutter}
  <section class="screen">
    <div class="head">
      <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <div>
        <h1>{shutter.name}</h1>
        <p class="sub">{travel}</p>
      </div>
    </div>

    {#if shutter.measuring}
      <MeasuringBanner name={shutter.name} />
    {/if}

    <div class="stage">
      <WindowGraphic
        percent={live}
        size="lg"
        dim={shutter.position.stale}
        unknown={shutter.position.confidence === 'unknown'}
        easeMs={shutters.easing[shutter.id] ?? 0}
      />
    </div>

    <div class="readout">
      <span class="pct">{percentText(live)}</span>
      <ConfidenceBadge position={shutter.position} moving={shutter.movement !== null} />
    </div>

    {#if auth.can('command')}
    <div class="slider">
      <label for="target">Zielposition</label>
      <input
        id="target"
        type="range"
        min="0"
        max="100"
        step="1"
        bind:value={sliderValue}
        disabled={busy}
        onpointerdown={() => (dragging = true)}
        onpointerup={() => (dragging = false)}
        onchange={() => {
          dragging = false;
          shutters.command(shutter.id, 'position', sliderValue);
        }}
      />
      <div class="scale"><span>0 % geschlossen</span><span>100 % offen</span></div>
    </div>

    <div class="row">
      <button type="button" class="btn big" disabled={busy || !shutters.canOpen(shutter)} onclick={() => shutters.command(shutter.id, 'open')}>auf</button>
      <button type="button" class="btn big" disabled={busy || !shutters.canStop(shutter)} onclick={() => shutters.command(shutter.id, 'stop')}>stop</button>
      <button type="button" class="btn big" disabled={busy || !shutters.canClose(shutter)} onclick={() => shutters.command(shutter.id, 'close')}>zu</button>
    </div>
    {/if}

    {#if auth.can('calibrate')}
      <button type="button" class="btn calibrate" disabled={shutter.measuring} onclick={() => oncalibrate(shutter.id)}>
        {shutter.calibrated ? 'Laufzeiten neu messen' : 'Laufzeiten messen'}
      </button>
    {/if}

    {#if shutter.position.confidence !== 'certain'}
      <div class="conf">
        <p>
          {#if shutter.position.confidence === 'unknown'}
            Die Position ist unbekannt — nach einem Neustart weiß das System nicht, wo der
            Rolladen steht. Eine Fahrt an die Endlage stellt das wieder her.
          {:else}
            Seit der letzten Endlage wird aus der Laufzeit gerechnet. Fernbedienung,
            Stromausfall oder ein Hindernis können die Anzeige verschoben haben.
          {/if}
        </p>
        {#if auth.can('command')}
          <button type="button" class="btn amber" disabled={busy} onclick={() => shutters.resync(shutter.id)}>
            Resync — an die Endlage fahren
          </button>
        {/if}
      </div>
    {/if}
  </section>
{/if}

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
  .stage {
    display: flex;
    justify-content: center;
  }
  .readout {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 12px;
  }
  .pct {
    font-family: var(--mono);
    font-size: 44px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }
  .slider {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .slider label {
    font-size: 13px;
    color: var(--muted);
  }
  .slider input {
    width: 100%;
    height: 44px;
    accent-color: var(--amber);
  }
  .scale {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--faint);
  }
  .row {
    display: flex;
    gap: 10px;
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
  .btn.big {
    height: 52px;
    border-radius: 14px;
    font-size: 16px;
    font-weight: 600;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .conf {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .calibrate {
    height: 44px;
    border-radius: 12px;
    background: var(--surface);
  }
  .conf p {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
  }
  .amber {
    background: var(--amber-soft);
    border-color: var(--amber-line);
    color: var(--amber);
    font-weight: 600;
  }
</style>
