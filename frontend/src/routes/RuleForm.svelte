<script lang="ts">
  // The rule form, ported from mocks/rolladen-ui.html. The server validates again;
  // this only keeps a person from saving something obviously incomplete.
  import { onMount } from 'svelte';
  import {
    DAY_LABELS,
    EVERY_DAY,
    WEEKDAYS,
    WEEKEND,
    type RuleAction,
    type RuleDraft,
    type Trigger
  } from '../lib/automations';
  import { automations } from '../lib/automations.svelte';
  import { shutters } from '../lib/shutters.svelte';

  interface Props {
    id?: string;
    onback: () => void;
  }
  let { id, onback }: Props = $props();

  const existing = $derived(id ? automations.byId(id) : undefined);

  let name = $state('');
  let days = $state<boolean[]>([...WEEKDAYS]);
  let trigger = $state<Trigger>({ kind: 'time', time: '06:45' });
  let targets = $state<'all' | string[]>('all');
  let action = $state<RuleAction>({ kind: 'open' });
  let enabled = $state(true);
  let message = $state<string | null>(null);
  let saving = $state(false);

  onMount(async () => {
    if (id && !automations.loaded) await automations.load();
    const rule = id ? automations.byId(id) : undefined;
    if (rule) {
      name = rule.name;
      days = [...rule.days];
      trigger = { ...rule.trigger };
      targets = rule.targets === 'all' ? 'all' : [...rule.targets];
      action = { ...rule.action } as RuleAction;
      enabled = rule.enabled;
    }
  });

  const toggleDay = (i: number) => (days = days.map((on, j) => (j === i ? !on : on)));

  function toggleTarget(shutterId: string) {
    const current = targets === 'all' ? shutters.shutters.map((s) => s.id) : targets;
    const next = current.includes(shutterId) ? current.filter((x) => x !== shutterId) : [...current, shutterId];
    targets = next.length === shutters.shutters.length ? 'all' : next;
  }
  const isTarget = (shutterId: string) => targets === 'all' || targets.includes(shutterId);

  function setAction(kind: RuleAction['kind']) {
    action = kind === 'position' ? { kind, percent: action.kind === 'position' ? action.percent : 30 } : { kind };
  }

  const incomplete = $derived(
    !name.trim()
      ? 'Bitte einen Namen eingeben.'
      : targets !== 'all' && targets.length === 0
        ? 'Mindestens einen Rolladen wählen.'
        : null
  );

  async function save() {
    if (incomplete) {
      message = incomplete;
      return;
    }
    saving = true;
    const draft: RuleDraft = { name: name.trim(), enabled, days, trigger, targets, action };
    const result = await automations.save(draft, id);
    saving = false;
    if (!result.ok) {
      message = result.message;
      return;
    }
    onback();
  }

  async function remove() {
    if (!id) return;
    await automations.remove(id);
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
    <h1>{existing ? 'Regel bearbeiten' : 'Neue Regel'}</h1>
  </div>

  <label class="field">
    <span class="label">Name</span>
    <input type="text" bind:value={name} placeholder="z. B. Werktags morgens" autocomplete="off" maxlength="60" />
  </label>

  <div class="field">
    <span class="label">Uhrzeit</span>
    {#if trigger.kind === 'time'}
      <input type="time" bind:value={trigger.time} required />
    {/if}
  </div>

  <div class="field">
    <span class="label">Wochentage</span>
    <div class="chips">
      {#each DAY_LABELS as label, i (label)}
        <button type="button" class="chip" class:on={days[i]} aria-pressed={days[i]} onclick={() => toggleDay(i)}>{label}</button>
      {/each}
    </div>
    <div class="quick">
      <button type="button" class="linkish" onclick={() => (days = [...WEEKDAYS])}>Werktags</button>
      <button type="button" class="linkish" onclick={() => (days = [...WEEKEND])}>Wochenende</button>
      <button type="button" class="linkish" onclick={() => (days = [...EVERY_DAY])}>Alle</button>
    </div>
  </div>

  <div class="field">
    <span class="label">Rolladen</span>
    <div class="chips">
      <button type="button" class="chip" class:on={targets === 'all'} aria-pressed={targets === 'all'} onclick={() => (targets = targets === 'all' ? [] : 'all')}>Alle</button>
      {#each shutters.shutters as shutter (shutter.id)}
        <button type="button" class="chip" class:on={isTarget(shutter.id)} aria-pressed={isTarget(shutter.id)} onclick={() => toggleTarget(shutter.id)}>{shutter.name}</button>
      {/each}
    </div>
  </div>

  <div class="field">
    <span class="label">Aktion</span>
    <div class="seg" role="radiogroup" aria-label="Aktion">
      <button type="button" class="seg-btn" aria-pressed={action.kind === 'open'} onclick={() => setAction('open')}>auf</button>
      <button type="button" class="seg-btn" aria-pressed={action.kind === 'close'} onclick={() => setAction('close')}>zu</button>
      <button type="button" class="seg-btn" aria-pressed={action.kind === 'position'} onclick={() => setAction('position')}>Position</button>
    </div>
  </div>

  {#if action.kind === 'position'}
    <label class="field">
      <span class="label">Zielposition <span class="mono">{action.percent} %</span></span>
      <input type="range" min="0" max="100" step="5" bind:value={action.percent} />
      <span class="note">
        Zwischenpositionen sind eine Zeitschätzung. Nach einer Weile ohne Endlage steht der Rolladen woanders als hier
        eingestellt.
      </span>
    </label>
  {/if}

  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}

  <button type="button" class="primary" disabled={saving} onclick={save}>Regel speichern</button>

  {#if existing}
    <div class="danger">
      <button type="button" class="btn danger-btn" onclick={remove}>Regel löschen</button>
    </div>
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
  input[type='text'],
  input[type='time'] {
    height: 44px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 0 12px;
    font-size: 15px;
  }
  input[type='range'] {
    accent-color: var(--amber);
  }
  .mono {
    font-family: var(--mono);
    color: var(--text);
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
  .quick {
    display: flex;
    gap: 14px;
  }
  .linkish {
    all: unset;
    cursor: pointer;
    font-size: 12px;
    color: var(--muted);
    text-decoration: underline;
    text-underline-offset: 3px;
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
    height: 40px;
    border-radius: 9px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 14px;
    font-weight: 500;
    white-space: nowrap;
  }
  .seg-btn[aria-pressed='true'] {
    background: var(--surface-2);
    border-color: var(--line);
    color: var(--text);
  }
  .note {
    font-size: 12px;
    color: var(--faint);
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
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
