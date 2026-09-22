<script lang="ts">
  // Constitution III made visible: a position always says how much it can be
  // trusted, and how old that trust is. The wording lives in lib/confidence.ts
  // so it can be tested — see calibration, which must not change any of it.
  import { confidenceLabel, tone } from '../lib/confidence';
  import type { PositionEstimate } from '../lib/types';

  interface Props {
    position: PositionEstimate;
  }
  let { position }: Props = $props();
</script>

<span class="badge">
  <span class="dot {tone(position)}"></span>
  <span>{confidenceLabel(position)}</span>
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
  .estimated {
    background: var(--amber);
  }
  .unsure {
    background: var(--grey-dot);
  }
</style>
