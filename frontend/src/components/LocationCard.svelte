<script lang="ts">
  // Where the house is, for sunrise and sunset. Typed in, or taken from this phone.
  // Nothing is looked up online: the Pi computes the sun itself.
  import { automations } from '../lib/automations.svelte';

  let latitude = $state<number | null>(automations.location?.latitude ?? null);
  let longitude = $state<number | null>(automations.location?.longitude ?? null);
  let message = $state<string | null>(null);
  let editing = $state(false);

  // Browsers only allow geolocation in a secure context; http://<pi>:8000 is not one.
  const canLocate = typeof navigator !== 'undefined' && 'geolocation' in navigator && window.isSecureContext;

  $effect(() => {
    if (!editing && automations.location) {
      latitude = automations.location.latitude;
      longitude = automations.location.longitude;
    }
  });

  async function save() {
    if (latitude === null || longitude === null) {
      message = 'Bitte Breite und Länge eingeben.';
      return;
    }
    message = await automations.setLocation(latitude, longitude);
    if (!message) editing = false;
  }

  function locate() {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        latitude = Math.round(pos.coords.latitude * 100) / 100;
        longitude = Math.round(pos.coords.longitude * 100) / 100;
        editing = true;
      },
      () => (message = 'Standort nicht verfügbar — bitte eintippen.')
    );
  }
</script>

<div class="card">
  <div class="top">
    <span class="title">Standort</span>
    {#if automations.location && !editing}
      <button type="button" class="linkish" onclick={() => (editing = true)}>ändern</button>
    {/if}
  </div>

  {#if automations.location && !editing}
    <p class="line">
      <span class="mono">{automations.location.latitude.toFixed(2)}, {automations.location.longitude.toFixed(2)}</span>
      · heute Sonnenaufgang <span class="mono">{automations.location.sunrise ?? '—'}</span>, Sonnenuntergang
      <span class="mono">{automations.location.sunset ?? '—'}</span>
    </p>
  {:else}
    <p class="line">Für Regeln nach dem Sonnenstand. Die Sonnenzeiten berechnet der Pi selbst, ohne Internet.</p>
    <div class="inputs">
      <label>Breite <input type="number" step="0.01" min="-90" max="90" bind:value={latitude} placeholder="52.52" /></label>
      <label>Länge <input type="number" step="0.01" min="-180" max="180" bind:value={longitude} placeholder="13.40" /></label>
    </div>
    <div class="actions">
      {#if canLocate}
        <button type="button" class="btn" onclick={locate}>Standort dieses Geräts verwenden</button>
      {/if}
      <button type="button" class="btn primary" onclick={save}>Speichern</button>
    </div>
  {/if}
  {#if message}
    <p class="error" role="alert">{message}</p>
  {/if}
</div>

<style>
  .card {
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: 16px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .top {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .title {
    font-size: 15px;
    font-weight: 600;
  }
  .line {
    margin: 0;
    font-size: 13px;
    color: var(--muted);
  }
  .mono {
    font-family: var(--mono);
    color: var(--text);
  }
  .inputs {
    display: flex;
    gap: 10px;
  }
  .inputs label {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
  }
  input {
    height: 40px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--page);
    color: var(--text);
    padding: 0 10px;
    font-size: 15px;
    width: 100%;
  }
  .actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .btn {
    flex: 1 1 auto;
    height: 40px;
    border-radius: 10px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    color: var(--text);
    font-size: 14px;
  }
  .btn.primary {
    background: var(--amber);
    border-color: var(--amber);
    color: var(--ink);
    font-weight: 600;
  }
  .linkish {
    all: unset;
    cursor: pointer;
    font-size: 12px;
    color: var(--muted);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .error {
    margin: 0;
    font-size: 13px;
    color: var(--amber);
  }
</style>
