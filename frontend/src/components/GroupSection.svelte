<script lang="ts">
  // Feature 004: one group on the overview — its name, an honest summary of its
  // members, the group's own buttons, and the members' ordinary cards. A group
  // has no position of its own; the summary only counts what the members say.
  import { auth } from '../lib/auth.svelte';
  import { summarize } from '../lib/groups';
  import { shutters } from '../lib/shutters.svelte';
  import type { Action, Group, Shutter } from '../lib/types';
  import ShutterCard from './ShutterCard.svelte';

  interface Props {
    group: Group;
    members: Shutter[];
    collapsed: boolean;
    ontoggle: () => void;
    onopen: (id: string) => void;
  }
  let { group, members, collapsed, ontoggle, onopen }: Props = $props();

  const summary = $derived(summarize(members));
  // Members being measured are refused by the server anyway; they do not count
  // towards "would this button move anything".
  const drivable = $derived(members.filter((m) => !m.measuring));
  const offline = $derived(!shutters.bridge.connected);

  let notice = $state<string | null>(null);
  let positioning = $state(false);
  let target = $state(50);

  async function send(action: Action, percent?: number) {
    notice = await shutters.commandGroup(group.id, action, percent);
    positioning = false;
  }
</script>

<section class="group" aria-label={group.name}>
  <header>
    <button type="button" class="title" onclick={ontoggle} aria-expanded={!collapsed}>
      <svg class="chev" class:closed={collapsed} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M6 9l6 6 6-6" />
      </svg>
      <span class="name">{group.name}</span>
    </button>
    <span class="summary"><span class="dot {summary.tone}"></span>{summary.text}</span>
  </header>

  {#if members.length}
    {#if auth.can('command')}
    <div class="row">
      <button type="button" class="btn" disabled={offline || !drivable.some((m) => shutters.canOpen(m))} onclick={() => send('open')}>auf</button>
      <button type="button" class="btn" disabled={offline || !drivable.some((m) => shutters.canStop(m))} onclick={() => send('stop')}>stop</button>
      <button type="button" class="btn" disabled={offline || !drivable.some((m) => shutters.canClose(m))} onclick={() => send('close')}>zu</button>
      <button type="button" class="btn" disabled={offline || !drivable.length} aria-expanded={positioning} onclick={() => (positioning = !positioning)}>Position…</button>
    </div>
    {/if}

    {#if positioning}
      <div class="sheet">
        <label for="target-{group.id}">Alle auf <span class="mono">{target} %</span></label>
        <input id="target-{group.id}" type="range" min="0" max="100" step="1" bind:value={target} />
        <div class="scale"><span>0 % geschlossen</span><span>100 % offen</span></div>
        <p class="note">Zwischenpositionen sind aus der Laufzeit geschätzt, nicht gemessen.</p>
        <button type="button" class="btn go" disabled={offline} onclick={() => send('position', target)}>Fahren</button>
      </div>
    {/if}

    {#if notice}
      <p class="notice" role="status">{notice}</p>
    {/if}

    {#if !collapsed}
      <div class="cards">
        {#each members as shutter (shutter.id)}
          <ShutterCard {shutter} {onopen} />
        {/each}
      </div>
    {/if}
  {/if}
</section>

<style>
  .group {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }
  .title {
    all: unset;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .name {
    font-family: var(--display);
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chev {
    color: var(--muted);
    flex-shrink: 0;
    transition: transform 0.15s;
  }
  .chev.closed {
    transform: rotate(-90deg);
  }
  .summary {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--grey-dot);
  }
  .dot.sure {
    background: var(--teal);
  }
  .dot.estimated {
    background: var(--amber);
  }
  .row {
    display: flex;
    gap: 8px;
  }
  .btn {
    flex: 1 1 0;
    height: 40px;
    border-radius: 11px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    font-weight: 500;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .sheet {
    display: flex;
    flex-direction: column;
    gap: 8px;
    border: 1px solid var(--surface-2);
    border-radius: 12px;
    padding: 12px;
  }
  .sheet label {
    font-size: 13px;
    color: var(--muted);
  }
  .mono {
    font-family: var(--mono);
    color: var(--text);
  }
  input[type='range'] {
    accent-color: var(--amber);
  }
  .scale {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--faint);
  }
  .note {
    margin: 0;
    font-size: 12px;
    color: var(--faint);
  }
  .go {
    flex: none;
  }
  .notice {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
  .cards {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
</style>
