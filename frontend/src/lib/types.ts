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
  /** Travel shape: 1 is linear. The motor runs linearly in time, not in percent. */
  curve_a: number;
}

export interface Shutter {
  id: string;
  name: string;
  calibrated: boolean;
  travel_up_seconds: number | null;
  travel_down_seconds: number | null;
  position: PositionEstimate;
  movement: Movement | null;
  /** A calibration run is under way; the server refuses commands for it. */
  measuring: boolean;
  /** Feature 005: from config/shutters.toml, or confirmed from the bridge's announcements. */
  origin: 'config' | 'bridge';
  /** The bridge no longer announces it after its last restart; commands are refused. */
  forgotten: boolean;
}

export interface BridgeStatus {
  connected: boolean;
  kind: 'mqtt' | 'sim';
}

/** Feature 004: the household's name for a set of shutters. Owns no state. */
export interface Group {
  id: string;
  name: string;
  /** In display order. Empty only when every member left the configuration. */
  members: string[];
}

/** One shutter's answer to a command sent to several (contracts/rest.md, feature 004). */
export interface CommandResult {
  id: string;
  accepted: boolean;
  movement?: Movement | null;
  error?: 'measurement_in_progress' | 'bridge_unreachable' | 'forgotten';
}

/** A rule conflict a group change created (FR-028): two rules now meet on a shutter. */
export interface GroupConflict {
  rule_id: string;
  rule_name: string;
  other_rule_id: string;
  other_rule_name: string;
  shutter_id: string;
  via: string | null;
  first_at: string;
  winner: string;
}

/** Feature 005: GET /api/roster (contracts/rest.md). */
export interface RosterEntry {
  id: string;
  name: string;
  address: string;
  origin: 'config' | 'bridge';
  forgotten: boolean;
  removable: boolean;
}

export interface NewShutter {
  address: string;
  bridge_name: string;
  /** The bridge's name made unique among the household ("Küche 2"). */
  suggested_name: string;
}

export interface SetAsideShutter {
  address: string;
  name: string;
}

export interface Roster {
  active: RosterEntry[];
  new: NewShutter[];
  set_aside: SetAsideShutter[];
  bridge: { announcements_seen: boolean; web_url: string | null };
}

export interface RosterCounts {
  new: number;
  forgotten: string[];
}

/** GET /api/shutters/{id}/removal: what removing would take with it. */
export interface RemovalPreview {
  removable: boolean;
  groups: { id: string; name: string }[];
  rules: { id: string; name: string; left_without_target: boolean }[];
  calibrated: boolean;
  still_announced: boolean;
  reason: 'configured_by_hand' | 'measurement_in_progress' | null;
}

export interface Snapshot {
  shutters: Shutter[];
  bridge: BridgeStatus;
  groups?: Group[];
  /** Feature 003: pause and clock state, so the overview banner is right at once. */
  automations?: import('./automations').AutomationState;
  /** Feature 005: how many new shutters wait for a name, and which are forgotten. */
  roster?: RosterCounts;
}

export type Frame =
  | { type: 'snapshot'; seq: number; data: Snapshot }
  | { type: 'movement'; seq: number; shutter_id: string; movement: Movement }
  | { type: 'position'; seq: number; shutter_id: string; position: PositionEstimate }
  | { type: 'correction'; seq: number; shutter_id: string; position: PositionEstimate; ease_ms: number }
  | { type: 'bridge'; seq: number; connected: boolean; kind: 'mqtt' | 'sim' }
  | { type: 'measuring'; seq: number; shutter_id: string; active: boolean; direction: 'up' | 'down' | null }
  | ({ type: 'automations'; seq: number } & import('./automations').AutomationState)
  | { type: 'automation_fired'; seq: number; rule_id: string; rule_name: string; planned_at: string; status: string; commanded: number; total: number }
  | { type: 'rules_changed'; seq: number }
  | { type: 'groups'; seq: number; groups: Group[] }
  | ({ type: 'roster'; seq: number } & RosterCounts)
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
