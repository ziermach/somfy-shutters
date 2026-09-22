<script lang="ts">
  // Rejected runs stay visible with their reason (FR-012). Hiding them would
  // leave the user wondering why a measurement they just made did nothing.
  import { REJECTION_TEXT, type Run } from '../lib/calibration.svelte';

  interface Props {
    runs: Run[];
  }
  let { runs }: Props = $props();
</script>

<div class="panel">
  <h3>Läufe</h3>
  {#if runs.length === 0}
    <p class="empty">Noch keine Messung.</p>
  {:else}
    <table>
      <thead>
        <tr><th>#</th><th>Richtung</th><th>Totzeit</th><th>Gesamt</th><th>Status</th></tr>
      </thead>
      <tbody>
        {#each runs as run, index (run.id)}
          <tr class:dropped={run.rejected}>
            <td>{index + 1}</td>
            <td>{run.direction === 'up' ? 'auf' : 'zu'}</td>
            <td>{run.dead_seconds.toFixed(2)}</td>
            <td>{run.total_seconds.toFixed(2)}</td>
            <td class="verdict">
              {run.rejected ? (REJECTION_TEXT[run.rejected] ?? run.rejected) : 'gewertet'}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .panel {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
  }
  h3 {
    margin: 0 0 10px;
    font-size: 13px;
    font-weight: 600;
  }
  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--faint);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  th {
    text-align: right;
    font-weight: 500;
    color: var(--faint);
    padding: 0 0 6px 8px;
  }
  th:first-child,
  td:first-child {
    text-align: left;
    padding-left: 0;
  }
  td {
    text-align: right;
    padding: 5px 0 5px 8px;
    border-top: 1px solid var(--surface-2);
  }
  tr.dropped td {
    color: var(--faint);
    text-decoration: line-through;
  }
  tr.dropped .verdict {
    text-decoration: none;
    color: var(--amber);
    font-family: var(--body);
  }
</style>
