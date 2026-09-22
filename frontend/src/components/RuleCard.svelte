<script lang="ts">
  import { actionText, daysText, lastText, nextText, targetsText, triggerText, type Rule } from '../lib/automations';

  interface Props {
    rule: Rule;
    names: Record<string, string>;
    onedit: (id: string) => void;
  }
  let { rule, names, onedit }: Props = $props();

  const last = $derived(lastText(rule.last));
</script>

<div class="rule" class:off={!rule.enabled}>
  <div class="top">
    <div class="meta">
      <button type="button" class="name" onclick={() => onedit(rule.id)}>{rule.name}</button>
      <div class="when">
        <span class="mono">{triggerText(rule.trigger)}</span>
        <span>· {daysText(rule.days)}</span>
      </div>
      <div class="what">{targetsText(rule.targets, names)} → {actionText(rule.action)}</div>
    </div>
  </div>
  <div class="foot">
    <span class="next" class:none={!rule.next.at}>Nächste: {nextText(rule.next)}</span>
    {#if last}
      <span class="last">Zuletzt {last}</span>
    {/if}
  </div>
</div>

<style>
  .rule {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .rule.off {
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
  .last {
    color: var(--faint);
  }
</style>
