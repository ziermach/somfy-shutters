# Feature Specification: API authentication and audit

**Feature Branch**: `worktree-007-api-auth`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "API authentication and audit for the backend. Today every REST endpoint and the WebSocket are open: anyone who can reach the backend's port can move the shutters, and nothing records who did."

## User Scenarios & Testing *(mandatory)*

Features 001–004 assume the only people who can reach the app are the people
already standing in the house. That assumption is about to be retired: a later
remote-access feature makes the app reachable from outside the home network, and it cannot start until
this one has landed.

The system currently has no notion of who is asking. Every caller is anonymous and
every caller is fully privileged: the same open port that shows a position can close
every shutter in the house, change measured travel times, or watch the live state of
every room. Nothing anywhere records that it happened.

This feature gives the system that notion, and a memory of what was done with it.

### User Story 1 - Nothing moves without a credential (Priority: P1)

The owner installs the update and finds the app asking for a credential before it
will do anything. Every way into the system — the commands, the live state feed, the
calibration, the configuration — refuses an unidentified caller. A device that has
been given a credential keeps working exactly as before.

**Why this priority**: It is the whole point. Until an unidentified caller is refused,
no other part of this feature matters and remote access is unsafe to begin.

**Independent Test**: Reach the system without a credential and confirm every route
refuses, including the live state feed; then reach it with one and confirm the app is
unchanged in daily use. Delivers a closed front door on its own.

**Acceptance Scenarios**:

1. **Given** a caller with no credential, **When** it asks for the state of the house,
   **Then** the request is refused and no state is disclosed.
2. **Given** a caller with no credential, **When** it attempts to open a shutter,
   **Then** nothing is sent to the shutter layer and the request is refused.
3. **Given** a caller with no credential, **When** it opens the live state feed,
   **Then** the feed is closed before any state is sent.
4. **Given** a caller with a revoked or unrecognised credential, **When** it makes any
   request, **Then** it is refused in the same way as one with no credential, and the
   response does not reveal which of the two it was.
5. **Given** a caller with a valid credential, **When** it uses the app normally,
   **Then** every action behaves as it did before this feature.

---

### User Story 2 - One credential per device, revocable alone (Priority: P1)

The owner hands out a credential per thing that talks to the system: the phone in the
kitchen, a partner's phone, a tablet by the door, later an assistant. Each is named so
they can be told apart. When a phone is lost, its credential is revoked and everything
else keeps working.

**Why this priority**: A single shared secret cannot be revoked without breaking every
device at once, which in practice means it never gets revoked. Per-device credentials
and revocation are one idea and ship together.

**Independent Test**: Issue two credentials, use both, revoke one, and confirm the
revoked one is refused immediately while the other is unaffected.

**Acceptance Scenarios**:

1. **Given** the owner is authenticated, **When** they issue a credential and give it a
   name, **Then** the credential is shown once, in full, and is usable immediately.
2. **Given** an issued credential, **When** the owner looks at the list later, **Then**
   they see its name, when it was created and when it was last used, but never the
   credential itself again.
3. **Given** two active credentials, **When** one is revoked, **Then** its next request
   is refused and the other continues to work without interruption.
4. **Given** a revoked credential, **When** the owner looks at the list, **Then** the
   revocation is visible rather than the entry silently disappearing.
5. **Given** a credential in use by an open live feed, **When** it is revoked, **Then**
   that feed stops within seconds rather than lasting until the client disconnects.

---

### User Story 3 - A credential can do less than everything (Priority: P2)

A phone shortcut that only ever closes the shutters at night does not need the ability
to change measured travel times or hand out new credentials. The owner gives each
credential only the abilities its holder needs, and an attempt to exceed them fails.

**Why this priority**: It limits the damage of a leaked credential, and it is what makes
handing one to an outside integration through remote access defensible. It is worth less than
having any door at all, so it follows P1.

**Independent Test**: Issue a credential limited to watching and commanding, then
attempt a calibration change and an issuance with it and confirm both are refused while
commands still work.

**Acceptance Scenarios**:

1. **Given** a credential limited to reading, **When** it attempts to move a shutter,
   **Then** the attempt is refused and recorded as refused.
2. **Given** a credential limited to reading and commanding, **When** it attempts to
   change a measured travel time or issue another credential, **Then** both are refused.
3. **Given** a credential permitted to issue credentials, **When** it issues one,
   **Then** the new credential cannot be given abilities the issuer does not itself have.
4. **Given** any credential, **When** the owner looks at the list, **Then** what each one
   is allowed to do is stated in plain language.

---

### User Story 4 - Adding a phone without typing a long secret (Priority: P2)

