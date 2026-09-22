<script lang="ts">
  // Feature 008: the one time a device is asked anything. Not a login — nothing to
  // remember, no password. A code read out by someone whose phone is already
  // paired, or printed by `somfy-shutters auth recover` on the Pi.
  import { formatCode, normaliseCode } from '../lib/auth';
  import { auth } from '../lib/auth.svelte';

  interface Props {
    onpaired: () => void;
  }
  let { onpaired }: Props = $props();

  let code = $state('');
  let name = $state('');
  let message = $state<string | null>(null);
  let busy = $state(false);

  const ready = $derived(normaliseCode(code) !== null && name.trim().length > 0);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!ready) return;
    busy = true;
    message = await auth.pair(code, name.trim());
    busy = false;
    if (message === null) onpaired();
  }
</script>

<section class="screen">
  <header>
    <h1>Gerät koppeln</h1>
    <p class="sub">Einmal pro Gerät. Danach fragt die App nicht wieder.</p>
  </header>

  <form onsubmit={submit}>
    <label class="field">
      <span class="label">Kopplungscode</span>
      <input
        class="code"
        type="text"
        inputmode="text"
        autocapitalize="characters"
        autocomplete="one-time-code"
        spellcheck="false"
        placeholder="K7Q-9XM"
        maxlength="7"
        value={code}
        oninput={(e) => (code = formatCode(e.currentTarget.value))}
      />
    </label>

    <label class="field">
      <span class="label">Name dieses Geräts</span>
      <input type="text" bind:value={name} placeholder="z. B. Annas Handy" maxlength="40" autocomplete="off" />
    </label>

    {#if message}
      <p class="error" role="alert">{message}</p>
    {/if}

    <button type="submit" class="primary" disabled={!ready || busy}>Koppeln</button>
  </form>

  <div class="help">
    <p>
      Den Code zeigt ein bereits gekoppeltes Gerät unter <em>Geräte → Gerät koppeln</em>. Ist keines mehr da, auf
      dem Pi <code>somfy-shutters auth recover</code> ausführen.
    </p>
    <p>
      Auf dem iPhone hat eine zum Home-Bildschirm hinzugefügte App eigene Cookies: dort koppeln, nicht vorher in
      Safari.
    </p>
  </div>
</section>

<style>
  .screen {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }
  h1 {
    margin: 0;
    font-family: var(--display);
    font-size: 30px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .sub {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 16px;
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
  input {
    height: 48px;
    border-radius: 12px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    padding: 0 14px;
    font-size: 16px;
  }
  .code {
    font-family: var(--mono);
    font-size: 26px;
    letter-spacing: 0.12em;
    text-align: center;
    height: 60px;
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
  .help {
    font-size: 12px;
    color: var(--faint);
  }
  .help p {
    margin: 0 0 8px;
  }
  code {
    font-family: var(--mono);
    color: var(--muted);
  }
</style>
