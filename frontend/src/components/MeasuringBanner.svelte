<script lang="ts">
  // A measurement is the one thing a command would ruin, so the interface says
  // so rather than letting somebody press a button the server will refuse.
  interface Props {
    name: string;
  }
  let { name }: Props = $props();
</script>

<div class="banner" role="status">
  <span class="pulse" aria-hidden="true"></span>
  <span>{name} wird gerade gemessen — solange lässt er sich nicht fahren.</span>
</div>

<style>
  .banner {
    background: var(--amber-soft);
    border: 1px solid var(--amber-line);
    color: var(--amber);
    border-radius: 12px;
    padding: 12px 14px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
    flex-shrink: 0;
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.25;
    }
  }
</style>
