// One store for every view, fed by the WebSocket and by command responses.
//
// The socket is the only way state arrives; commands go over REST. On every
// connect the server sends a full snapshot, so there is no resume logic here
// and no missed-message detection to get wrong.

import { interpolate } from './animate';
import type { Action, BridgeStatus, Frame, Movement, Shutter } from './types';

const BACKOFF_START = 1000;
const BACKOFF_MAX = 30000;

class ShutterState {
  shutters = $state<Shutter[]>([]);
  bridge = $state<BridgeStatus>({ connected: false, kind: 'sim' });
  connected = $state(false);
  /** Set while a correction is easing in, so the graphic glides (FR-017). */
  easing = $state<Record<string, number>>({});

  #socket: WebSocket | null = null;
  #backoff = BACKOFF_START;
  #closing = false;

  byId(id: string): Shutter | undefined {
    return this.shutters.find((s) => s.id === id);
  }

  /** Where a shutter is right now — interpolated locally while it travels. */
  livePercent(shutter: Shutter): number | null {
    if (shutter.movement) return interpolate(shutter.movement);
    return shutter.position.percent;
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
    }
  }

  #patch(id: string, change: (shutter: Shutter) => Shutter): void {
    this.shutters = this.shutters.map((s) => (s.id === id ? change(s) : s));
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

  async resync(id: string): Promise<string | null> {
    const response = await fetch(`/api/shutters/${id}/resync`, { method: 'POST' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return body.message ?? 'Resync fehlgeschlagen.';
    if (body.movement) this.#patch(id, (s) => ({ ...s, movement: body.movement as Movement }));
    return null;
  }
}

export const shutters = new ShutterState();
