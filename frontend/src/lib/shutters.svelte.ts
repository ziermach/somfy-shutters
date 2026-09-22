// One store for every view, fed by the WebSocket and by command responses.
//
// The socket is the only way state arrives; commands go over REST. On every
// connect the server sends a full snapshot, so there is no resume logic here
// and no missed-message detection to get wrong.

import { interpolate } from './animate';
import { automations } from './automations.svelte';
import type { Action, BridgeStatus, Frame, Movement, Shutter } from './types';

const BACKOFF_START = 1000;
const BACKOFF_MAX = 30000;

class ShutterState {
  shutters = $state<Shutter[]>([]);
  bridge = $state<BridgeStatus>({ connected: false, kind: 'sim' });
  connected = $state(false);
  /** Set while a correction is easing in, so the graphic glides (FR-017). */
  easing = $state<Record<string, number>>({});
  /** A finished travel the app would like confirmed — one tap, feature 002. */
  confirmable = $state<{ id: string; name: string } | null>(null);
  /**
   * The animation clock. livePercent() reads it so that Svelte re-derives every
   * frame; reading Date.now() directly is invisible to reactivity, and the
   * graphic froze at the start of every travel until the final frame arrived.
   */
  now = $state(Date.now());

  #socket: WebSocket | null = null;
  #backoff = BACKOFF_START;
  #closing = false;

  /** The shutter being calibrated right now, if any. */
  get measuring(): Shutter | undefined {
    return this.shutters.find((s) => s.measuring);
  }

  byId(id: string): Shutter | undefined {
    return this.shutters.find((s) => s.id === id);
  }

  /** Where a shutter is right now — interpolated locally while it travels. */
  livePercent(shutter: Shutter): number | null {
    if (shutter.movement) return interpolate(shutter.movement, this.now);
    return shutter.position.percent;
  }

