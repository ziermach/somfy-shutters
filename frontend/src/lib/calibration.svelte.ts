// The calibration screens' state.
//
// The two presses are the whole measurement, so the client does as little as
// possible with them: it posts, and the server timestamps on arrival. Nothing
// here computes a duration — a clock on a phone is not something a measurement
// should depend on.

export type DirectionValue = { travel_seconds: number; dead_seconds: number; runs: number; curve_a: number; source: 'manual' | 'measured' | 'default'; updated_at: string | null };

export interface CalibrationShutter {
  id: string;
  name: string;
  state: 'calibrated' | 'partial' | 'uncalibrated' | 'manual';
  up: DirectionValue;
  down: DirectionValue;
}

export interface Run {
  id: number;
  direction: 'up' | 'down';
  dead_seconds: number;
  total_seconds: number;
  recorded_at: string;
  kind: 'guided' | 'confirmed';
  rejected: string | null;
}

export interface CalibrationDetail extends CalibrationShutter {
  runs: Run[];
  active_run: { direction: 'up' | 'down'; phase: string; elapsed_seconds: number } | null;
}

export const REJECTION_TEXT: Record<string, string> = {
  dead_after_arrival: 'Bewegung nach der Ankunft gemeldet',
  too_short: 'zu kurz für eine ganze Fahrt',
  implausible: 'weicht zu stark von den anderen ab',
  disturbed: 'währenddessen anderweitig gefahren',
  abandoned: 'kein „Angekommen" gedrückt'
};

type Phase = 'idle' | 'waiting_for_movement' | 'timing';

class CalibrationState {
  shutters = $state<CalibrationShutter[]>([]);
  detail = $state<CalibrationDetail | null>(null);
  phase = $state<Phase>('idle');
  direction = $state<'up' | 'down'>('up');
  startedAt = $state(0);
  elapsed = $state(0);
  message = $state('');
  needsHoming = $state(false);
  homingTarget = $state(100);
  lastRun = $state<Run | null>(null);
  busy = $state(false);
  checking = $state(false);
  atLimit = $state(false);

  #ticker = 0;

  async loadList(): Promise<void> {
    const response = await fetch('/api/calibration');
    this.shutters = (await response.json()).shutters;
  }

  async loadDetail(id: string): Promise<void> {
    const response = await fetch(`/api/calibration/${id}`);
    this.detail = await response.json();
    this.needsHoming = false;
    this.lastRun = null;
    this.phase = 'idle';
  }

  #startTicking(): void {
    this.startedAt = performance.now();
    this.elapsed = 0;
    cancelAnimationFrame(this.#ticker);
    const loop = () => {
      this.elapsed = (performance.now() - this.startedAt) / 1000;
      this.#ticker = requestAnimationFrame(loop);
    };
    this.#ticker = requestAnimationFrame(loop);
  }

  #stopTicking(): void {
    cancelAnimationFrame(this.#ticker);
    this.#ticker = 0;
  }

  async start(id: string): Promise<void> {
    this.busy = true;
    const response = await fetch(`/api/calibration/${id}/run`, { method: 'POST' });
    const body = await response.json();
    this.busy = false;

    if (response.status === 409 && body.error === 'not_at_end_stop') {
      this.needsHoming = true;
      this.homingTarget = body.suggested_target;
      this.message = `Die Messung muss an einer Endlage beginnen. Erst ${body.suggested_target === 100 ? 'ganz öffnen' : 'ganz schließen'}.`;
      return;
    }
    if (!response.ok) {
      this.message = body.message ?? 'Die Messung konnte nicht starten.';
      return;
    }

    this.direction = body.direction;
    this.phase = 'waiting_for_movement';
    this.needsHoming = false;
    this.lastRun = null;
    this.message =
      'Befehl gesendet. Drücken, sobald sich wirklich etwas bewegt — vorher läuft nur der Sanftanlauf.';
    this.#startTicking();
  }

  async home(id: string): Promise<void> {
    this.busy = true;
    const response = await fetch(`/api/calibration/${id}/home`, { method: 'POST' });
    const body = await response.json();
    this.busy = false;
    if (!response.ok) {
      this.message = body.message ?? 'Anfahrt fehlgeschlagen.';
      return;
    }
    this.needsHoming = false;
    this.message = `Fährt an die Endlage bei ${body.target_percent} %. Wird nicht gemessen.`;
  }

