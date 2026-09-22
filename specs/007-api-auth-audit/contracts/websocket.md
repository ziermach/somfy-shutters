# WebSocket contract: API authentication and audit

Changes to `GET /api/ws` from features 001–004.

## Opening

The upgrade request must carry the `sst` cookie (the browser sends it by itself) or an
`Authorization: Bearer` header, and — when authenticated by cookie — an `Origin` equal to
the server's own. The credential needs `watch`.

On any failure the server **accepts and immediately closes** the socket with code
**`4401`** and reason `"unauthorized"`, before any frame — no snapshot, no state
(user story 1, scenario 3). Accept-then-close is used because browsers do not expose an
HTTP status of a refused upgrade to script, and the app needs to tell "not paired" from
"backend down" to show the pairing screen rather than the offline banner.

A throttled source is closed with **`4429`**.

## While open

| Event | Close code | When |
|---|---|---|
| credential revoked | `4401` | at once (FR-005) |
| credential expired | `4401` | within 30 s |

The client treats `4401` as "show the pairing screen, do not reconnect" and `4429` as
"reconnect after the backoff". Any other close keeps the existing reconnect with backoff.

## Frames

Unchanged. No frame carries credential data. A client with `watch` only receives the
same frames as the owner's: the live state is the house's, not the credential's.
