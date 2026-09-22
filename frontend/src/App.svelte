<script lang="ts">
  import { onMount } from 'svelte';
  import { ticker } from './lib/animate';
  import { shutters } from './lib/shutters.svelte';
  import ArrivalPrompt from './components/ArrivalPrompt.svelte';
  import Calibration from './routes/Calibration.svelte';
  import CalibrationRun from './routes/CalibrationRun.svelte';
  import Detail from './routes/Detail.svelte';
  import Overview from './routes/Overview.svelte';

  type View =
    | { name: 'overview' }
    | { name: 'detail'; id: string }
    | { name: 'calibration' }
    | { name: 'calibrationRun'; id: string };

  let view = $state<View>({ name: 'overview' });

  onMount(() => {
    shutters.connect();
    // One animation loop for the whole app. Svelte re-reads livePercent() on
    // each frame; nothing is fetched while a shutter travels.
    const stop = ticker(() => shutters.tick());
    return () => {
      stop();
      shutters.disconnect();
    };
  });
</script>

<main>
  {#if !shutters.connected}
    <div class="banner offline" role="status">
      Keine Verbindung zum Haus. Die angezeigten Positionen sind nicht aktuell.
    </div>
  {:else if !shutters.bridge.connected}
    <div class="banner" role="status">
      Funkbrücke nicht erreichbar — Rolladen lassen sich gerade nicht fahren.
    </div>
  {/if}

  {#if shutters.confirmable}
    <ArrivalPrompt
      name={shutters.confirmable.name}
      onconfirm={() => shutters.confirmArrival()}
      ondismiss={() => shutters.dismissArrival()}
    />
  {/if}

  {#if view.name === 'detail'}
    <Detail
      id={view.id}
      onback={() => (view = { name: 'overview' })}
      oncalibrate={(id) => (view = { name: 'calibrationRun', id })}
    />
  {:else if view.name === 'calibration'}
    <Calibration
      onopen={(id) => (view = { name: 'calibrationRun', id })}
      onback={() => (view = { name: 'overview' })}
    />
  {:else if view.name === 'calibrationRun'}
    <CalibrationRun id={view.id} onback={() => (view = { name: 'calibration' })} />
  {:else}
    <Overview
      onopen={(id) => (view = { name: 'detail', id })}
      oncalibration={() => (view = { name: 'calibration' })}
    />
  {/if}
</main>

<style>
  main {
    max-width: 480px;
    margin: 0 auto;
    padding: 24px 20px 40px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  .banner {
    background: var(--amber-soft);
    border: 1px solid var(--amber-line);
    color: var(--amber);
    border-radius: 12px;
    padding: 12px 14px;
    font-size: 13px;
  }
  .banner.offline {
    background: var(--surface);
    border-color: var(--line);
    color: var(--muted);
  }
</style>
