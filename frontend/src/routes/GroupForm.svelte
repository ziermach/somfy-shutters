<script lang="ts">
  // Feature 004: name a set of shutters. The server validates again; this only
  // keeps a person from saving something obviously incomplete.
  import { untrack } from 'svelte';
  import { nextText } from '../lib/automations';
  import { groups } from '../lib/groups.svelte';
  import { shutters } from '../lib/shutters.svelte';
  import type { GroupConflict } from '../lib/types';

  interface Props {
    id?: string;
    onback: () => void;
  }
  let { id, onback }: Props = $props();

  // Read once: a frame arriving while someone edits must not overwrite their typing.
  // App remounts this form (a {#key} block) when it is opened for another group.
  const existing = untrack(() => (id ? groups.byId(id) : undefined));
  let name = $state(existing?.name ?? '');
  let members = $state<string[]>(existing ? [...existing.members] : []);
  let message = $state<string | null>(null);
  let saving = $state(false);
  /** Set after a save that created rule conflicts: shown before leaving (FR-028). */
  let conflicts = $state<GroupConflict[] | null>(null);

  const ready = $derived(name.trim().length > 0 && members.length > 0);

  function nameOf(shutterId: string): string {
    return shutters.byId(shutterId)?.name ?? shutterId;
  }

  function toggle(shutterId: string) {
    members = members.includes(shutterId) ? members.filter((m) => m !== shutterId) : [...members, shutterId];
  }

  function move(index: number, by: -1 | 1) {
    const next = [...members];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    members = next;
  }

  async function save() {
    message = null;
    saving = true;
    const result = await groups.save(name.trim(), members, id);
    saving = false;
    if (!result.ok) {
      message = result.message;
      return;
    }
    if (result.conflicts.length) {
      conflicts = result.conflicts;
      return;
    }
    onback();
  }

  let confirming = $state(false);
  async function remove() {
    if (!id) return;
    const failed = await groups.remove(id);
    if (failed) {
      message = failed;
      confirming = false;
      return;
    }
    onback();
  }
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück ohne Speichern">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <h1>{existing ? 'Gruppe bearbeiten' : 'Neue Gruppe'}</h1>
  </div>

  {#if conflicts}
    <p class="saved">Gespeichert.</p>
    {#each conflicts as c (`${c.rule_id}-${c.other_rule_id}-${c.shutter_id}`)}
      <p class="conflict" role="status">
        Durch diese Änderung treffen „{c.rule_name}“ und „{c.other_rule_name}“ in derselben Minute auf
        {nameOf(c.shutter_id)}{c.via ? ` (über ${c.via})` : ''}, erstmals {nextText({ at: c.first_at, reason: null })}.
        Es gewinnt „{c.winner === c.rule_id ? c.rule_name : c.other_rule_name}“ — sie wird zuletzt ausgeführt.
      </p>
    {/each}
    <button type="button" class="primary" onclick={onback}>Verstanden</button>
  {:else}
    <label class="field">
      <span class="label">Name</span>
      <input type="text" bind:value={name} placeholder="z. B. Obergeschoss" autocomplete="off" maxlength="40" />
    </label>

    <div class="field">
      <span class="label">Rolladen</span>
      <div class="chips">
        {#each shutters.shutters as shutter (shutter.id)}
          <button type="button" class="chip" class:on={members.includes(shutter.id)} aria-pressed={members.includes(shutter.id)} onclick={() => toggle(shutter.id)}>{shutter.name}</button>
        {/each}
      </div>
    </div>

    {#if members.length > 1}
      <div class="field">
        <span class="label">Reihenfolge in der Übersicht</span>
        <ol class="order">
          {#each members as member, i (member)}
            <li>
              <span>{nameOf(member)}</span>
              <button type="button" class="step" disabled={i === 0} onclick={() => move(i, -1)} aria-label="{nameOf(member)} nach oben">↑</button>
              <button type="button" class="step" disabled={i === members.length - 1} onclick={() => move(i, 1)} aria-label="{nameOf(member)} nach unten">↓</button>
            </li>
          {/each}
        </ol>
      </div>
    {/if}

    {#if message}
      <p class="error" role="alert">{message}</p>
    {/if}

    <button type="button" class="primary" disabled={!ready || saving} onclick={save}>Gruppe speichern</button>

    {#if existing}
      <div class="danger">
        {#if confirming}
          <p class="note">Die Rolladen bleiben, wie sie sind. Regeln, die diese Gruppe nutzen, verlieren sie als Ziel.</p>
          <div class="row">
            <button type="button" class="btn danger-btn" onclick={remove}>Wirklich löschen</button>
            <button type="button" class="btn" onclick={() => (confirming = false)}>Abbrechen</button>
          </div>
        {:else}
          <button type="button" class="btn danger-btn" onclick={() => (confirming = true)}>Gruppe löschen</button>
        {/if}
      </div>
    {/if}
  {/if}
</section>

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
    font-size: 24px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .label {
    font-size: 13px;
    color: var(--muted);
  }
  input[type='text'] {
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 0 12px;
    font-size: 15px;
  }
  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .chip {
    border-radius: 9px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--surface-2);
    background: transparent;
    color: var(--faint);
  }
  .chip.on {
    background: var(--amber-soft);
    border-color: var(--amber-line);
    color: var(--amber);
  }
  .order {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .order li {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    border: 1px solid var(--surface-2);
    border-radius: 10px;
    padding: 4px 4px 4px 12px;
  }
  .order li span {
    flex: 1 1 auto;
  }
  .step {
    width: 36px;
    height: 36px;
    border-radius: 9px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
  }
  .step:disabled {
    opacity: 0.3;
  }
  .error,
  .saved {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
  .saved {
    color: var(--muted);
  }
  .conflict {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
    background: var(--amber-soft);
    border: 1px solid var(--amber-line);
    border-radius: 12px;
    padding: 10px 12px;
  }
  .note {
    margin: 0 0 10px;
    font-size: 12px;
    color: var(--faint);
  }
  .primary {
    height: 56px;
    border-radius: 14px;
    border: 1px solid var(--amber);
    background: var(--amber);
    color: var(--ink);
    font-size: 16px;
    font-weight: 600;
  }
  .primary:disabled {
    opacity: 0.5;
  }
  .danger {
    border-top: 1px solid var(--surface-2);
    padding-top: 14px;
  }
  .row {
    display: flex;
    gap: 10px;
  }
  .btn {
    width: 100%;
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
  }
  .danger-btn {
    border-color: var(--amber-line);
    color: var(--amber);
    background: var(--amber-soft);
  }
</style>
