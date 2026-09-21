<script lang="ts">
  import { onMount } from 'svelte';
  import { ticker } from './lib/animate';
  import { shutters } from './lib/shutters.svelte';
  import Detail from './routes/Detail.svelte';
  import Overview from './routes/Overview.svelte';

  let openId = $state<string | null>(null);

  onMount(() => {
    shutters.connect();
    // One animation loop for the whole app. Svelte re-reads livePercent() on
    // each frame; nothing is fetched while a shutter travels.
    const stop = ticker(() => shutters.settleArrived());
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

  {#if openId}
    <Detail id={openId} onback={() => (openId = null)} />
  {:else}
    <Overview onopen={(id) => (openId = id)} />
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