A partner's phone needs access. The owner opens the app on an already-paired device,
asks for a pairing code, and reads out six characters. The phone enters them, receives
its own credential, and never sees the owner's. The code stops working immediately
afterwards.

**Why this priority**: Without it, every new device means moving a long random string
onto a phone by hand, which people solve by sharing one credential between everybody —
the exact thing user story 2 exists to prevent. It needs credentials to exist first.

**Independent Test**: Mint a code on one device, redeem it on a second, confirm the
second has its own separately revocable credential, and confirm the code is refused on a
third attempt.

**Acceptance Scenarios**:

1. **Given** a credential permitted to manage credentials, **When** the owner asks for a
   pairing code, **Then** a short code is shown together with how long it lasts.
2. **Given** an unused, unexpired code, **When** a new device redeems it, **Then** that
   device receives its own named credential and the code is spent.
3. **Given** a spent or expired code, **When** anything tries to redeem it, **Then** it
   is refused and the attempt is recorded.
4. **Given** a code minted by a credential that cannot change measured values, **When**
   it is redeemed, **Then** the new credential cannot change measured values either.
5. **Given** an outstanding code, **When** the owner cancels it, **Then** it can no
   longer be redeemed.
6. **Given** repeated wrong guesses at a code, **When** they pass the failure threshold,
   **Then** they are throttled like any other failed authentication.

---

### User Story 5 - Explaining a movement afterwards (Priority: P2)

A shutter closes at eleven in the morning and nobody admits to it. The owner opens the
app, looks at the record, and sees which credential asked, what it asked for, when, and
whether the system accepted it.

**Why this priority**: The question "who did that" is the reason to know who is calling
in the first place, and with remote access it stops being hypothetical. It depends on
credentials existing, so it cannot precede them.

**Independent Test**: Command a shutter from two different credentials, then read the
record and confirm both appear, correctly attributed, in order, with their outcome.

**Acceptance Scenarios**:

1. **Given** a command that was accepted, **When** the owner reads the record, **Then**
   it shows which shutter, what was asked, when, which credential asked, and that it
   succeeded.
2. **Given** a command refused for lack of permission, **When** the owner reads the
   record, **Then** the attempt appears, marked refused, with the reason.
3. **Given** a movement that the system inferred rather than commanded — a report
   arriving from the shutter layer — **When** the owner reads the record, **Then** it is
   distinguishable from a command the app itself sent.
4. **Given** a revoked credential, **When** the owner reads the record, **Then** its past
   entries remain attributed to it and readable.
5. **Given** a long-running installation, **When** the record grows, **Then** old entries
   are discarded on a stated schedule rather than filling the disk.

---

### User Story 6 - Getting back in after losing everything (Priority: P2)

Every credential is lost — the phone died, nothing was written down. The owner walks to
the Pi, is physically present at it, and recovers access without reinstalling the
system or losing the house's measured values.

**Why this priority**: A door with no key of last resort eventually locks the owner out
of their own shutters. It is not needed daily, which is why it is not P1.

**Independent Test**: Revoke every credential, then recover access using only physical
access to the machine, and confirm the measured travel times and the record survived.

**Acceptance Scenarios**:

1. **Given** no usable credential exists, **When** the owner performs the documented
   recovery while physically at the machine, **Then** a new credential is produced.
2. **Given** the recovery has been performed, **When** the owner looks at the record,
   **Then** the recovery itself appears in it.
3. **Given** recovery requires physical presence, **When** it is attempted over the
   network, **Then** it is refused.
4. **Given** recovery has completed, **When** the owner opens the app, **Then** the
   configured shutters, measured travel times and history are all intact.

---

### User Story 7 - Guessing and flooding are throttled (Priority: P3)

Someone tries credentials in bulk against the system, or a broken client sends a
hundred commands a second. Both are slowed to the point of pointlessness, and the owner
can see it happened.

**Why this priority**: It converts a weak credential from a certainty into a long shot,
and it protects the shutter layer from a runaway client. It is a hardening measure on
top of a door that already exists.

**Independent Test**: Make repeated failed attempts and confirm they are progressively
refused; then flood commands with a valid credential and confirm they are throttled
without the service becoming unusable for other credentials.

**Acceptance Scenarios**:

1. **Given** repeated failed authentication from one source, **When** the failures pass a
   stated threshold, **Then** further attempts from it are refused for a stated period.
2. **Given** a throttled source, **When** a different credential makes a valid request,
   **Then** it is unaffected.
3. **Given** a valid credential sending commands far faster than a person could,
   **When** the rate passes a stated threshold, **Then** the excess is refused and
   recorded rather than passed to the shutter layer.
4. **Given** throttling has occurred, **When** the owner reads the record, **Then** it is
   visible there.

---

