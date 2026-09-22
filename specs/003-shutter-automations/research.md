# Research: Shutter automations

Decisions for [plan.md](./plan.md). Each one answers a question the spec left to the
plan, or a place where the obvious approach would have been wrong.

## 1. What APScheduler does, and what it must not

The constitution fixes APScheduler for time triggers. The obvious use — one
`CronTrigger` per rule — does not survive the spec:

- **Sun rules** change time every day and carry "not before / not after" bounds. A cron
  expression cannot say "sunset −30 min, not after 21:00".
- **Daylight saving** (FR-014) asks for "first valid minute" on spring-forward and "once"
  on fall-back. That has to be a stated, tested rule of ours, not whatever a library
  version happens to do in the gap.
- **No double firing across restarts** (SC-005) and **missed / held / paused records**
  (FR-012, FR-013, FR-020) need state that outlives the process. APScheduler's own job
  store would be a second copy of the rules, able to disagree with the first.

- **Decision**: a pure planner, `next_firing(rule, after, location, tz)`, computes every
  firing time. The engine keeps **one** APScheduler `DateTrigger` job, set to the
  earliest next firing over all enabled rules, and replaced whenever a rule, the pause,
  the location or the clock state changes. When it wakes it calls
  `engine.run_due(now)`, which does all the work. APScheduler is the timer, with an
  in-memory job store; the database is the only record.
- **Why one job, not one per rule**: rules firing in the same minute must run in a fixed
  order (FR-011) and one after another, since they may command the same shutter. One
  wake-up that collects everything due and runs it sequentially gives that for free;
  concurrent per-rule jobs would need a lock and an ordering scheme on top.
- **Dedupe**: every firing is recorded under `UNIQUE(rule_id, planned_at)` *before*
  commands go out. A second attempt at the same planned time — a restart, a clock jump,
  a timer that fires twice — finds the row and does nothing.
- **Testability**: `run_due(now)` takes the time as an argument. Integration tests drive
  it with a fake clock and never start APScheduler; one test checks that the job is set
  to the right instant.
- **Alternatives considered**: `CronTrigger` per rule (fails the three points above); a
  plain asyncio sleep loop without APScheduler (would work, but deviates from the
  constitution for no gain — the single-job use costs nothing); APScheduler 4 (still
  pre-release). **APScheduler 3.11**, `AsyncIOScheduler`.

## 2. Planning a firing time

- **Base date.** A rule belongs to a local calendar date *d*; its weekday selection
  applies to *d*. The firing time is computed on *d* and may fall on the next day (sunset
  +5 h). The list shows the real date and time.
- **Time rule**: local wall time on *d*. If it does not exist (spring-forward gap), the
  first minute after it that does. If it exists twice (fall-back), the first occurrence
  only (`fold=0`). The dedupe key is the UTC instant, so the second occurrence of 02:30
  is a different key — the planner simply never produces it.
- **Sun rule**: sunrise or sunset on *d* at the home location, plus the offset, then
  moved into `[not_before, not_after]` (wall times on *d*). If the sun does not rise or
  set that day, no firing for *d*; the engine records `no_sun` if that day's firing
  would have been due (edge case in the spec; cannot occur in Germany).
- **Search window**: from the day before `after` (a firing on *d−1* can land after
  midnight) through eight days ahead; the earliest candidate strictly after `after` wins.
  A rule with no selected days or no targets has no next firing, with a reason.
- **Offsets** ±360 minutes (FR-002). Bounds only on sun rules.

## 3. Sun times, offline

- **Decision**: `astral` 3.x, `sun.time_at_elevation(observer, −0.833, date, direction)`
  — the standard definition published tables use (refraction plus solar radius).
- **Found during implementation**: astral's own `sunrise()`/`sunset()` use
  `90° + solar radius` and leave the refraction out. Against published times for Berlin
  that is 2.6 minutes late at sunrise and early at sunset — outside FR-018. With the
  elevation given explicitly the worst of eight reference times is 78 s.
- **Verification**: a fixture of published sunrise/sunset times for the configured test
  location on four dates (both solstices, both equinoxes), collected once during
  implementation and committed; the test asserts ±2 min. No network at test time.
