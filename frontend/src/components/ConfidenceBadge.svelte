<script lang="ts">
  // Constitution III made visible: a position always says how much it can be
  // trusted, and how old that trust is.
  import type { PositionEstimate } from '../lib/types';

  interface Props {
    position: PositionEstimate;
  }
  let { position }: Props = $props();

  function age(seconds: number | null): string {
    if (seconds === null) return 'nie';
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} Min.`;
    const hours = Math.round(minutes / 60);
    if (hours < 48) return `${hours} Std.`;
    return `${Math.round(hours / 24)} Tagen`;
  }

  const tone = $derived(
    position.confidence === 'certain' ? 'sure' : position.stale || position.confidence === 'unknown' ? 'grey' : 'est'
  );

  const label = $derived(
    position.confidence === 'certain'
      ? 'Endlage · sicher'
      : position.confidence === 'unknown'
        ? 'Position unbekannt'
        : `Schätzung · Sync vor ${age(position.age_seconds)}`
  );
</script>

<span class="badge">
  <span class="dot {tone}"></span>
  <span>{label}</span>
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--grey-dot);
  }
  .sure {
    background: var(--teal);
  }
  .est {
    background: var(--amber);
  }
</style>
