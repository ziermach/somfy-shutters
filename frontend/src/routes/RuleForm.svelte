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
    type RuleTargets,
    type Trigger,
    nextText
  } from '../lib/automations';
  import { automations, type Preview } from '../lib/automations.svelte';
  import { groups } from '../lib/groups.svelte';
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
  let targets = $state<RuleTargets>('all');
  let action = $state<RuleAction>({ kind: 'open' });
  let enabled = $state(true);
  let message = $state<string | null>(null);
  let saving = $state(false);

  onMount(async () => {
    if (!automations.loaded) await automations.load();
    const rule = id ? automations.byId(id) : undefined;
    if (rule) {
      name = rule.name;
      days = [...rule.days];
      trigger = { ...rule.trigger };
      if (rule.trigger.kind !== 'time') {
        offsetAbs = Math.abs(rule.trigger.offset_minutes);
        offsetSign = rule.trigger.offset_minutes < 0 ? -1 : 1;
        showBounds = !!(rule.trigger.not_before || rule.trigger.not_after);
      }
      targets = rule.targets === 'all' ? 'all' : { shutters: [...rule.targets.shutters], groups: [...rule.targets.groups] };
      action = { ...rule.action } as RuleAction;
      enabled = rule.enabled;
    }
  });

  // --- trigger ---------------------------------------------------------------

  let lastTime = '06:45';
  let offsetAbs = $state(30);
  let offsetSign = $state<-1 | 1>(-1);
  let showBounds = $state(false);

  function setTrigger(kind: Trigger['kind']) {
    if (trigger.kind === 'time') lastTime = trigger.time;
    if (kind === 'time') {
      trigger = { kind, time: lastTime };
      return;
    }
    const bounds = trigger.kind === 'time' ? { not_before: null, not_after: null } : trigger;
    trigger = { kind, offset_minutes: offsetSign * offsetAbs, not_before: bounds.not_before, not_after: bounds.not_after };
  }

  $effect(() => {
    // keep the stored offset in step with the two controls
    if (trigger.kind !== 'time') trigger.offset_minutes = offsetSign * Math.min(360, Math.max(0, offsetAbs || 0));
  });

  // --- live preview ------------------------------------------------------------

  let preview = $state<Preview | null>(null);
  let previewTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const draft: RuleDraft = { name: name.trim() || 'Vorschau', enabled: true, days: [...days], trigger: cleanTrigger(trigger), targets: copyTargets(targets), action: { ...action } as RuleAction };
    if (noTargets(draft.targets)) return;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(async () => (preview = await automations.preview(draft, id)), 250);
  });

  /** An emptied time field reads as "", which is not a time; the server wants null. */
  function cleanTrigger(t: Trigger): Trigger {
    if (t.kind === 'time') return { ...t };
    return { ...t, not_before: t.not_before || null, not_after: t.not_after || null };
  }

  const noLocation = $derived(trigger.kind !== 'time' && !automations.location);

  const toggleDay = (i: number) => (days = days.map((on, j) => (j === i ? !on : on)));

  // --- targets: "Alle", groups, shutters (feature 004) --------------------------

  const NONE = { shutters: [] as string[], groups: [] as string[] };
  const copyTargets = (t: RuleTargets): RuleTargets => (t === 'all' ? 'all' : { shutters: [...t.shutters], groups: [...t.groups] });
  const noTargets = (t: RuleTargets) => t !== 'all' && t.shutters.length === 0 && t.groups.length === 0;

  function toggleTarget(shutterId: string) {
    const current = targets === 'all' ? { ...NONE, shutters: shutters.shutters.map((s) => s.id) } : targets;
    const next = current.shutters.includes(shutterId)
      ? current.shutters.filter((x) => x !== shutterId)
      : [...current.shutters, shutterId];
    // Every shutter by hand and no group is what "Alle" says, and "Alle" also
    // includes shutters added later — so it becomes that.
    targets = next.length === shutters.shutters.length && current.groups.length === 0 ? 'all' : { ...current, shutters: next };
  }
  function toggleGroup(groupId: string) {
    const current = targets === 'all' ? NONE : targets;
    const next = current.groups.includes(groupId) ? current.groups.filter((x) => x !== groupId) : [...current.groups, groupId];
    targets = { ...current, groups: next };
  }
  const isTarget = (shutterId: string) => targets === 'all' || targets.shutters.includes(shutterId);
  const isGroupTarget = (groupId: string) => targets !== 'all' && targets.groups.includes(groupId);

  /** Who the rule would reach right now, so a group's meaning is visible (US4 scenario 5). */
  const reaches = $derived.by(() => {
    if (targets === 'all') return [];
    const wanted = new Set(targets.shutters);
    for (const gid of targets.groups) for (const m of groups.byId(gid)?.members ?? []) wanted.add(m);
    return shutters.shutters.filter((s) => wanted.has(s.id)).map((s) => s.name);
  });

  function setAction(kind: RuleAction['kind']) {
    action = kind === 'position' ? { kind, percent: action.kind === 'position' ? action.percent : 30 } : { kind };
  }

  const incomplete = $derived(
    !name.trim()
      ? 'Bitte einen Namen eingeben.'
      : noTargets(targets)
        ? 'Mindestens einen Rolladen oder eine Gruppe wählen.'
        : null
  );

  async function save() {
    if (incomplete) {
      message = incomplete;
      return;
    }
    saving = true;
    const draft: RuleDraft = { name: name.trim(), enabled, days, trigger: cleanTrigger(trigger), targets, action };
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
    <span class="label">Auslöser</span>
    <div class="seg" role="radiogroup" aria-label="Auslöser">
      <button type="button" class="seg-btn" aria-pressed={trigger.kind === 'time'} onclick={() => setTrigger('time')}>Uhrzeit</button>
      <button type="button" class="seg-btn" aria-pressed={trigger.kind === 'sunrise'} onclick={() => setTrigger('sunrise')}>Sonnenauf</button>
      <button type="button" class="seg-btn" aria-pressed={trigger.kind === 'sunset'} onclick={() => setTrigger('sunset')}>Sonnenunter</button>
    </div>
  </div>

  {#if trigger.kind === 'time'}
    <label class="field">
      <span class="label">Uhrzeit</span>
      <input type="time" bind:value={trigger.time} required />
    </label>
  {:else}
    <div class="field">
      <span class="label">Versatz</span>
      <div class="inline">
        <input type="number" min="0" max="360" step="5" bind:value={offsetAbs} aria-label="Versatz in Minuten" />
        <span class="unit">Min</span>
        <div class="seg small" role="radiogroup" aria-label="Vor oder nach">
          <button type="button" class="seg-btn" aria-pressed={offsetSign === -1} onclick={() => (offsetSign = -1)}>vorher</button>
          <button type="button" class="seg-btn" aria-pressed={offsetSign === 1} onclick={() => (offsetSign = 1)}>danach</button>
        </div>
      </div>
      {#if noLocation}
        <span class="warn">Für den Sonnenstand braucht die App den Standort des Hauses — unter Automationen → Standort.</span>
      {/if}
      <button type="button" class="linkish" onclick={() => (showBounds = !showBounds)}>
        {showBounds ? 'Zeitfenster ausblenden' : 'Zeitfenster (nicht vor / nicht nach)'}
      </button>
      {#if showBounds}
        <div class="bounds">
          <label>nicht vor <input type="time" bind:value={trigger.not_before} /></label>
          <label>nicht nach <input type="time" bind:value={trigger.not_after} /></label>
        </div>
        <span class="note">Im Juni geht die Sonne vor fünf auf. „Nicht vor 06:30“ hält das Schlafzimmer zu.</span>
      {/if}
    </div>
  {/if}

  {#if preview}
    <p class="preview">
      {#if preview.today}heute {preview.today}{/if}
      {#if preview.next.at}· nächste Ausführung {nextText(preview.next)}{:else if preview.next.reason}· {nextText(preview.next)}{/if}
    </p>
  {/if}

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
      <button type="button" class="chip" class:on={targets === 'all'} aria-pressed={targets === 'all'} onclick={() => (targets = targets === 'all' ? { ...NONE } : 'all')}>Alle</button>
    </div>
    {#if groups.groups.length}
      <div class="chips">
        {#each groups.groups as group (group.id)}
          <button type="button" class="chip group" class:on={isGroupTarget(group.id)} aria-pressed={isGroupTarget(group.id)} onclick={() => toggleGroup(group.id)}>{group.name}</button>
        {/each}
      </div>
    {/if}
    <div class="chips">
      {#each shutters.shutters as shutter (shutter.id)}
        <button type="button" class="chip" class:on={isTarget(shutter.id)} aria-pressed={isTarget(shutter.id)} onclick={() => toggleTarget(shutter.id)}>{shutter.name}</button>
      {/each}
    </div>
    {#if targets !== 'all' && targets.groups.length}
      <span class="note">Betrifft jetzt: {reaches.length ? reaches.join(', ') : 'keinen Rolladen'}. Gruppen gelten, wie sie beim Auslösen sind.</span>
    {/if}
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

  {#each preview?.conflicts ?? [] as conflict (conflict.rule_id)}
    <p class="conflict" role="status">
      Gleiche Minute wie „{conflict.rule_name}“ für {shutters.byId(conflict.shutter_id)?.name ?? conflict.shutter_id}{conflict.via ? ` (über ${conflict.via})` : ''},
      erstmals {nextText({ at: conflict.first_at, reason: null })}. Es gewinnt
      {conflict.winner === conflict.rule_id ? `„${conflict.rule_name}“` : 'diese Regel'} — sie wird zuletzt ausgeführt.
    </p>
  {/each}

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
  input[type='time'],
  input[type='number'] {
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
  .chip.group {
    border-style: dashed;
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
  .inline {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .inline input {
    width: 80px;
  }
  .unit {
    font-size: 13px;
    color: var(--muted);
  }
  .seg.small {
    padding: 3px;
    margin-left: auto;
  }
  .seg.small .seg-btn {
    height: 34px;
    font-size: 13px;
    padding: 0 12px;
    flex: 0 0 auto;
  }
  .bounds {
    display: flex;
    gap: 10px;
  }
  .bounds label {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }
  .warn {
    font-size: 12px;
    color: var(--amber);
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
  .preview {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
    font-family: var(--mono);
  }
  .linkish {
    align-self: flex-start;
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
