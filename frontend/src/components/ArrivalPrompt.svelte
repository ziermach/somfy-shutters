<script lang="ts">
  // One question, one tap. The app cannot tell whether the shutter arrived —
  // nothing in the system observes that — so it asks instead of assuming, and
  // records nothing at all if the question goes unanswered.
  interface Props {
    name: string;
    onconfirm: () => void;
    ondismiss: () => void;
  }
  let { name, onconfirm, ondismiss }: Props = $props();
</script>

<div class="prompt" role="status">
  <span class="text">{name} sollte jetzt angekommen sein. Stimmt das?</span>
  <div class="answers">
    <button type="button" class="yes" onclick={onconfirm}>Ja</button>
    <button type="button" class="no" onclick={ondismiss}>Noch nicht</button>
  </div>
</div>

<style>
  .prompt {
    background: var(--amber-soft);
    border: 1px solid var(--amber-line);
    border-radius: 14px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .text {
    font-size: 13px;
    color: var(--text);
  }
  .answers {
    display: flex;
    gap: 8px;
  }
  button {
    flex: 1 1 0;
    height: 40px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    border: 1px solid var(--amber-line);
  }
  .yes {
    background: var(--amber);
    color: var(--ink);
    font-weight: 600;
  }
  .no {
    background: transparent;
    color: var(--muted);
    border-color: var(--line);
  }
</style>
