<script lang="ts">
  import MeasuringBanner from '../components/MeasuringBanner.svelte';
  import ShutterCard from '../components/ShutterCard.svelte';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    onopen: (id: string) => void;
    oncalibration: () => void;
  }
  let { onopen, oncalibration }: Props = $props();
</script>

<section class="screen">
  <header>
    <h1>Zuhause</h1>
    <p class="sub">{shutters.shutters.length} Rolladen · 100 % = ganz offen</p>
  </header>

  {#if shutters.measuring}
    <MeasuringBanner name={shutters.measuring.name} />
  {/if}

  <div class="row">
    <button type="button" class="btn ghost" disabled={!shutters.bridge.connected} onclick={() => shutters.commandAll('open')}>
      Alle auf
    </button>
    <button type="button" class="btn ghost" disabled={!shutters.bridge.connected} onclick={() => shutters.commandAll('close')}>
      Alle zu
    </button>
  </div>

  <div class="cards">
    {#each shutters.shutters as shutter (shutter.id)}
      <ShutterCard {shutter} {onopen} />
    {/each}
  </div>

  <button type="button" class="btn ghost wide" onclick={oncalibration}>Kalibrierung</button>

  <p class="footnote">
    Position ist eine Zeitschätzung, kein Rückmeldewert. Nur die Endlagen sind sicher.
  </p>
</section>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  h1 {
    margin: 0;
    font-family: var(--display);
    font-size: 30px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .sub {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .row {
    display: flex;
    gap: 10px;
  }
  .btn {
    flex: 1 1 0;
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .wide {
    flex: none;
    width: 100%;
  }
  .cards {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .footnote {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--faint);
  }
</style>
