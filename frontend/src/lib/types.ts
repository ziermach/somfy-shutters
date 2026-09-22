// Mirrors contracts/rest.md. A position never arrives without its confidence,
// and the type says so — the server enforces the same invariant.

export type Confidence = 'certain' | 'estimated' | 'unknown';

export interface PositionEstimate {
  percent: number | null;
  confidence: Confidence;
  certain_at: string | null;
  age_seconds: number | null;
  stale: boolean;
  source: 'command' | 'report' | 'restored';
}

export interface Movement {
  from_percent: number;
  target_percent: number;
  direction: 'up' | 'down';
  started_at: string;
  expected_arrival: string;
  origin: 'local' | 'external';
}

export interface Shutter {
  id: string;
  name: string;
  calibrated: boolean;
  travel_up_seconds: number | null;
  travel_down_seconds: number | null;
  position: PositionEstimate;
  movement: Movement | null;
}

export interface BridgeStatus {
  connected: boolean;
  kind: 'mqtt' | 'sim';
}

export interface Snapshot {
  shutters: Shutter[];
  bridge: BridgeStatus;
}

export type Frame =
  | { type: 'snapshot'; seq: number; data: Snapshot }
  | { type: 'movement'; seq: number; shutter_id: string; movement: Movement }
  | { type: 'position'; seq: number; shutter_id: string; position: PositionEstimate }
  | { type: 'correction'; seq: number; shutter_id: string; position: PositionEstimate; ease_ms: number }
  | { type: 'bridge'; seq: number; connected: boolean; kind: 'mqtt' | 'sim' }
  | { type: 'confirmable'; seq: number; shutter_id: string; direction: 'up' | 'down'; name: string }
  | {
      type: 'calibration';
      seq: number;
      shutter_id: string;
      direction: 'up' | 'down';
      travel_seconds: number;
      runs: number;
    };

export type Action = 'open' | 'close' | 'stop' | 'position';