### Edge Cases

- A credential is revoked while a shutter it commanded is mid-travel: the movement
  completes; revocation stops new commands, it does not stop a motor.
- The live feed is open and the credential expires or is revoked mid-session: the feed
  closes rather than continuing to stream state.
- The owner issues a credential and never records it: the value is unrecoverable and
  the only remedy is to issue another and revoke the lost one.
- The system clock jumps (a Pi with no battery-backed clock catching up over the
  network): the record must stay readable and ordered, and throttling must not lock the
  owner out for an implausible period.
- Two clients use the same credential at once: permitted, but the record cannot tell
  them apart, and the owner is not led to believe otherwise.
- Every credential is revoked from within the app, including the last one that could
  issue credentials: recovery by physical presence is the only way back, and the app
  warns before it happens.
- A request arrives with a well-formed but expired credential: refused, and
  distinguishable in the record from an unrecognised one.
- The record is read while commands are arriving: reading never blocks a command.
- Development against the simulator, where no shutter can be harmed: must remain
  possible without inventing credentials by hand for every run.
- A pairing code is minted and the minting credential is revoked before it is redeemed:
  the code stops working, rather than outliving the authority that created it.
- Two devices race to redeem the same pairing code: exactly one wins and the other is
  refused; no two credentials are ever produced from one code.
- A pairing code is read aloud within earshot of someone outside the household: it is
  short-lived and single-use, and the owner can cancel it before it is redeemed.
- An installation is started with the simulator exemption enabled but real shutters
  configured: it must refuse to start rather than silently run open.

## Requirements *(mandatory)*

### Functional Requirements

**Identifying the caller**

- **FR-001**: The system MUST refuse any request that does not present a valid,
  unrevoked credential, without disclosing state or acting on shutters.
- **FR-002**: The protection MUST cover every route the system exposes, including the
  live state feed, with a stated, minimal list of exceptions (a liveness check that
  reveals nothing about the house, and whatever a browser needs to load the app before
  a person has authenticated).
- **FR-003**: Refusals for an absent, unrecognised, expired and revoked credential MUST
  be indistinguishable to the caller.
- **FR-004**: The system MUST NOT store a credential in a form that allows it to be
  read back, by the owner or by anyone who obtains the stored data.
- **FR-005**: An open live feed whose credential is revoked MUST be closed within a
  stated short period rather than persisting for the life of the connection.

**Managing credentials**

- **FR-006**: The owner MUST be able to issue a credential, give it a human-readable
  name, and see its value exactly once at issuance.
- **FR-007**: The owner MUST be able to list credentials with their name, abilities,
  creation time, last-used time and revocation state — and never their value.
- **FR-008**: The owner MUST be able to revoke a single credential without affecting
  any other, and revocation MUST take effect on the next request.
- **FR-009**: Issuing and revoking MUST work while the system is running, without
  editing files by hand and without a restart.
- **FR-010**: A credential MUST carry a limited set of abilities, at minimum
  distinguishing watching the house, commanding shutters, changing measured values, and
  managing credentials.
- **FR-011**: A credential MUST NOT be able to grant abilities it does not itself hold.
- **FR-012**: A credential MAY carry an expiry, after which it is refused as if revoked.
- **FR-013**: The system MUST warn before an action that would leave no credential
  capable of managing credentials.

**Recording what happened**

- **FR-014**: Every attempt to move a shutter MUST be recorded with the shutter, what
  was asked, the time, the credential that asked, and the outcome — accepted, refused
  for permission, refused for throttling, or failed at the shutter layer.
- **FR-015**: Credential issuance, revocation, and recovery MUST be recorded the same way.
- **FR-016**: Movement the system inferred from the shutter layer MUST be
  distinguishable in the record from movement the system itself commanded.
- **FR-017**: The record MUST remain attributed and readable after the credential that
  produced an entry is revoked.
- **FR-018**: The owner MUST be able to read the record from the app, newest first,
  filtered at least by shutter and by credential.
- **FR-019**: The record MUST be discarded on a stated retention schedule, and the
  schedule MUST be configurable.
- **FR-020**: Recording MUST NOT delay or block a command; a failure to record MUST NOT
  prevent a shutter from moving, and MUST itself be visible in the logs.

**Throttling**

- **FR-021**: Repeated failed authentication from one source MUST be refused for a
  stated period after a stated number of failures, and the threshold and period MUST be
  configurable.
- **FR-022**: Throttling one source or credential MUST NOT affect others.
- **FR-023**: Commands from a single credential arriving faster than a stated rate MUST
  be refused rather than forwarded to the shutter layer.
- **FR-024**: Throttling events MUST appear in the record.

**Recovery and continuity**

