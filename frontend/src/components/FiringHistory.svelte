<script lang="ts">
  // What a rule actually did, per shutter, with the reason for every one that did not
  // move. A firing sends commands; whether the shutter arrived nobody can report.
  import { onMount } from 'svelte';
  import { nextText, outcomeText, statusText, viaText, wallTime, type Firing } from '../lib/automations';
  import { automations } from '../lib/automations.svelte';

  interface Props {
    ruleId: string;
    names: Record<string, string>;
  }
  let { ruleId, names }: Props = $props();

  let firings = $state<Firing[] | null>(null);
  onMount(async () => (firings = await automations.firings(ruleId)));
</script>

<div class="history">
  {#if firings === null}
    <p class="muted">lädt …</p>
  {:else if firings.length === 0}
    <p class="muted">Noch nie ausgeführt.</p>
  {:else}
    <ul>
      {#each firings as firing (firing.planned_at)}
        <li>
          <div class="head">
            <span class="mono">{nextText({ at: firing.planned_at, reason: null })}</span>
            {#if firing.fired_at && wallTime(firing.fired_at) !== wallTime(firing.planned_at)}
              <span class="late">ausgeführt {wallTime(firing.fired_at)}</span>
            {/if}
            <span class="status {firing.status}">{statusText(firing.status)}</span>
          </div>
          {#if viaText(firing.outcomes)}
            <div class="via">{viaText(firing.outcomes)}</div>
          {/if}
          {#each firing.outcomes.filter((o) => o.result !== 'commanded') as outcome (outcome.shutter_id)}
            <div class="outcome">{names[outcome.shutter_id] ?? outcome.shutter_id}: {outcomeText(outcome)}</div>
          {/each}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .via {
    font-size: 12px;
    color: var(--faint);
  }
  .history {
    border-top: 1px solid var(--surface-2);
    padding-top: 10px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .head {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 12px;
    color: var(--muted);
  }
  .mono {
    font-family: var(--mono);
  }
  .late {
    color: var(--faint);
  }
  .status {
    margin-left: auto;
  }
  .status.partial,
  .status.failed,
  .status.held,
  .status.missed {
    color: var(--amber);
  }
  .outcome {
    font-size: 12px;
    color: var(--faint);
    padding-left: 8px;
  }
  .muted {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
  }
</style>
