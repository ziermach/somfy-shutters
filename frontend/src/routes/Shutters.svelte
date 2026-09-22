<script lang="ts">
  // Feature 005: every shutter the household has, and everything the bridge knows
  // beyond them — new, set aside, forgotten — in one place (FR-019).
  import { onMount } from 'svelte';
  import { roster } from '../lib/roster.svelte';

  interface Props {
    onback: () => void;
    onadd: () => void;
    onopen: (id: string) => void;
  }
  let { onback, onadd, onopen }: Props = $props();

  onMount(() => roster.watch());

  // Per new shutter: the name being typed, and what went wrong.
  let names = $state<Record<string, string>>({});
  let errors = $state<Record<string, string>>({});
  let renaming = $state<string | null>(null);
  let renameTo = $state('');
  let renameError = $state<string | null>(null);

  const data = $derived(roster.data);
  const household = $derived(data?.active.filter((e) => !e.forgotten) ?? []);
  const forgotten = $derived(data?.active.filter((e) => e.forgotten) ?? []);

  async function confirm(address: string, suggested: string) {
    const result = await roster.confirm(address, names[address] ?? suggested);
    if (result.ok) {
      const { [address]: _done, ...rest } = errors;
      errors = rest;
    } else {
      errors = { ...errors, [address]: result.message };
    }
  }

  function startRename(id: string, name: string) {
    renaming = id;
    renameTo = name;
    renameError = null;
  }

  async function saveRename() {
    if (!renaming) return;
    const result = await roster.rename(renaming, renameTo);
    if (result.ok) renaming = null;
    else renameError = result.message;
  }

  async function restore(address: string) {
    const result = await roster.restore(address);
    if (!result.ok) errors = { ...errors, [address]: result.message };
  }
</script>