- **FR-025**: The owner MUST be able to produce a working credential using only
  physical access to the machine the system runs on, without reinstalling it and
  without losing configuration, measured values or the record.
- **FR-026**: Recovery MUST NOT be possible over the network.
- **FR-027**: Upgrading an existing installation MUST NOT destroy configuration,
  measured travel times, stored positions or history.
- **FR-028**: A device MUST present its credential once and stay authenticated until the
  credential is revoked or expires; there is no password and no login screen, and the
  app MUST NOT ask again on reload.
- **FR-029**: A real installation MUST always require a credential. The only exemption
  is the simulated house, and it MUST be impossible to run without authentication while
  real shutters are configured.

**Adding a device**

- **FR-030**: A credential permitted to manage credentials MUST be able to mint a
  short-lived pairing code that a new device exchanges once for its own credential.
- **FR-031**: A pairing code MUST expire after a short stated period and MUST be usable
  exactly once, whether or not the exchange succeeded.
- **FR-032**: The abilities of a credential obtained by pairing MUST be fixed when the
  code is minted and MUST NOT exceed those of the credential that minted it.
- **FR-033**: A pairing code MUST be short enough to read aloud or type on a phone, and
  guessing one MUST be throttled as a failed authentication is.
- **FR-034**: Minting, redeeming and expiring a pairing code MUST appear in the record,
  and the credential it produced MUST be identifiable as having come from pairing.
- **FR-035**: The owner MUST be able to cancel an outstanding pairing code before it is
  used.

### Key Entities

- **Credential**: something a client presents to prove it may act. Has a name, a set of
  abilities, a creation time, a last-used time, an optional expiry, and a revocation
  state. Its secret value exists in full exactly once, at issuance.
- **Ability**: a named permission a credential may hold — watching, commanding,
  changing measured values, managing credentials.
- **Record entry**: one thing that happened. Has a time, an actor (a credential, the
  system itself, or the shutter layer), what was attempted, on which shutter where
  applicable, and the outcome.
- **Pairing code**: a short, short-lived, single-use value that a new device exchanges
  for its own credential. Carries the abilities the new credential will have, an expiry,
  and whether it has been spent or cancelled.
- **Throttle state**: how close a source or credential currently is to being refused,
  and until when.

The plan refines two of these: it adds a fifth ability, *configuring* rules, groups and
location, which features 003 and 004 introduced after this spec was written; and it names
automations, recovery and the simulator as actors of their own ("the system itself"
above). See `plan.md` and `research.md` §3.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller with no credential cannot learn the position of any shutter or
  cause any shutter to move, through any route the system exposes.
- **SC-002**: A lost device is fully cut off in under a minute of the owner's attention,
  with no other device interrupted.
- **SC-003**: For any movement in the last retention window, the owner can say who asked
  for it, and when, in under a minute.
- **SC-004**: Commanding a shutter from the app takes no longer, to a person, than it
  did before this feature.
- **SC-005**: A guessing attack of a thousand attempts an hour has no realistic chance
  of success within a year, and does not degrade the system for legitimate clients.
- **SC-006**: An owner locked out completely is back in control within ten minutes of
  reaching the machine, with configuration, measured values and history intact.
- **SC-007**: Setting up a new phone — reading out a pairing code and redeeming it —
  takes under two minutes and never involves transcribing a long secret by hand.
- **SC-008**: Developing against the simulated house takes no extra setup steps compared
  with today.
- **SC-009**: A real installation cannot be brought up without authentication; the only
  configuration that runs open is the simulated house.

## Assumptions

- Devices are paired by someone already holding an authorised device, in person or over
  a channel they trust; there is no self-service enrolment and no invitation by email.
- The people who hold credentials are trusted adults in one household; there is no
  multi-tenancy, no role hierarchy beyond the abilities above, and no per-shutter
  permissions.
- The owner is technically able and physically present at the machine when recovery is
  needed; recovery may involve a terminal on that machine.
- Transport confidentiality is not this feature's concern. Until a remote-access feature adds it,
  credentials cross the home network in whatever form the existing transport uses, and
  that is accepted for a local-only installation.
- A stolen credential is as good as the device it was on; there is no second factor, and
  none is planned for a household of this size.
- Retention of the record defaults to a bounded window measured in months, not forever;
  the exact default is a plan decision.
- The record is for explaining movements, not for security forensics against a skilled
  attacker with access to the machine.
- A later remote-access feature (reverse proxy, voice control) depends on this feature and
  is out of scope here. Nothing in this spec assumes a particular remote arrangement.
- The existing behaviour of features 001–004 is unchanged for an authenticated
  caller; this feature adds a gate and a ledger, it does not alter how shutters move or
  how positions are estimated.
