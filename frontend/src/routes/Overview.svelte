<script lang="ts">
  import { auth } from '../lib/auth.svelte';
  import AutomationBanner from '../components/AutomationBanner.svelte';
  import GroupSection from '../components/GroupSection.svelte';
  import MeasuringBanner from '../components/MeasuringBanner.svelte';
  import ShutterCard from '../components/ShutterCard.svelte';
  import { loadView, saveView, sections, type View } from '../lib/groups';
  import { groups } from '../lib/groups.svelte';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    onopen: (id: string) => void;
    oncalibration: () => void;
    onautomations: () => void;
    ongroups: () => void;
    ondevices: () => void;
    onrecord: () => void;
  }
  let { onopen, oncalibration, onautomations, ongroups, ondevices, onrecord }: Props = $props();

  // Per device (FR-014): grouped or flat, and which groups are folded away.
  let view = $state<View>(loadView());
  const hasGroups = $derived(groups.groups.length > 0);
  const grouped = $derived(hasGroups && view.mode !== 'flat');
  const parts = $derived(sections(groups.groups, shutters.shutters));

  function setMode(mode: 'grouped' | 'flat') {
    view = { ...view, mode };
    saveView(view);
  }

  function toggle(groupId: string) {
    const collapsed = view.collapsed.includes(groupId)
      ? view.collapsed.filter((id) => id !== groupId)
      : [...view.collapsed, groupId];
    view = { ...view, collapsed };
    saveView(view);
  }
</script>

<section class="screen">
  <header>
    <h1>Zuhause</h1>
    <p class="sub">{shutters.shutters.length} Rolladen · 100 % = ganz offen</p>
  </header>

  <AutomationBanner />

  {#if shutters.measuring}
    <MeasuringBanner name={shutters.measuring.name} />
  {/if}

  {#if auth.can('command')}
  <div class="row">
    <button type="button" class="btn ghost" disabled={!shutters.bridge.connected || !shutters.shutters.some((s) => !s.measuring && shutters.canOpen(s))} onclick={() => shutters.commandAll('open')}>
      Alle auf
    </button>
    <button type="button" class="btn ghost" disabled={!shutters.bridge.connected || !shutters.shutters.some((s) => !s.measuring && shutters.canClose(s))} onclick={() => shutters.commandAll('close')}>
      Alle zu
    </button>
  </div>
  {/if}

  {#if hasGroups}
    <div class="seg" role="radiogroup" aria-label="Ansicht">
      <button type="button" class="seg-btn" aria-pressed={grouped} onclick={() => setMode('grouped')}>Gruppen</button>
      <button type="button" class="seg-btn" aria-pressed={!grouped} onclick={() => setMode('flat')}>Liste</button>
    </div>
  {/if}

  {#if grouped}
    {#each parts.grouped as part (part.group.id)}
      <GroupSection
        group={part.group}
        members={part.members}
        collapsed={view.collapsed.includes(part.group.id)}
        ontoggle={() => toggle(part.group.id)}
        {onopen}
      />
    {/each}
    {#if parts.ungrouped.length}
      <section class="ungrouped" aria-label="Ohne Gruppe">
        <h2>Ohne Gruppe</h2>
        <div class="cards">
          {#each parts.ungrouped as shutter (shutter.id)}
            <ShutterCard {shutter} {onopen} />
          {/each}
        </div>
      </section>
    {/if}
  {:else}
    <div class="cards">
      {#each shutters.shutters as shutter (shutter.id)}
        <ShutterCard {shutter} {onopen} />
      {/each}
    </div>
    {#if !hasGroups && shutters.shutters.length > 1 && auth.can('configure')}
      <button type="button" class="hint" onclick={ongroups}>Rolladen zu Gruppen zusammenfassen →</button>
    {/if}
  {/if}

  <div class="row">
    <button type="button" class="btn ghost" onclick={ongroups}>Gruppen</button>
    <button type="button" class="btn ghost" onclick={onautomations}>Automationen</button>
    {#if auth.can('calibrate')}
      <button type="button" class="btn ghost" onclick={oncalibration}>Kalibrierung</button>
    {/if}
  </div>
  {#if auth.can('manage')}
    <div class="row">
      <button type="button" class="btn ghost" onclick={ondevices}>Geräte</button>
      <button type="button" class="btn ghost" onclick={onrecord}>Protokoll</button>
    </div>
  {/if}

  <p class="footnote">
    Position ist eine Zeitschätzung, kein Rückmeldewert. Nur die Endlagen sind sicher.
  </p>
</section>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  h1 {
    margin: 0;
    font-family: var(--display);
    font-size: 30px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .sub {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .row {
    display: flex;
    gap: 10px;
  }
  .btn {
    flex: 1 1 0;
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    font-size: 15px;
    font-weight: 500;
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .seg {
    display: flex;
    gap: 6px;
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 12px;
    padding: 4px;
  }
  .seg-btn {
    flex: 1 1 0;
    height: 36px;
    border-radius: 9px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 14px;
    font-weight: 500;
  }
  .seg-btn[aria-pressed='true'] {
    background: var(--surface-2);
    border-color: var(--line);
    color: var(--text);
  }
  .ungrouped {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  h2 {
    margin: 0;
    font-family: var(--display);
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--muted);
  }
  .hint {
    all: unset;
    cursor: pointer;
    align-self: flex-start;
    font-size: 13px;
    color: var(--muted);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .cards {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .footnote {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--faint);
  }
</style>
