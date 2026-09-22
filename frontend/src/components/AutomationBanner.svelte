<script lang="ts">
  // FR-026: when rules will not run, the overview says so — nobody should have to
  // wonder why the shutters stayed shut.
  import { pauseText } from '../lib/automations';
  import { automations } from '../lib/automations.svelte';
</script>

{#if !automations.state.clock_reliable}
  <div class="banner" role="status">
    <span class="dot"></span>
    <span>Uhrzeit unsicher — Automationen angehalten, bis der Pi die Zeit wieder kennt.</span>
  </div>
{:else if automations.state.paused}
  <div class="banner" role="status">
    <span class="dot"></span>
    <span>{pauseText(automations.state.until)}</span>
    <button type="button" class="resume" onclick={() => automations.resume()}>Fortsetzen</button>
  </div>
{/if}

<style>
  .banner {
    background: var(--amber-soft);
    border: 1px solid var(--amber-line);
    color: var(--amber);
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
    flex-shrink: 0;
  }
  .resume {
    margin-left: auto;
    border: 1px solid var(--amber-line);
    background: transparent;
    color: var(--amber);
    border-radius: 9px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 600;
  }
</style>
