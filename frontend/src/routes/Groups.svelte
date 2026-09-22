<script lang="ts">
  // Feature 004: every group, in the order the overview shows them.
  import { auth } from '../lib/auth.svelte';
  import { groups } from '../lib/groups.svelte';

  interface Props {
    onedit: (id?: string) => void;
    onback: () => void;
  }
  let { onedit, onback }: Props = $props();

  let message = $state<string | null>(null);

  async function move(index: number, by: -1 | 1) {
    const ids = groups.groups.map((g) => g.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    message = await groups.reorder(ids);
    // On a refusal the list changed meanwhile; the frame has already brought the
    // current one, so the person sees it and can try again.
  }

  function count(n: number): string {
    return n === 0 ? 'leer' : n === 1 ? '1 Rolladen' : `${n} Rolladen`;
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
      <h1>Gruppen</h1>
      <p class="sub">Ein Rolladen darf in mehreren Gruppen sein.</p>
    </div>
  </div>

  <ol class="list">
    {#each groups.groups as group, i (group.id)}
      <li>
        <button type="button" class="open" disabled={!auth.can('configure')} onclick={() => onedit(group.id)}>
          <span class="name">{group.name}</span>
          <span class="count">{count(group.members.length)}</span>
        </button>
        {#if auth.can('configure')}
          <button type="button" class="step" disabled={i === 0} onclick={() => move(i, -1)} aria-label="{group.name} nach oben">↑</button>
          <button type="button" class="step" disabled={i === groups.groups.length - 1} onclick={() => move(i, 1)} aria-label="{group.name} nach unten">↓</button>
        {/if}
      </li>
    {:else}
      <p class="empty">Noch keine Gruppe. Zum Beispiel ein Raum, eine Etage oder eine Hausseite.</p>
    {/each}
  </ol>

  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}

  {#if auth.can('configure')}
    <button type="button" class="add" onclick={() => onedit()}>+ Neue Gruppe</button>
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
  .sub {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .list li {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .open {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    height: 52px;
    padding: 0 14px;
    border-radius: 14px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    text-align: left;
  }
  .name {
    font-size: 16px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    flex-shrink: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .step {
    width: 40px;
    height: 52px;
    flex-shrink: 0;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
  }
  .step:disabled {
    opacity: 0.3;
  }
  .empty {
    margin: 0;
    font-size: 14px;
    color: var(--faint);
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
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