- **Timezone**: `general.timezone` in `shutters.toml`, default `Europe/Berlin`, via the
  standard library's `zoneinfo`. The Pi's system timezone is not read — one explicit
  setting beats a surprise after an OS reinstall.

## 4. Home location

- **Decision**: stored in the database, set from the app (FR-016): latitude and
  longitude, with a "use this device's location" button that asks the *phone* (browser
  geolocation). Optional `[location]` in `shutters.toml` seeds it on first start.
- **Why not a place list**: a useful offline list is a data file to maintain; coordinates
  plus the phone's own GPS cover the need with nothing to ship. If geolocation is
  unavailable, typing two numbers still works.
- The location is not sent anywhere. The phone's geolocation may itself use a network
  service on some devices; that is the device's business and optional.

## 5. Knowing when the clock cannot be trusted (FR-013)

The Pi has no battery-backed clock. Raspberry Pi OS restores the last shutdown time at
boot (`fake-hwclock`) and corrects it once NTP answers. Until then the clock is behind,
sometimes by days.

- **Decision**: a `ClockGuard` with two checks, either one enough to hold automations:
  1. **Kernel sync state** on Linux: `adjtimex(2)` via `ctypes`; a return value of
     `TIME_ERROR` means the kernel does not consider the clock synchronised. No
     subprocess, no `timedatectl` parsing.
  2. **Going backwards**: the time is earlier than the last heartbeat the engine wrote
     while the clock *was* reliable (minus a minute of slack). That catches a restored
     stale time even if the kernel state were misreported.
- Checked every 30 s. On non-Linux development machines check 1 reports reliable; the
  simulator exposes `POST /api/sim/clock` to force the state for tests.
- **What happens to firings meanwhile**: nothing is scheduled from an untrusted clock.
  When the clock becomes reliable the engine catches up exactly as after a restart
  (§6), recording what fell into the gap as `held` rather than `missed`, because the
  system was running and the reason was the clock.

## 6. Restarts and missed firings (FR-012)

- A **heartbeat** (`automation.heartbeat`) is written every 60 s while the clock is
  reliable.
- On start, and when the clock becomes reliable again, the engine lists every planned
  firing in `(heartbeat, now]` for each enabled rule (capped at seven days back, so a Pi
  in a drawer for a month does not write a thousand rows):
  - planned within the last 10 minutes and not yet recorded → **carried out now**,
    recorded with both planned and actual time;
  - older → recorded **missed** (system was down) or **held** (system was up, clock was
    not), and not carried out.
- The grace is 10 minutes (spec, FR-012), a named constant.

## 7. One command path

Automations must honour everything a button press honours (FR-009): the measurement
lock, bridge failures, the travel curve, the bridge counter, the WebSocket frames.

- **Decision**: extract `_apply` from `api/rest.py` into `commands.py` as
  `apply(state, shutter_id, action, target_percent)`, raising `MeasurementInProgress`,
  `BridgeUnreachable`, `UnknownShutter`. REST and the engine both call it. This moves
  code without changing it; the existing contract tests are the proof.
- **No queue** (FR-010): a failure is recorded and that is the end of it.

## 8. Conflicts (FR-022)

- On save (and in the form's preview) the server compares the rule with every other
  enabled rule sharing a target shutter, over the next 366 days of planned firings, and
  reports each pair that lands in the same minute with a different action, with the
  first such date and which rule wins by the FR-011 order.
- 366 days because sun rules drift: two rules can coincide only in June. A few rules
  over a year is a few thousand planner calls — milliseconds.

## 9. Retention

Firing records older than 90 days are deleted once a day (FR-021). Deleting a rule
deletes its records; the spec asks for history per rule, and a deleted rule's history
has no screen to live on.

## 10. What is not researched here

Nothing in this feature needs the open hardware questions answered: it issues the same
commands features 001 and 002 issue. The constitution's rule that changes to the command
path are verified on hardware applies to §7's extraction; that verification is part of
the pending hardware tasks, not a blocker for building this.
