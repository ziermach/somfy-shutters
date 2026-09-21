<script lang="ts">
  // The slats cover the part of the window that is closed. `percent` is how
  // open it is, so the covered share is 100 - percent.
  interface Props {
    percent: number | null;
    size?: 'sm' | 'md' | 'lg';
    dim?: boolean;
    unknown?: boolean;
    easeMs?: number;
  }
  let { percent, size = 'sm', dim = false, unknown = false, easeMs = 0 }: Props = $props();

  // An unknown position is drawn half-covered and dashed — never as a number
  // pretending to be a measurement.
  const covered = $derived(percent === null ? 50 : 100 - percent);
</script>

<div class="win {size}" class:dim class:unknown aria-hidden="true">
  <div
    class="slats"
    style:height="{covered}%"
    style:transition-duration={easeMs ? `${easeMs}ms` : null}
  ></div>
</div>

<style>
  .win {
    position: relative;
    overflow: hidden;
    background: var(--window);
    border: 2px solid var(--line);
    border-radius: 6px;
    flex-shrink: 0;
  }
  .slats {
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    background: repeating-linear-gradient(
      180deg,
      var(--slat-a) 0 5px,
      var(--slat-b) 5px 7px
    );
    border-bottom: 2px solid var(--slat-edge);
    transition: height 120ms linear;
  }
  .sm {
    width: 46px;
    height: 58px;
  }
  .md {
    width: 116px;
    height: 150px;
  }
  .lg {
    width: 210px;
    height: 250px;
    border-width: 3px;
    border-radius: 10px;
  }
  .lg .slats {
    background: repeating-linear-gradient(
      180deg,
      var(--slat-a) 0 9px,
      var(--slat-b) 9px 12px
    );
    border-bottom-width: 3px;
  }
  .lg::before {
    content: '';
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--mullion);
    transform: translateX(-50%);
  }
  .dim {
    opacity: 0.5;
  }
  .unknown {
    border-style: dashed;
    border-color: var(--slat-edge);
  }
  .unknown .slats {
    border-bottom-style: dashed;
  }
</style>
