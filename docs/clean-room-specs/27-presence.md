# 27. Presence and edit locks

Spec `spec-presence-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Three related live-collaboration capabilities: (1) soft pessimistic edit locks per record with acquire (idempotent for the holder, takeover once expired), heartbeat renewal, release, expiry sweep and project-based access gating; (2) per-record presence rooms that announce who is viewing and relay lock events live; (3) an app-wide presence channel scoped per project that shows teammates in the same project, the page they are on and an active or idle status, with idle detection, keep-alive and reconnection on the client. Also covers an adjacent discussion-comment surface. Numeric durations and limits in this spec are illustrative; the destination chooses its own values.

## Behaviour

- At most one lock exists per (record kind, record id). A lock records holder, acquired time, last renewal time and expiry. The set of lockable record kinds is a fixed allowlist covering the main editable record types of the application; the destination derives the allowlist from its own record catalogue. _(prs-beh-001; observed)_
- Acquire: validates the record kind against the allowlist, then the caller's access to the record's owning project; then (a) no lock: create one expiring after the requested lifetime; (b) caller already holds it, live or lapsed: refresh in place (same lock id, new acquire time, renewal time and expiry), idempotent; (c) another user holds a live lock: conflict, naming the holder, with acquire time, expiry and remaining whole seconds; (d) another user holds an expired lock: it is taken over (old removed, new created for the caller). _(prs-beh-002; observed)_
- Lifetime has a default and a bounded range (illustratively a default of about a minute within a range from seconds to minutes). Success answers created with the lock id, record, holder id and display name, acquired, renewed and expiry times and remaining seconds (floored at zero). Holder display name is full name, else email, else identifier. _(prs-beh-003; observed)_
- Conflict (HTTP 409) body carries a human message naming the holder, holder id and name, acquire time, expiry and remaining seconds. If concurrent contention cannot be resolved after a bounded number of internal attempts, the caller receives a retry-style conflict naming no holder (zero seconds remaining) rather than a false success. _(prs-beh-004; observed)_
- Concurrency: all lock writes are conditional on the state that was read (holder and, for takeover, still-expired), so simultaneous callers never both believe they hold the lock, a holder returning to a lock that someone took over gets a proper conflict naming the new holder, and a lost write never surfaces as a server error. _(prs-beh-005; observed)_
- Heartbeat: extends a lock only when it exists, belongs to the caller and has not yet expired; new expiry is now plus the requested extension (a default within a bounded range, illustratively tens of seconds), replacing the previous expiry (not additive). Otherwise the answer is not-found, telling the client to re-acquire. Caller's access to the record's project is re-verified first so a removed member cannot keep a lock pinned. _(prs-beh-006; observed)_
- Release: only the holder may release; an unknown lock id is a silent success (idempotent); a non-holder is refused as forbidden. A release announcement is published only if a row was actually removed. _(prs-beh-007; observed)_
- Read current holder for a record: after allowlist and access checks, returns the live lock or null; an expired lock reads as free even before the sweep removes it. My-locks lists the caller's live locks (expiry after now). _(prs-beh-008; observed)_
- A lock expires when its expiry time is at or before now. A background sweep on a short interval (illustratively tens of seconds) deletes all expired locks atomically and announces one expiry per removed lock after commit; sweep failures are logged and the loop continues; the sweep starts with the application and is cancelled cleanly at shutdown. Acquire treats an expired lock as takeover-able even before the sweep runs. _(prs-beh-009; observed)_
- Lock lifecycle announcements (acquired, renewed, released, expired) are published after the operation and relayed to every client connected to that record's presence room, carrying lock id, holder id and display name (not for expiry) and the expiry (for acquired and renewed). _(prs-beh-010; observed)_
- Record presence room: a client connects for one record kind and id, authenticates, and must be able to reach the record's owning project. After joining it receives a snapshot (roster of distinct users with display names, the current live lock or none, and a lock-state value of held, free or unknown when the read failed), and the rest of the room is told someone joined. Closing the last tab of a user announces that user left; closing a tab while another tab of the same user remains announces nothing. _(prs-beh-011; observed)_
- When the final connection of a room closes, every user still on the roster is announced as having left (one announcement per user), and the room's state is discarded to bound memory. Broadcasts silently drop connections that fail to receive. Presence is local to the process holding the connections. _(prs-beh-012; observed)_
- Record room keep-alive: a text keep-alive frame is answered; other frames, including binary, are ignored without closing. _(prs-beh-013; observed)_
- Edit-lock client behavior: optional automatic acquire when a record is opened (and re-acquire when the record changes), requesting a lifetime of about a minute; after success a renewal on a fixed interval shorter than the lifetime, extending by more than the interval so one missed renewal does not drop the lock; release on leaving (fire and forget). States: idle, acquiring, held, conflict, released, error. A conflict shows a warning naming the holder and seconds remaining; a network failure on acquire enters error and tells the user they may still edit but changes may conflict; a failed renewal stops renewing, drops the lock and tells the user to save and re-acquire. A failed release is ignored because the sweep will reap it. The client never throws; a broken lock service must still allow read-only viewing. _(prs-beh-014; observed)_
- Record room client: connects when enabled and signed in, sending the access credential as the first frame (never in the address); statuses idle, connecting, open, closed, error; snapshot replaces the roster, join adds a user if absent, leave removes; no automatic reconnect on this channel; observational only. _(prs-beh-015; observed)_
- Indicator badge: shows an editing-by-you label when the holder is the viewer, a locked-by-name label with remaining seconds when someone else holds it, and nothing when no lock is held unless configured to show a viewers count when at least one other person is present. The holder comes from the parent's own lock if given, otherwise only from the last snapshot (so a snapshot with an unknown lock state cannot be told from a free lock). Whether the viewer is the holder is decided by a comparison the destination should base on user identifiers. _(prs-beh-016; observed)_
- App-wide presence: each authenticated tab holds one connection. A tab reports its current page and the project it is working in; it sees exactly the people whose tabs report the same project and is seen only by them. A tab in no project (dashboard, settings, project list) sees nobody and is seen by nobody. A project the user may not open is treated as no project, silently. _(prs-beh-017; observed)_
- A user's roster entry in a project is built only from that user's tabs in that project: display name, the page of their most recently active tab there, status active if any tab there is active else idle, and the earliest connection time. A second tab in another project never leaks its page. _(prs-beh-018; observed)_
- On connect the tab receives an empty roster snapshot. On a page or project report: if the project changed, the old project's room is told the user left (only if that was the user's last tab there, otherwise it receives the user's updated entry), the tab receives the new project's roster, and the new room is told the user joined (if this is their first tab there) or updated; if the project is unchanged, the room is told of an update excluding the sender. A status report (active or idle) updates the entry and is announced to the room excluding the sender; ignored if the tab is in no project or the status is not active/idle. Closing a tab announces leave if it was the user's last tab in that project, else an update. _(prs-beh-019; observed)_
- App-wide channel protocol rules: the first client frame must carry the access credential or the connection is refused; text keep-alive is answered; malformed, non-object or unknown-type messages are ignored; a page report requires a non-empty page text. Project access is checked once per project change and cached for page changes inside the same project. Display name is full name, else the part of the email before the at sign (a full address is not broadcast), else the identifier. _(prs-beh-020; observed)_
- App-wide client: mounted once at the application shell; connects after sign-in; reports page and project immediately after authenticating and whenever either changes; becomes idle after a few minutes without mouse, keyboard or pointer input, or immediately when the browser tab is hidden, and returns to active on the next input or when visible again; sends a keep-alive on a fixed interval of tens of seconds; reconnects after closure with full-jitter exponential backoff (base about a second, doubling, ceiling about half a minute), resetting on a successful open; clears the roster and timers on unmount. If it never connects, nothing is shown. _(prs-beh-021; observed)_
- Wire user normalization: a joined or updated user arrives with fields at the top level (not nested). A user message without a non-empty identifier is dropped without error. Missing name becomes empty, missing page becomes the root, any status other than idle is active, and last-active is the message time, else connection time, else now. _(prs-beh-022; observed)_
- Avatar stack: excludes the viewer (identified from the credential's subject claim; an undecodable credential means nobody is excluded); shows up to a small fixed maximum of initial-based circles, with an overflow pill giving the remaining count; idle users are dimmed and carry a muted status marker, active users an active marker; colour is derived deterministically from the user id from a small fixed palette; initials are first and last name initials, or the first letter, or a generic fallback letter; hidden on small screens and entirely when the channel is not open or nobody else is present. Clicking an avatar toggles its popover. Exact palette, maximum and styling are the destination's choice. _(prs-beh-023; observed)_
- Popover: shows the name, the user's current page as a readable title (from the last non-identifier segment of the page path, via a fixed slug-to-title mapping with title-casing fallback and a translated title when known; root means dashboard), and status text for active, idle, or idle with an elapsed duration in minutes or hours once at least a minute has passed; closes on outside click or Escape. _(prs-beh-024; observed)_
- Discussion comments: a comment attaches to a record, may be a reply to a comment of the same record (reply to a missing parent is not-found, to a different record's comment or a deleted comment is a bad request), may carry mentions and an attached viewpoint. Only the author may edit or delete; editing a deleted comment is a bad request; deleting twice is idempotent; deletion is soft. A standalone viewpoint may link to a comment only if that comment belongs to the same record. Listing returns top-level comments with their replies. _(prs-beh-025; observed)_
- Creating a comment publishes a best-effort announcement (with the owning project, author, parent and a bounded-length excerpt) from which other participants are notified; failure to publish never fails the comment. _(prs-beh-026; observed)_

## Inputs

- Acquire: record kind (bounded length, allowlisted), record id (must be a valid identifier), lifetime seconds within a bounded range with a default. Heartbeat: lock id and extension seconds within a bounded range with a default. Read holder: record kind and record id (must parse as an identifier, otherwise bad request). _(prs-in-001; observed)_
- Record room connect: record kind and record id plus credential in the first frame. App-wide channel client messages: authenticate, report page and project (page text and optional project id, null for none), report status (active or idle), keep-alive. _(prs-in-002; observed)_

## Outputs

- Lock response fields: id, record kind and id, holder id and name, acquired, renewed and expiry times, remaining seconds. Release answers no content. Read holder answers a lock or null. _(prs-out-001; observed)_
- App-wide server messages: roster snapshot (list of users, each with id, name, page, status, first connection time), joined, left (user id only), updated, and keep-alive reply; each with a timestamp. _(prs-out-002; observed)_

## States and transitions

- Lock: absent, held (live), expired (still stored but treated free), then removed by sweep, takeover or release; the holder's re-acquire or renewal returns it to held while live. _(prs-st-001; observed)_
- Client lock state machine: idle, acquiring, then held or conflict or error; held then released on release, or error when a renewal fails. _(prs-st-002; observed)_
- App-wide tab: connected with no project, then in a project room after the first accepted page report, moving between rooms on project change, leaving on close. _(prs-st-003; observed)_

## Timing and ordering

- Illustrative parameters, chosen by the destination: lock lifetime default of about a minute (bounded range); renewal extension default of tens of seconds (bounded range); client renewal interval of several seconds, shorter than the extension; sweep interval of tens of seconds; small bounded number of internal attempts on contention. _(prs-time-001; observed)_
- Idle after a few minutes of no input; keep-alive every tens of seconds; reconnect backoff with full jitter from about a second up to about half a minute (illustrative); presence roster entry orders follow connection order. _(prs-time-002; observed)_
- Announcements ordering on connect to a record room: snapshot to the joiner first, then join announcement to the others; on disconnect, one leave announcement per departed user in roster order. _(prs-time-003; observed)_
- The lock expiry announcements follow the sweep's commit and are therefore at most about one sweep interval late. _(prs-time-004; derived)_

## Edge cases

- Presence snapshot lock-state unknown exists because a failed lock read must not look like nobody holds it; the roster is still delivered. _(prs-edge-002; observed)_
- A user in a record room with multiple tabs appears once in the roster. _(prs-edge-003; observed)_
- Two users in different projects with an administrative role do not see each other in the app-wide channel; reach does not imply presence. _(prs-edge-004; observed)_
- A locked record that cannot be resolved to a project (missing record or unsupported resolution) is treated as not-found for every operation, failing closed. _(prs-edge-005; observed)_
- Presence is per process: with several server workers, lock decisions remain correct (serialized by storage) but presence announcements reach only clients on the same process. _(prs-edge-006; observed)_
- The multi-tab departure case: a user who closes one of several tabs on a record keeps their presence. _(prs-edge-007; observed)_

## Errors

- Unsupported record kind on HTTP: bad request (checked before access so the allowlist error is not masked); invalid record id: bad request; unresolved or inaccessible record: not-found; conflict: 409 with holder details; heartbeat on missing, expired or someone else's lock: not-found; release by non-holder: forbidden. _(prs-err-001; observed)_
- Record room refusals close the connection with policy-violation (code 1008): unknown record kind, invalid record id, bad or missing credential, inactive user, invalid subject, no access to the record's project (with a forbidden-style reason); with internal-error (code 1011) when authentication or authorization could not be judged because of an infrastructure fault. Nothing is sent and the room is not joined before checks pass. _(prs-err-002; observed)_
- App-wide channel refusals: policy-violation (code 1008) for bad credentials and internal-error (code 1011) when authentication could not be judged; failure to check project access places the tab in no project instead of an error. _(prs-err-003; observed)_

## What it must not do

- Nobody can read a record's lock holder or room roster, or plant a lock, on a record in a project they cannot open; the app-wide channel never shows a user to people outside their project. _(prs-neg-001; observed)_
- A non-holder can neither renew nor release a lock; a lock never outlives its expiry for decision purposes; a lock is never held hostage by a disconnected client. _(prs-neg-002; observed)_
- The lock mechanism does not prevent writes by itself: it is advisory, and the client can proceed to edit after a lock error, with a warning. _(prs-neg-003; inferred)_
- The access credential is never placed in the connection address by the current clients. _(prs-neg-004; observed)_

## Security

- Both live channels authenticate by a credential in the first frame and re-verify the user against storage (a forged credential for an unknown user is refused). Access to a record room requires access to the record's project; access to an app-wide room requires access to that project. _(prs-sec-001; observed)_
- The access gate for lock operations resolves every lockable kind to its owning project (directly or through a single link) and uses the common project access rule, with absence and denial both answered as not-found to avoid revealing existence. Unresolvable kinds fail closed and the error is logged loudly. _(prs-sec-002; observed)_
- Presence exposes names and pages only to teammates in the same project; the email's domain is not broadcast. _(prs-sec-003; observed)_

## Invariants

- At most one live lock per record at any instant, regardless of concurrent requests. _(prs-inv-001; observed)_
- Only the holder can extend or release; the sweep removes every lock whose expiry is at or before now. _(prs-inv-002; observed)_
- A user appears at most once in a room roster, and is announced as left only when none of their tabs remain in that room. _(prs-inv-003; observed)_
- Remaining seconds is never negative and equals the floor of the time until expiry. _(prs-inv-004; observed)_

## Notes

- Clients depend on the conflict body fields (holder id, holder name, acquire time, expiry, remaining seconds) and on the lock response fields to render messages; the destination must keep these, or provide equivalents with the same meaning. _(prs-compat-001; derived)_
- Both live channels use JSON text frames with an event discriminator and an ISO timestamp, and first-frame credentials. Whether the exact frame vocabulary must be preserved is a destination decision. _(prs-compat-002; inferred)_
- All durations, intervals, ranges, caps and counts in this spec are illustrative; the destination chooses its own values and need not match any stated number. Close codes 1008 and 1011 are public WebSocket standard codes and may be used as stated. _(prs-compat-003; derived)_

## Non-goals

- No source code, identifiers or message strings are reproduced.
- Do not reproduce origin provenance markers.
- No visual specification of badges, avatars or popovers beyond their behavior.
- Cross-process presence fan-out and persistent presence history are not provided by the observed behavior and are not required.
- Comment markup rendering, mention parsing and building-model viewpoint payload contents are out of scope.
- The destination is not required to mirror the origin's module structure, naming or event vocabulary.

## Test cases

- **prs-test-001**: Given a free record, when user A acquires with the default lifetime, then the answer is created with remaining seconds near the lifetime; reading the holder returns A's lock.  
  Expected: Lock is created and readable.
- **prs-test-002**: Given A holds a live lock, when A acquires again, then the same lock id is returned with a later expiry; when B acquires, then a conflict names A with the remaining seconds.  
  Expected: Idempotent refresh for holder; conflict for others.
- **prs-test-003**: Given A's lock has expired but not been swept, when B acquires, then B holds a new lock and A's old lock id no longer works; when A then heartbeats the old id, not-found is returned; when A acquires, a conflict names B.  
  Expected: Takeover and correct conflict for the former holder.
- **prs-test-004**: Given lifetimes just below the configured minimum, at the minimum, at the maximum and just above the maximum, then the out-of-range ones are rejected and the others succeed; given extensions just below the minimum, at the minimum and above the maximum, then the out-of-range ones are rejected.  
  Expected: Bounds enforced.
- **prs-test-005**: Given A holds a lock with twenty seconds left, when A heartbeats with an extension of thirty seconds, then the remaining time becomes about thirty, not fifty; given an expired lock, heartbeat returns not-found.  
  Expected: Heartbeat replaces expiry and rejects expired locks.
- **prs-test-006**: Given a lock, when a non-holder releases it, then forbidden; when the holder releases, no content and a release announcement; when releasing an unknown id, no content and no announcement.  
  Expected: Release rules.
- **prs-test-007**: Given three expired locks and one live lock, when the sweep runs, then three are removed, three expiry announcements are published after commit, and the live lock remains; repeated sweeps do nothing.  
  Expected: Atomic sweep with one announcement per removal.
- **prs-test-008**: Given an unsupported record kind and a valid kind with a malformed id, then the first returns bad request even if the user lacks access, and the second bad request; given a valid kind for a record in an inaccessible project, not-found.  
  Expected: Validation order and fail-closed gating.
- **prs-test-009**: Given two concurrent acquires on a free record by different users, then exactly one succeeds and the other receives a conflict naming the winner; repeated contention beyond the bounded number of attempts yields a retry conflict, never a server error.  
  Expected: Mutual exclusion.
- **prs-test-010**: Given the list of the caller's locks, then only live locks held by the caller are returned.  
  Expected: My-locks listing.
- **prs-test-011**: Given a client opens a record room, then the first frame is a snapshot with the roster, the lock (or none) and lock state held or free; given the lock read fails, lock state unknown and roster still delivered; the others receive a join announcement.  
  Expected: Snapshot content and ordering.
- **prs-test-012**: Given user A with two tabs in a room and user B with one, when A closes one tab, then no leave is announced; when A closes the second, a leave for A is announced; when B closes the last connection of the room, a leave is announced for every user still on the roster.  
  Expected: Departure semantics.
- **prs-test-013**: Given a record room, when a lock is acquired, renewed, released or expires for that record, then every connected client receives the matching announcement; clients of other records receive nothing.  
  Expected: Room-scoped relay.
- **prs-test-014**: Given invalid credentials, an inactive user, an unknown record kind, a user without project access, and a database outage during authentication, then closures are 1008, 1008, 1008, 1008 and 1011 respectively and nothing is sent first.  
  Expected: Close codes.
- **prs-test-015**: Given a text keep-alive frame followed by a binary frame on either channel, then a reply is sent for the first and the connection stays open after the second.  
  Expected: Robust frame handling.
- **prs-test-016**: Given the client lock controller with automatic acquire, when the record opens, then one acquire is sent with the configured lifetime and renewals on the configured interval extend by more than that interval; on conflict, state is conflict and the holder and seconds appear in a warning; on renewal failure, state is error and renewal stops; on leaving, a release is sent without waiting.  
  Expected: Client lock state machine.
- **prs-test-017**: Given the client roster tracker, when snapshot, join of an existing user, join of a new user and leave arrive, then the roster is replaced, unchanged, extended and reduced respectively; no credential appears in the address.  
  Expected: Roster reducer.
- **prs-test-018**: Given the indicator with the viewer as holder, someone else as holder, and no holder, then the badge shows the editing-by-you label, the locked-by-name label, and is hidden, respectively; with the viewers option and two present users and no holder, a viewers-count label shows.  
  Expected: Badge states.
- **prs-test-019**: Given two users in project P and a third in project Q, when each reports its page and project, then the two see each other and not the third; a tab with no project sees an empty roster and is invisible; an administrative tab in Q cannot see P.  
  Expected: Project-scoped visibility.
- **prs-test-020**: Given user A with one tab in P (page x, idle) and one in Q (page y, active), then P's roster entry shows page x and idle, Q's shows page y and active, with name and earliest connection time per project.  
  Expected: Entry built from tabs in the project only.
- **prs-test-021**: Given A moves a tab from project P to Q and it was A's only tab in P, then P is told A left, A receives Q's roster, and Q is told A joined; if A had another tab in P, P receives an update instead of a leave.  
  Expected: Room transitions.
- **prs-test-022**: Given a report of a project the user cannot open, then the tab is treated as in no project and receives an empty roster; given a status report that is neither active nor idle, it is ignored.  
  Expected: Silent downgrade and validation.
- **prs-test-023**: Given a user with no full name and email 'ana@example.org', then the broadcast name is 'ana'.  
  Expected: Name fallback hides the domain.
- **prs-test-024**: Given the app-wide client with no input for the idle period, then it reports idle; on input, active; when the browser tab becomes hidden, idle immediately; the connection drops, then reconnect delays are random between zero and a doubling ceiling up to the maximum, and reset after a successful open.  
  Expected: Idle detection and backoff.
- **prs-test-025**: Given wire messages: a flat join with id, name, page and status; a snapshot entry with only a connection time and idle status; an entry with an empty id and an object missing the id, then results are a normalized user, a user whose last-active time is the connection time, and two dropped entries.  
  Expected: Normalization rules.
- **prs-test-026**: Given more other users online than the avatar maximum, then the maximum number of avatars and an overflow pill with the remainder show; idle users are dimmed; with nobody else or a closed channel, nothing renders; clicking an avatar opens its popover, clicking again or pressing Escape or clicking elsewhere closes it.  
  Expected: Avatar stack behavior.
- **prs-test-027**: Given a page path whose last non-identifier segment is in the title mapping, one whose segment is unknown, and the root path, then readable titles are the mapped title, a title-cased form of the segment, and the dashboard title; a user idle for five minutes shows an idle-with-duration status.  
  Expected: Popover title and status text.
- **prs-test-028**: Given a reply to a comment on a different record, a reply to a deleted comment and a reply to a missing comment, then bad request, bad request and not-found; given a non-author edit or delete, forbidden; given the author deleting twice, success both times; given an edit after deletion, bad request.  
  Expected: Comment guard rules.

## Open questions (decisions for QC Manager)

- Which discussion comment and viewpoint listing semantics (page sizes, ordering, reply nesting limits, mention types, access gate by record kind) apply? Only the service-level rules were analysed in depth; access gating and ordering for comments were not.
- Should the destination deliver a per-record editing indicator, and what should it show when the lock state is unknown?
- Should the destination identify am-I-the-holder by user identifier rather than by comparing display text (a documented weakness of the origin)?
- Should the destination keep the allowlist of lockable record kinds as observed, or derive it from its own record catalogue?
- Are record-room roster entries ever refreshed after join besides snapshot and join/leave events (no update event exists on that channel)?
- Is multi-tenant scoping of locks expected in the destination?
