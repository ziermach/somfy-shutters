<script lang="ts">
  import { onMount } from 'svelte';
  import RunTable from '../components/RunTable.svelte';
  import { calibration, timesLabel, type DirectionValue } from '../lib/calibration.svelte';
  import { shutters } from '../lib/shutters.svelte';
  import WindowGraphic from '../components/WindowGraphic.svelte';

  interface Props {
    id: string;
    onback: () => void;
  }
  let { id, onback }: Props = $props();

  onMount(() => {
    calibration.loadDetail(id);
  });

  const detail = $derived(calibration.detail);
  const shutter = $derived(shutters.byId(id));
  const live = $derived(shutter ? shutters.livePercent(shutter) : null);
  const running = $derived(calibration.phase !== 'idle');

  // One button that carries the whole flow, so there is never a choice to get
  // wrong while watching a window rather than the screen.
  const buttonLabel = $derived(
    calibration.phase === 'waiting_for_movement'
      ? 'Bewegt sich!'
      : calibration.phase === 'timing'
        ? calibration.direction === 'up'
          ? 'Fertig — oben angekommen'
          : 'Fertig — unten angekommen'
        : calibration.needsHoming
          ? calibration.homingTarget === 100
            ? 'Erst ganz öffnen (kein Messlauf)'
            : 'Erst ganz schließen (kein Messlauf)'
          : 'Fahrt starten'
  );

  async function primary() {
    if (calibration.phase === 'waiting_for_movement') return calibration.mark(id, 'moving');
    if (calibration.phase === 'timing') return calibration.mark(id, 'arrived');
    if (calibration.needsHoming) return calibration.home(id);
    return calibration.start(id);
  }

  function seconds(value: DirectionValue): string {
    return value.source === 'default' ? 'nicht gemessen' : `${value.travel_seconds.toFixed(2)} s`;
  }

  function sourceLabel(value: DirectionValue): string {
    return value.source === 'manual' ? 'von Hand' : value.source === 'measured' ? 'gemessen' : 'geraten';
  }

  const rows = $derived<{ label: string; value: DirectionValue }[]>(
    detail ? [
      { label: 'auf', value: detail.up },
      { label: 'zu', value: detail.down }
    ] : []
  );
</script>

