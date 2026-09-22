<script lang="ts">
  // Feature 005, US3: "Rolladen entfernen". One confirmation that names what goes with
  // it (FR-012). Nothing is sent to the bridge (FR-015); the person is told how to
  // delete it there too.
  import { roster } from '../lib/roster.svelte';
  import type { RemovalPreview, Shutter } from '../lib/types';

  interface Props {
    shutter: Shutter;
    onremoved: (setAside: boolean) => void;
  }
  let { shutter, onremoved }: Props = $props();

  let preview = $state<RemovalPreview | null>(null);
  let error = $state<string | null>(null);
  let working = $state(false);

  async function open() {
    error = null;
    const result = await roster.preview(shutter.id);
    if (result.ok) preview = result.value;
    else error = result.message;
  }

  async function remove() {
    working = true;
    const result = await roster.remove(shutter.id);
    working = false;
    if (result.ok) onremoved(result.value.set_aside);
    else error = result.message;
  }
</script>

{#if shutter.origin === 'config'}
  <p class="note">
    Von Hand eingetragen: entfernt wird dieser Rolladen in <code>config/shutters.toml</code>, danach
    die App neu starten.
  </p>
{:else if preview === null}
  <button type="button" class="remove" onclick={open}>Rolladen entfernen</button>
{:else}
  <div class="confirm" role="alertdialog" aria-labelledby="remove-title">
    <strong id="remove-title">{shutter.name} entfernen?</strong>
    {#if !preview.removable}
      <p>
        {preview.reason === 'measurement_in_progress'
          ? 'Für diesen Rolladen läuft gerade eine Messung. Erst beenden oder abbrechen.'
          : 'Dieser Rolladen ist in config/shutters.toml eingetragen und wird dort entfernt.'}
      </p>
      <button type="button" class="ghost" onclick={() => (preview = null)}>Schließen</button>
    {:else}
      <ul>
        {#each preview.groups as group (group.id)}
          <li>verlässt die Gruppe „{group.name}“</li>
        {/each}
        {#each preview.rules as rule (rule.id)}
          <li>
            fällt aus der Automation „{rule.name}“{rule.left_without_target ? ' — sie hat danach keinen Rolladen mehr' : ''}
          </li>
        {/each}
        {#if preview.calibrated}
          <li>gemessene Laufzeiten werden gelöscht</li>
        {/if}
        {#if !preview.groups.length && !preview.rules.length && !preview.calibrated}
          <li>nicht in Gruppen oder Automationen, nichts gemessen</li>
        {/if}
      </ul>
      {#if preview.still_announced}
        <p class="note">
          Die Funkbrücke kennt ihn danach weiterhin; er liegt dann unter „Beiseitegelegt“. Ganz löschen:
          in Pi-Somfy den Rolladen löschen und Pi-Somfy neu starten. Soll auch der Motor die Funkbrücke
          vergessen: Motor mit der alten Fernbedienung in den Anlernmodus bringen (PROG halten, bis er
          wackelt) und in Pi-Somfy bei diesem Rolladen noch einmal „Program“ drücken.
        </p>
      {/if}
      <p class="note">An die Funkbrücke wird nichts gesendet. Fährt er gerade, fährt er zu Ende.</p>
      <div class="actions">
        <button type="button" class="ghost" onclick={() => (preview = null)}>Abbrechen</button>
        <button type="button" class="danger" disabled={working} onclick={remove}>Entfernen</button>
      </div>
    {/if}
  </div>
{/if}
{#if error}
  <p class="error" role="alert">{error}</p>
{/if}

<style>
  .remove {
    all: unset;
    cursor: pointer;
    align-self: flex-start;
    font-size: 14px;
    color: var(--muted);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .confirm {
    display: flex;
    flex-direction: column;
    gap: 10px;
    border-radius: 14px;
    border: 1px solid var(--amber-line);
    background: var(--surface);
    padding: 14px;
  }
  .confirm p,
  .confirm ul {
    margin: 0;
    font-size: 14px;
  }
  .confirm ul {
    padding-left: 18px;
  }
  .note {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .ghost,
  .danger {
    flex: 1 1 0;
    height: 44px;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 500;
  }
  .ghost {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
  }
  .danger {
    border: 1px solid var(--amber-line);
    background: var(--amber-soft);
    color: var(--amber);
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
  code {
    font-size: 12px;
  }
</style>