<section class="screen">
  <div class="head">
    <button type="button" class="back" onclick={onback} aria-label="Zurück zur Übersicht">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>
    <div>
      <h1>Rolladen</h1>
      <p class="sub">Was im Haus ist, und was die Funkbrücke sonst noch kennt.</p>
    </div>
  </div>

  {#if data === null}
    <p class="empty">Lädt …</p>
  {:else}
    {#if data.new.length}
      <section class="group" aria-label="Neu gefunden">
        <h2>Neuer Rolladen gefunden</h2>
        <p class="note">Die Funkbrücke kennt ihn, im Haus ist er noch nicht. Gib ihm einen Namen.</p>
        {#each data.new as item (item.address)}
          <form class="card new" onsubmit={(e) => { e.preventDefault(); confirm(item.address, item.suggested_name); }}>
            <div class="meta">
              <span class="name">{item.bridge_name}</span>
              <span class="addr">{item.address}</span>
            </div>
            <label class="field">
              <span>Name im Haus</span>
              <input
                maxlength="40"
                value={names[item.address] ?? item.suggested_name}
                oninput={(e) => (names = { ...names, [item.address]: e.currentTarget.value })}
              />
            </label>
            {#if errors[item.address]}
              <p class="error" role="alert">{errors[item.address]}</p>
            {/if}
            <button type="submit" class="primary">Übernehmen</button>
          </form>
        {/each}
      </section>
    {/if}

    {#if forgotten.length}
      <section class="group" aria-label="Unbekannt in der Funkbrücke">
        <h2>Funkbrücke kennt sie nicht mehr</h2>
        <p class="note">
          Nach ihrem letzten Neustart hat die Funkbrücke diese Rolladen nicht mehr gemeldet. Befehle
          gehen nicht mehr raus; die Einstellungen bleiben, bis du sie entfernst.
        </p>
        {#each forgotten as entry (entry.id)}
          <button type="button" class="card row warn" onclick={() => onopen(entry.id)}>
            <span class="name">{entry.name}</span>
            <span class="tag">vergessen</span>
          </button>
        {/each}
      </section>
    {/if}

    <section class="group" aria-label="Im Haus">
      <h2>Im Haus</h2>
      {#each household as entry (entry.id)}
        {#if renaming === entry.id}
          <form class="card new" onsubmit={(e) => { e.preventDefault(); saveRename(); }}>
            <label class="field">
              <span>Neuer Name</span>
              <input maxlength="40" bind:value={renameTo} />
            </label>
            {#if renameError}
              <p class="error" role="alert">{renameError}</p>
            {/if}
            <div class="actions">
              <button type="button" class="ghost" onclick={() => (renaming = null)}>Abbrechen</button>
              <button type="submit" class="primary">Speichern</button>
            </div>
          </form>
        {:else}
          <div class="card row">
            <button type="button" class="open" onclick={() => onopen(entry.id)}>
              <span class="name">{entry.name}</span>
              <span class="origin">{entry.origin === 'config' ? 'von Hand eingetragen' : 'aus der Funkbrücke'}</span>
            </button>
            {#if entry.origin === 'bridge'}
              <button type="button" class="small" onclick={() => startRename(entry.id, entry.name)}>Umbenennen</button>
            {/if}
          </div>
        {/if}
      {:else}
        <p class="empty">Noch kein Rolladen im Haus.</p>
      {/each}
      {#if household.some((e) => e.origin === 'config')}
        <p class="note">
          Von Hand eingetragene Rolladen stehen in <code>config/shutters.toml</code>. Umbenannt oder
          entfernt werden sie dort; die App schreibt diese Datei nie.
        </p>
      {/if}
    </section>

    {#if data.set_aside.length}
      <section class="group" aria-label="Beiseitegelegt">
        <h2>Beiseitegelegt</h2>
        <p class="note">
          Aus dem Haus entfernt, aber die Funkbrücke meldet sie noch. Löschen lassen sie sich nur in
          der Funkbrücke selbst.
        </p>
        {#each data.set_aside as item (item.address)}
          <div class="card row">
            <div class="meta">
              <span class="name">{item.name}</span>
              <span class="addr">{item.address}</span>
            </div>
            <button type="button" class="small" onclick={() => restore(item.address)}>Wieder aufnehmen</button>
          </div>
          {#if errors[item.address]}
            <p class="error" role="alert">{errors[item.address]}</p>
          {/if}
        {/each}
      </section>
    {/if}

    {#if !data.bridge.announcements_seen}
      <p class="note">
        Die Funkbrücke hat noch keinen Rolladen gemeldet. Vielleicht sind die Ankündigungen in
        Pi-Somfy ausgeschaltet (<code>EnableDiscovery</code>).
      </p>
    {/if}

    <button type="button" class="add" onclick={onadd}>+ Rolladen hinzufügen</button>
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
    font-size: 26px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  h2 {
    margin: 0;
    font-family: var(--display);
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .sub {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .card {
    border-radius: 14px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 12px 14px;
  }
  .card.new {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .card.row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    text-align: left;
  }
  .card.warn {
    border-color: var(--amber-line);
    background: var(--amber-soft);
  }
  .open {
    all: unset;
    cursor: pointer;
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .name {
    font-size: 16px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .addr,
  .origin {
    font-size: 12px;
    color: var(--muted);
  }
  .tag {
    font-size: 12px;
    color: var(--amber);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }
  input {
    height: 42px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--bg, transparent);
    color: var(--text);
    padding: 0 12px;
    font-size: 15px;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .primary,
  .ghost {
    flex: 1 1 0;
    height: 42px;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 500;
  }
  .primary {
    border: 1px solid var(--text);
    background: var(--text);
    color: var(--surface);
  }
  .ghost {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
  }
  .small {
    flex-shrink: 0;
    height: 34px;
    padding: 0 12px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
    font-size: 13px;
  }
  .note,
  .empty {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
  code {
    font-size: 12px;
  }
  .add {
    height: 48px;
    border-radius: 14px;
    border: 1px dashed var(--slat-a);
    background: transparent;
    color: var(--muted);
    font-size: 15px;
    font-weight: 500;
  }
</style>