{#if detail}
  <section class="screen">
    <div class="head">
      <button type="button" class="back" onclick={onback} disabled={running} aria-label="Zurück zur Liste">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <div>
        <h1>{detail.name}</h1>
        <p class="sub">{timesLabel(detail)}</p>
      </div>
    </div>

    <div class="stage">
      <WindowGraphic
        percent={live}
        size="md"
        unknown={shutter?.position.confidence === 'unknown'}
      />
      <div class="side">
        <div class="clock">{calibration.elapsed.toFixed(2)} s</div>
        <p class="status" role="status" aria-live="polite">
          {calibration.message ||
            'Die Messung beginnt an einer Endlage. Zwei Knopfdrücke: einmal wenn er sich bewegt, einmal wenn er steht.'}
        </p>
      </div>
    </div>

    <button type="button" class="primary" class:armed={running} disabled={calibration.busy} onclick={primary}>
      {buttonLabel}
    </button>

    <div class="secondary">
      <button type="button" class="btn" disabled={!running} onclick={() => calibration.abort(id)}>
        Abbrechen
      </button>
      <button type="button" class="btn" disabled={running} onclick={() => calibration.clear(id)}>
        Messungen verwerfen
      </button>
    </div>

    <div class="panel">
      <h3>Gespeicherte Werte</h3>
      <table>
        <thead><tr><th>Richtung</th><th>Totzeit</th><th>Gesamt</th><th>Läufe</th><th>Quelle</th></tr></thead>
        <tbody>
          {#each rows as row (row.label)}
            <tr>
              <td>{row.label}</td>
              <td>{row.value.source === 'default' ? '—' : row.value.dead_seconds.toFixed(2)}</td>
              <td>{seconds(row.value)}</td>
              <td>{row.value.runs}</td>
              <td class="source">{sourceLabel(row.value)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if detail.up.source === 'manual' || detail.down.source === 'manual'}
        <p class="override">
          Für diesen Rolladen steht eine Laufzeit in <code>shutters.toml</code>. Die gilt, auch
          wenn hier gemessen wird — Messungen überschreiben nichts, was du selbst eingetragen hast.
        </p>
      {/if}
    </div>

    {#if detail.up.source !== 'default' || detail.down.source !== 'default'}
      <div class="panel">
        <h3>Prüfen</h3>
        <p class="hint">
          Zwei Knopfdrücke können nicht erfassen, dass der Motor ungleichmäßig fährt — in
          der Mitte bleibt ein Rest. Hier fährt er auf die angezeigte Mitte und du sagst,
          was du siehst. Die Endlagen bleiben davon unberührt.
        </p>
        {#if calibration.checking}
          <div class="answers">
            <button type="button" class="btn" onclick={() => calibration.answerCheck(id, 'too_high')}>
              zu hoch
            </button>
            <button type="button" class="btn" onclick={() => calibration.answerCheck(id, 'about_right')}>
              passt
            </button>
            <button type="button" class="btn" onclick={() => calibration.answerCheck(id, 'too_low')}>
              zu tief
            </button>
          </div>
        {:else}
          <button type="button" class="btn wide" disabled={running || calibration.busy} onclick={() => calibration.startCheck(id)}>
            Auf die Mitte fahren
          </button>
        {/if}
        {#if detail.up.curve_k !== 0 || detail.down.curve_k !== 0}
          <button type="button" class="btn wide undo" disabled={running} onclick={() => calibration.undoCheck(id)}>
            Prüfungen zurücknehmen
          </button>
        {/if}
      </div>
    {/if}

    <RunTable runs={detail.runs} />

    <p class="note">
      Kalibriert heißt nicht bekannt: zwischen den Endlagen bleibt die Position eine
      Schätzung, egal wie gut die Laufzeit gemessen ist.
    </p>
  </section>
{/if}

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 14px;
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
  .back:disabled {
    opacity: 0.4;
    cursor: default;
  }
  h1 {
    margin: 0;
    font-family: var(--display);
    font-size: 24px;
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
    gap: 16px;
    align-items: center;
  }
  .side {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .clock {
    font-family: var(--mono);
    font-size: 30px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .status {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
    min-height: 4.2em;
  }
  .primary {
    height: 60px;
    border-radius: 14px;
    font-size: 16px;
    font-weight: 600;
    border: 1px solid var(--line);
    background: var(--surface-2);
    color: var(--text);
    width: 100%;
  }
  .primary.armed {
    background: var(--amber);
    border-color: var(--amber);
    color: var(--ink);
  }
  .primary:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .secondary {
    display: flex;
    gap: 10px;
  }
  .btn {
    flex: 1 1 0;
    height: 38px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    color: var(--text);
    font-size: 13px;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .panel {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
  }
  .panel h3 {
    margin: 0 0 10px;
    font-size: 13px;
    font-weight: 600;
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
    font-family: var(--body);
  }
  td {
    text-align: right;
    padding: 5px 0 5px 8px;
    border-top: 1px solid var(--surface-2);
  }
  .source {
    font-family: var(--body);
  }
  .hint {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
  }
  .answers {
    display: flex;
    gap: 8px;
  }
  .answers .btn {
    height: 44px;
    font-size: 14px;
  }
  .wide {
    flex: none;
    width: 100%;
    height: 44px;
  }
  .undo {
    margin-top: 8px;
    background: transparent;
    color: var(--muted);
  }
  .override {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--amber);
    line-height: 1.5;
  }
  .override code {
    font-family: var(--mono);
  }
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
    line-height: 1.5;
  }
</style>
