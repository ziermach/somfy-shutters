<script lang="ts">
  import { onMount } from 'svelte';
  import { ticker } from './lib/animate';
  import { auth } from './lib/auth.svelte';
  import { shutters } from './lib/shutters.svelte';
  import ArrivalPrompt from './components/ArrivalPrompt.svelte';
  import Automations from './routes/Automations.svelte';
  import RuleForm from './routes/RuleForm.svelte';
  import Calibration from './routes/Calibration.svelte';
  import CalibrationRun from './routes/CalibrationRun.svelte';
  import Detail from './routes/Detail.svelte';
  import GroupForm from './routes/GroupForm.svelte';
  import Groups from './routes/Groups.svelte';
  import Overview from './routes/Overview.svelte';
  import Pair from './routes/Pair.svelte';

  type View =
    | { name: 'overview' }
    | { name: 'detail'; id: string }
    | { name: 'calibration' }
    | { name: 'calibrationRun'; id: string }
    | { name: 'automations' }
    | { name: 'ruleForm'; id?: string }
    | { name: 'groups' }
    | { name: 'groupForm'; id?: string };

  let view = $state<View>({ name: 'overview' });

  onMount(() => {
    auth.install();
    void auth.load();
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
  {#if auth.paired === false}
    <!-- Feature 008: nothing of the house is shown to a device that is not paired. -->
    <Pair
      onpaired={() => {
        view = { name: 'overview' };
        shutters.connect();
      }}
    />
  {:else}
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
  {:else if view.name === 'automations'}
    <Automations
      onedit={(id) => (view = { name: 'ruleForm', id })}
      onback={() => (view = { name: 'overview' })}
    />
  {:else if view.name === 'ruleForm'}
    <RuleForm id={view.id} onback={() => (view = { name: 'automations' })} />
  {:else if view.name === 'groups'}
    <Groups
      onedit={(id) => (view = { name: 'groupForm', id })}
      onback={() => (view = { name: 'overview' })}
    />
  {:else if view.name === 'groupForm'}
    {#key view.id}
      <GroupForm id={view.id} onback={() => (view = { name: 'groups' })} />
    {/key}
  {:else}
    <Overview
      onopen={(id) => (view = { name: 'detail', id })}
      oncalibration={() => (view = { name: 'calibration' })}
      onautomations={() => (view = { name: 'automations' })}
      ongroups={() => (view = { name: 'groups' })}
    />
  {/if}
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