  async mark(id: string, which: 'moving' | 'arrived'): Promise<void> {
    const response = await fetch(`/api/calibration/${id}/mark`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mark: which })
    });
    const body = await response.json();
    if (!response.ok) {
      this.message = body.message ?? 'Das hat nicht geklappt.';
      this.phase = 'idle';
      this.#stopTicking();
      return;
    }

    if (which === 'moving') {
      this.phase = 'timing';
      this.message = `Totzeit ${body.dead_seconds.toFixed(2)} s. Jetzt drücken, wenn der Rolladen steht.`;
      return;
    }

    this.#stopTicking();
    this.phase = 'idle';
    this.lastRun = body.run;
    this.message = body.run.rejected
      ? `Lauf verworfen: ${REJECTION_TEXT[body.run.rejected] ?? body.run.rejected}. Nochmal.`
      : `Gespeichert. Nächste Fahrt geht ${body.next_direction === 'up' ? 'zu → auf' : 'auf → zu'}.`;
    await this.loadDetail(id);
  }

  async abort(id: string): Promise<void> {
    await fetch(`/api/calibration/${id}/run`, { method: 'DELETE' });
    this.#stopTicking();
    this.phase = 'idle';
    this.needsHoming = true;
    this.message =
      'Abgebrochen. Der Rolladen steht zwischen den Endlagen — erst wieder anfahren.';
    await this.loadDetail(id);
  }

  // --- verification ---------------------------------------------------------
  //
  // A check adjusts the *shape* of the estimate. It never makes the position
  // better known, and it can never move where the display reaches 0 or 100 —
  // that is guaranteed by the curve, not by anything here.

  async startCheck(id: string): Promise<void> {
    this.busy = true;
    const response = await fetch(`/api/calibration/${id}/check`, { method: 'POST' });
    const body = await response.json();
    this.busy = false;
    if (!response.ok) {
      this.message = body.message ?? 'Prüfung nicht möglich.';
      return;
    }
    this.checking = true;
    this.atLimit = false;
    this.message =
      'Fährt auf die angezeigte Mitte. Wenn er steht: sieht er etwa halb offen aus?';
  }

  async answerCheck(id: string, reply: 'too_high' | 'about_right' | 'too_low'): Promise<void> {
    const response = await fetch(`/api/calibration/${id}/check/answer`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ answer: reply })
    });
    const body = await response.json();
    this.atLimit = body.at_limit;

    if (reply === 'about_right') {
      this.checking = false;
      this.message = 'Passt. Die Mitte der Fahrt stimmt.';
    } else if (body.at_limit) {
      this.message = `Mitte um ${body.shift_pp.toFixed(1)} pp verschoben — weiter geht es nicht. Wenn es immer noch nicht passt, lieber neu messen.`;
    } else {
      this.message = `Mitte um ${body.shift_pp.toFixed(1)} pp verschoben. Nochmal prüfen?`;
    }
    await this.loadDetail(id);
    this.checking = reply !== 'about_right' && !body.at_limit;
  }

  async undoCheck(id: string): Promise<void> {
    await fetch(`/api/calibration/${id}/check`, { method: 'DELETE' });
    this.checking = false;
    this.atLimit = false;
    this.message = 'Prüfungen zurückgenommen. Die gemessenen Laufzeiten bleiben.';
    await this.loadDetail(id);
  }

  async clear(id: string): Promise<void> {
    await fetch(`/api/calibration/${id}`, { method: 'DELETE' });
    this.message = 'Alle Messungen dieses Rolladens verworfen.';
    await this.loadDetail(id);
    await this.loadList();
  }
}

export const calibration = new CalibrationState();

export function stateLabel(shutter: CalibrationShutter): string {
  switch (shutter.state) {
    case 'calibrated':
      return `gemessen, ${shutter.up.runs + shutter.down.runs} Läufe`;
    case 'partial':
      return 'nur eine Richtung gemessen';
    case 'manual':
      return 'von Hand eingetragen';
    default:
      return 'nicht kalibriert';
  }
}

export function timesLabel(shutter: CalibrationShutter): string {
  const fmt = (v: DirectionValue) =>
    v.source === 'default' ? '—' : `${v.travel_seconds.toFixed(1)} s`;
  return `${fmt(shutter.up)} auf · ${fmt(shutter.down)} zu`;
}

/** Which directions a person has overridden by hand, if any.
 *
 * Kept out of the template so it can be tested: "why did my measurement not
 * take effect" is the question this answers, and getting it wrong looks like
 * the app silently ignoring a measurement.
 */
export function overriddenDirections(shutter: CalibrationShutter): ('auf' | 'zu')[] {
  const out: ('auf' | 'zu')[] = [];
  if (shutter.up.source === 'manual') out.push('auf');
  if (shutter.down.source === 'manual') out.push('zu');
  return out;
}

export function overrideNotice(shutter: CalibrationShutter): string | null {
  const directions = overriddenDirections(shutter);
  if (directions.length === 0) return null;
  const which = directions.length === 2 ? 'beide Richtungen' : `die Richtung „${directions[0]}"`;
  const measured = shutter.up.runs + shutter.down.runs;
  const kept =
    measured > 0
      ? ` Die ${measured} gemessenen Läufe bleiben gespeichert und gelten wieder, sobald du den Eintrag entfernst.`
      : '';
  return `Für ${which} steht eine Laufzeit in shutters.toml. Die gilt, auch wenn hier gemessen wird —` +
    ` Messungen überschreiben nichts, was du selbst eingetragen hast.${kept}`;
}