  /** Where this shutter is headed or already stands, for disabling pointless buttons. */
  #endsAt(shutter: Shutter): number | null {
    if (shutter.movement) return shutter.movement.target_percent;
    return shutter.position.percent;
  }

  /** "auf" does nothing for a shutter that is open or already opening. */
  canOpen(shutter: Shutter): boolean {
    return this.#endsAt(shutter) !== 100;
  }

  /** "zu" does nothing for a shutter that is closed or already closing. */
  canClose(shutter: Shutter): boolean {
    return this.#endsAt(shutter) !== 0;
  }

  /** "stop" only means something while a travel is under way. */
  canStop(shutter: Shutter): boolean {
    return shutter.movement !== null;
  }

  /** Advance the animation clock; called once per frame. */
  tick(): void {
    // Only while something travels, so an idle page does not re-render at 60 fps.
    if (this.shutters.some((s) => s.movement)) this.now = Date.now();
    this.settleArrived();
  }

  connect(): void {
    this.#closing = false;
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${location.host}/api/ws`);
    this.#socket = socket;

    socket.onopen = () => {
      this.connected = true;
      this.#backoff = BACKOFF_START;
    };
    socket.onmessage = (event) => this.#apply(JSON.parse(event.data) as Frame);
    socket.onclose = () => {
      this.connected = false;
      this.freeze();
      if (!this.#closing) this.#reconnect();
    };
    socket.onerror = () => socket.close();
  }

  disconnect(): void {
    this.#closing = true;
    this.#socket?.close();
  }

  #reconnect(): void {
    // Backoff with jitter, so a backend coming up does not meet every client at once.
    const wait = this.#backoff * (0.7 + Math.random() * 0.6);
    this.#backoff = Math.min(BACKOFF_MAX, this.#backoff * 2);
    setTimeout(() => this.connect(), wait);
  }

  #apply(frame: Frame): void {
    switch (frame.type) {
      case 'snapshot':
        // Replaces everything. A client reconnecting after an hour is in the
        // same position as one that just opened the page.
        this.shutters = frame.data.shutters;
        this.bridge = frame.data.bridge;
        if (frame.data.automations) automations.setState(frame.data.automations);
        break;
      case 'automations':
        automations.setState({
          paused: frame.paused,
          until: frame.until,
          clock_reliable: frame.clock_reliable,
          clock_reason: frame.clock_reason
        });
        break;
      case 'automation_fired':
      case 'rules_changed':
        automations.changed();
        break;
      case 'movement':
        this.#patch(frame.shutter_id, (s) => ({ ...s, movement: frame.movement }));
        break;
      case 'position':
        this.#patch(frame.shutter_id, (s) => ({ ...s, movement: null, position: frame.position }));
        break;
      case 'correction':
        this.easing = { ...this.easing, [frame.shutter_id]: frame.ease_ms };
        this.#patch(frame.shutter_id, (s) => ({ ...s, movement: null, position: frame.position }));
        setTimeout(() => {
          const { [frame.shutter_id]: _gone, ...rest } = this.easing;
          this.easing = rest;
        }, frame.ease_ms);
        break;
      case 'bridge':
        this.bridge = { connected: frame.connected, kind: frame.kind };
        break;
      case 'measuring':
        this.#patch(frame.shutter_id, (s) => ({ ...s, measuring: frame.active }));
        break;
      case 'confirmable':
        this.confirmable = { id: frame.shutter_id, name: frame.name };
        break;
      case 'calibration':
        // A measured travel time changed, so this client must stop animating on
        // the old one. The snapshot carries the new value.
        fetch('/api/shutters')
          .then((r) => r.json())
          .then((data) => {
            this.shutters = data.shutters;
          })
          .catch(() => {});
        break;
    }
  }

  #patch(id: string, change: (shutter: Shutter) => Shutter): void {
    this.shutters = this.shutters.map((s) => (s.id === id ? change(s) : s));
  }

  /**
   * The connection is gone: stop every animation where it stands (contracts/websocket.md,
   * FR-022). Without the server nobody knows whether the travel continued, stopped, or
   * was overridden, so the graphic must not go on pretending. The position stays as an
   * estimate; the snapshot on reconnect replaces it.
   */
  freeze(now: number = Date.now()): void {
    this.shutters = this.shutters.map((s) =>
      s.movement
        ? {
            ...s,
            movement: null,
            position: { ...s.position, percent: interpolate(s.movement, now), confidence: 'estimated', source: 'command' }
          }
        : s
    );
  }

  /** Stop animating a shutter that has arrived, until the server confirms. */
  settleArrived(): void {
    for (const shutter of this.shutters) {
      if (shutter.movement && Date.now() >= Date.parse(shutter.movement.expected_arrival) + 1500) {
        this.#patch(shutter.id, (s) => ({ ...s, movement: null }));
      }
    }
  }

  async command(id: string, action: Action, targetPercent?: number): Promise<string | null> {
    const response = await fetch(`/api/shutters/${id}/command`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action, target_percent: targetPercent ?? null })
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return body.message ?? 'Der Befehl ist fehlgeschlagen.';

    // Animate from the response immediately rather than waiting for the frame;
    // the frame arrives moments later with the same timestamps.
    if (body.movement) {
      this.#patch(id, (s) => ({ ...s, movement: body.movement as Movement }));
    }
    return null;
  }

  async commandAll(action: Action): Promise<string | null> {
    const response = await fetch('/api/shutters/command', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action })
    });
    if (response.status === 503) return 'Kein Rolladen konnte erreicht werden.';
    return null;
  }

  async confirmArrival(): Promise<void> {
    const pending = this.confirmable;
    if (!pending) return;
    this.confirmable = null;
    await fetch(`/api/calibration/${pending.id}/confirm`, { method: 'POST' });
  }

  async dismissArrival(): Promise<void> {
    const pending = this.confirmable;
    if (!pending) return;
    this.confirmable = null;
    await fetch(`/api/calibration/${pending.id}/confirm`, { method: 'DELETE' });
  }

  async resync(id: string): Promise<string | null> {
    const response = await fetch(`/api/shutters/${id}/resync`, { method: 'POST' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return body.message ?? 'Resync fehlgeschlagen.';
    if (body.movement) this.#patch(id, (s) => ({ ...s, movement: body.movement as Movement }));
    return null;
  }
}

export const shutters = new ShutterState();
