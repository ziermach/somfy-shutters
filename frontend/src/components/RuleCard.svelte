<script lang="ts">
  import { actionText, daysText, groupMembersText, lastText, nextText, targetsText, triggerText, type Rule } from '../lib/automations';
  import { auth } from '../lib/auth.svelte';
  import { automations } from '../lib/automations.svelte';
  import { groups } from '../lib/groups.svelte';
  import FiringHistory from './FiringHistory.svelte';

  interface Props {
    rule: Rule;
    names: Record<string, string>;
    onedit: (id: string) => void;
  }
  let { rule, names, onedit }: Props = $props();

  const last = $derived(lastText(rule.last));
  // A firing inside the pause will not happen; the card should not read as if it will.
  const inPause = $derived(
    automations.state.paused &&
      rule.next.at !== null &&
      (automations.state.until === null || Date.parse(rule.next.at) < Date.parse(automations.state.until))
  );
  let showHistory = $state(false);
  let message = $state<string | null>(null);

  async function skip() {
    message = await automations.patch(rule.id, { skip_next: !rule.skip_next });
  }

  async function toggle() {
    message = await automations.patch(rule.id, { enabled: !rule.enabled });
  }
</script>

<div class="rule" class:off={!rule.enabled}>
  <div class="top">
    <div class="meta">
      <button type="button" class="name" disabled={!auth.can('configure')} onclick={() => onedit(rule.id)}>{rule.name}</button>
      <div class="when">
        <span class="mono">{triggerText(rule.trigger)}</span>
        <span>· {daysText(rule.days)}</span>
      </div>
      <div class="what">{targetsText(rule.targets, names, groups.groups)} → {actionText(rule.action)}</div>
      {#each groupMembersText(rule.targets, names, groups.groups) as line (line)}
        <div class="members">{line}</div>
      {/each}
    </div>
    {#if auth.can('configure')}
      <button
        type="button"
        class="switch"
        role="switch"
        aria-checked={rule.enabled}
        aria-label="{rule.name} ein- oder ausschalten"
        onclick={toggle}
      ></button>
    {/if}
  </div>
  <div class="foot">
    <span class="next" class:none={!rule.next.at}>
      Nächste: {nextText(rule.next)}{#if rule.skip_next}{' '}— wird übersprungen{:else if inPause}{' '}— fällt in die Pause{/if}
      {#if rule.next.at && auth.can('configure')}
        <button type="button" class="skip" onclick={skip}>{rule.skip_next ? 'doch ausführen' : 'überspringen'}</button>
      {/if}
    </span>
    {#if last}
      <button type="button" class="last" onclick={() => (showHistory = !showHistory)}>
        Zuletzt {last} {showHistory ? '▴' : '▾'}
      </button>
    {/if}
  </div>
  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}
  {#if showHistory}
    <FiringHistory ruleId={rule.id} {names} />
  {/if}
</div>

<style>
  .members {
    font-size: 12px;
    color: var(--faint);
  }
  .rule {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .rule.off .meta,
  .rule.off .foot {
    opacity: 0.55;
  }
  .top {
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }
  .meta {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .name {
    all: unset;
    cursor: pointer;
    font-size: 17px;
    font-weight: 600;
    color: var(--text);
  }
  .name:hover {
    color: var(--amber);
  }
  .when {
    display: flex;
    gap: 6px;
    font-size: 13px;
    color: var(--muted);
    flex-wrap: wrap;
  }
  .mono {
    font-family: var(--mono);
  }
  .what {
    font-size: 13px;
    color: var(--faint);
  }
  .switch {
    width: 52px;
    height: 30px;
    flex-shrink: 0;
    border-radius: 15px;
    padding: 2px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    display: flex;
    align-items: center;
    justify-content: flex-start;
  }
  .switch::after {
    content: '';
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--grey-dot);
  }
  .switch[aria-checked='true'] {
    background: var(--amber);
    border-color: var(--amber-line);
    justify-content: flex-end;
  }
  .switch[aria-checked='true']::after {
    background: var(--ink);
  }
  .foot {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
    color: var(--muted);
  }
  .next.none {
    color: var(--amber);
  }
  .skip {
    all: unset;
    cursor: pointer;
    margin-left: 6px;
    text-decoration: underline;
    text-underline-offset: 3px;
    color: var(--muted);
  }
  .last {
    all: unset;
    cursor: pointer;
    color: var(--faint);
  }
  .error {
    margin: 0;
    font-size: 12px;
    color: var(--amber);
  }
</style>
