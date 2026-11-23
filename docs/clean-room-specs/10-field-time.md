# 10. Field time (incl. offline)

Spec `spec-field-time-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Field time lets workers clock in and out from a phone with a single position reading per tap, taken only with the worker's recorded consent. Each position is compared with the project's site boundaries (circles or polygons with a tolerance); a tap outside is flagged and waits for a supervisor's reasoned decision but is never refused. Paired taps become shifts; the shifts of a UTC day build a draft timesheet that follows the ordinary timesheet lifecycle of validation, submission, approval, reversal, payroll and cost actuals. Hand-booked days recorded without connectivity are queued on the device and replayed to the server with at-least-once delivery and idempotent server handling. Numeric limits, windows, thresholds and retention values are illustrative; the destination chooses its own values and sources any statutory or regulatory period from the applicable law or policy.

## Behaviour

- A site boundary is either a circle (centre, radius) or a polygon (ordered corner list), with a name (blank becomes a generic default), a tolerance in metres, an optional list of supervisors to notify, a default cost code applied to timesheet lines built from clocks inside it, and an active flag. Only active boundaries are considered when judging a clock. _(beh-001; observed)_
- Boundary input is bounded (illustratively: name up to 200 characters; circle centre latitude -90..90 and longitude -180..180; radius greater than 0 and up to tens of kilometres; tolerance 0 up to a few kilometres; polygon up to 500 corners; up to 50 supervisors; default cost code up to 100 characters). A saved boundary must be usable: a circle needs a centre and a positive radius, a polygon needs at least three corners, all positions in range, tolerance not negative; otherwise the save is refused with an unprocessable response listing machine-readable problem codes and a plain message. _(beh-002; observed)_
- Judging a position against one circle: the distance from the centre is a great-circle distance on a spherical earth model of mean radius; the amount outside is that distance minus the radius, floored at zero. Against one polygon: the position is inside when a standard point-in-polygon test says so, otherwise the amount outside is the shortest distance to the polygon boundary (a local planar approximation is acceptable at site scale). The position counts as inside when the amount outside does not exceed the tolerance. The reported distance is the amount outside (tolerance not subtracted) rounded to one decimal; it is zero when inside the shape itself. _(beh-003; observed)_
- With several active boundaries, the chosen verdict is the containing boundary with the smallest outside distance when any contains the position, otherwise the nearest boundary. With no active boundary at all there is no verdict: the clock is recorded as inside, with no boundary and no distance, and needs no approval. _(beh-004; observed)_
- A clock outside every boundary (beyond tolerance) is stored with approval status pending and is never refused; a clock inside, or with no boundaries defined, has approval status not required. _(beh-005; observed)_
- Per-project clock settings: an enabled flag (default on when nothing was saved), position retention in days (bounded range, illustratively 1..3650, with an illustrative default of 90) and default unpaid break minutes (illustratively 0..240, default 0). Reading settings of a project that never saved any returns the defaults without storing them. Saving settings creates or replaces them. The destination sources the retention default and maximum from applicable data-protection law or policy. _(beh-006; observed)_
- Location consent is recorded per project and worker with a granted flag and a text version; granting stamps the grant time and clears any withdrawal time; withdrawing stamps the withdrawal time and immediately erases every stored position (latitude, longitude, accuracy) of that worker on the project while keeping the clock events themselves and marking them as purged. Reading consent for a worker never asked returns not granted. _(beh-007; observed)_
- A clock event needs project, worker, kind (in or out), latitude, longitude, optional accuracy radius (bounded), optional device-captured time (otherwise server now), optional client operation identifier (bounded length, illustratively 64 characters) and optional note (illustratively up to 2000 characters). Only the position at the tap is kept, never a track. _(beh-008; observed)_
- Recording a clock is idempotent per project and client operation identifier: a repeat with the same identifier returns the earlier event unchanged and does nothing else. _(beh-009; observed)_
- Recording a clock is refused as unprocessable when the clock is switched off for the project, and refused as unprocessable when the worker has no granted consent; the consent refusal tells the caller to ask for consent or book hours on a timesheet instead. Both refusals carry a stable machine-readable code. _(beh-010; observed)_
- In/out pairing at capture: the worker's most recent earlier clock decides. A clock-in while the most recent earlier event is a clock-in is refused as a conflict (already clocked in, naming the open event). A clock-out without a most-recent earlier clock-in is refused as a conflict (not clocked in). A clock-out is linked to the clock-in it closes. _(beh-011; observed)_
- A stored clock keeps position rounded to a fixed precision (illustratively 7 decimal degrees) and accuracy (illustratively 2 decimals), the boundary used, whether it was inside, the outside distance, its approval status and the recorder. A clock whose own time is older than the retention window is stored without any position and marked as purged. Every clock write also erases positions older than the retention window for the whole project, so no position outlives its window. _(beh-012; observed)_
- After a clock is stored, notifications are issued for the clock-in or clock-out and, for a flagged clock, an additional flag notification plus an in-app notification to the boundary's named supervisors and the project owner (duplicates removed) carrying worker name, site name, distance in whole metres and kind. Failure to notify never fails the clock. _(beh-013; observed)_
- Crew clocking: given a crew as the worker, the same position and time are applied to the crew itself and to each linked crew member (each once). Each member gets its own event with a client operation identifier made from the supplied one plus the member's index. A member who cannot be clocked (no consent, already in the requested state, clock disabled) is skipped and reported with a short reason code; the crew operation as a whole still succeeds and returns both recorded events and the skipped list. _(beh-014; observed)_
- A supervisor decision on a flagged clock requires a reason of bounded length (illustratively 3 to 2000 characters). Approving or rejecting is allowed from pending; approving is also allowed from rejected; rejecting an already rejected clock, or deciding a clock that is approved or never needed approval, is refused as a conflict stating the current status. A decision records the deciding user, the time and the reason, writes an audit entry (best effort) and issues a decision notification. _(beh-015; observed)_
- Clock events are listed for an inclusive date window (whole UTC days), optionally filtered by worker and by approval status (not required, pending, approved, rejected), newest first, with paging (illustratively default page 500, maximum 2000). _(beh-016; observed)_
- Shifts are formed per worker in time order by pairing each clock-in with the next clock-out. A second clock-in before a clock-out does not close the first shift: the first stays open and a new shift starts. A clock-out with no open shift is ignored when pairing. At the same instant, an in sorts before an out. _(beh-017; observed)_
- An open shift counts as a missing clock-out when it started longer ago than a threshold (illustratively 16 hours), or when the same worker has a later shift. Two closed shifts of one worker overlap when the later one starts before the earlier one ends; touching end-to-start is not an overlap. _(beh-018; observed)_
- Paid hours of a closed shift are its duration minus the unpaid break, never negative, rounded half-up to two decimals; an open shift has zero. The break actually applied never exceeds the shift's length in whole minutes and is never negative. A shift counts as approved when each of its flagged ends is approved (ends that never needed approval count). _(beh-019; observed)_
- The who-is-on-site status looks at a recent window of clocks (illustratively the last 7 days) and reports: workers with an open shift that is not a missing clock-out (name, time clocked in, whether inside, the opening event), their count, ordered by clock-in time; the number of clocks awaiting a decision; the number of missing clock-outs; and today's hours (UTC day) summed over shifts that started today, counting an open shift up to now, shown with two decimals. _(beh-020; observed)_
- Building a day's timesheet from clocks creates a draft timesheet marked as coming from the clock, with one line per closed shift that started on that UTC day, per worker and start time. Each line carries the worker, start and end times, the unpaid break (project default clamped to the shift) and the default cost code of the shift's boundary; hours come from the times. A line whose shift has an unapproved flagged end carries a note saying the clock was outside the site boundary and awaits approval. The clocks used are linked to the timesheet. The timesheet has a short generic note saying it was built from the time clock. _(beh-021; observed)_
- Building again for a day that already has a draft clock timesheet refreshes it: all lines are replaced from the current shifts. If that day's clock timesheet is already submitted or approved, the build is refused as a conflict telling the caller to reverse it first. If a locked payroll period covers the day, creating or refreshing is refused as a conflict. _(beh-022; observed)_
- A day built from clocks is gated by clock rules during validation: any clock outside the boundary that is still pending or rejected is an error that blocks submission; overlapping shifts of one worker is an error; an unclosed shift past the missing-clock-out threshold or superseded by a later shift is a warning. _(beh-023; observed)_
- Timesheet lines record either a worker or a machine, never both and never neither (unprocessable otherwise). A line that carries a start and end time has its hours derived from them minus the break and any typed hours are overruled; a line without times keeps typed hours. Times that cannot give a duration are refused as unprocessable with a reason: only one time given, mixed time-zone awareness, zero length, a single continuous span over 24 hours, negative break, or break as long as or longer than the shift. An end before start is read as crossing midnight. _(beh-024; observed)_
- Timesheet lifecycle: draft, submitted, approved, reversed. Header edits, line edits and deletion are draft only (bad request otherwise). Submitting requires a draft with at least one line and no error-severity validation findings (unprocessable with the list of errors otherwise). Approving requires submitted state and no errors; on approval hours become authoritative actuals, daywork lines are mirrored, approval time and approver are stored, an audit entry is written, and downstream publications for payroll and cost actuals are issued. _(beh-025; observed)_
- Reversing is allowed only for an approved timesheet: a new approved timesheet is created whose lines mirror the original with negated hours, linked back to the original, which flips to reversed. Hours therefore net to zero for cost and payroll. Reversal, like every change, is refused as a conflict when a locked payroll period covers the day. _(beh-026; observed)_
- Per-worker daily cap: the sum of one worker's labour hours across a day's lines may not exceed a ceiling (illustratively 24, configurable per timesheet); machine lines are exempt; negative hours count as zero. Two lines of one worker whose start-to-end intervals overlap are flagged as a likely double booking, comparing only lines that have both times and skipping pairs whose time-zone awareness differs. _(beh-027; observed)_
- Approved labour cost for a period: approved, non-reversed timesheets in an optional inclusive date range are summed into labour hours, labour cost (hours times each worker's rate), count of timesheets and how many hours came from clock-built timesheets, with a project currency; hours and cost shown to two decimals. Rate sourcing is not specified here. _(beh-028; observed)_
- Clock panel (phone-oriented screen): the person chooses who is clocking from the project's people resources; the screen loads the project's clock settings, status and that person's consent. If consent is not granted, tapping clock in first shows a consent dialog that states the retention period in days and the consent text version, and the device position is not read until the person agrees; agreeing records consent. When consent exists a clock tap reads the device position exactly once and sends kind, latitude, longitude, accuracy, a freshly generated client operation identifier and the device time. A withdraw-consent action is offered. _(beh-029; observed)_
- When the answer says the clock was outside, the panel shows a status message (not a blocking error) with the distance in whole metres and that the clock is flagged for supervisor approval. When the device is offline the tap is stored in a device-side queue instead of being sent, and a status message says it was saved on the device. _(beh-030; observed)_
- Clock log view groups events by day (newest day first) and by worker: an unpaired clock-in on a past day shows as a missing clock-out and counts toward that day's missing count; an unpaired clock-in on the current day shows as an open shift, not a miss; a paired shift is complete; a day counts its clocks awaiting approval. The default log window is two weeks inclusive of today. _(beh-031; observed)_
- Boundary drawing helpers on the client: distance between two positions on a sphere (one degree of latitude is about 111 km); a circle is drawn as a closed ring whose vertices all lie at the radius; point-in-polygon returns false for fewer than three corners; the inside/outside preview for a candidate position honours tolerance (a circle with radius 100 m and tolerance 20 m treats 110 m from the centre as inside and 300 m as outside with an outside distance above 190 m) and reports the distance to the polygon edge for polygons; an incomplete boundary gives neither ring nor preview; a radius dragged from the edge never goes below a small minimum (illustratively 1 metre). _(beh-032; observed)_
- Device-side offline queue, resend rules. Every recorded operation gets its own fresh operation identifier; a day recorded more than once keeps one stable entry key across recordings, so a correction made offline is kept as a second queued operation rather than swallowed. Queued operations replay strictly in recording order and the body sent is exactly the body recorded; withdrawals queue as their own kind of operation. Server answers are interpreted as follows: created or replayed both mean applied, stop resending and remove the item; a conflict (for example a withdrawn or already-approved day) means stop resending, remove the item and report the server's reason to the user; unprocessable or forbidden means give up on that item (rejected, remove and report); server errors, gateway errors and network failure mean retry later and leave the item queued; a success answer with no readable body still counts as applied, with no result identifier. Where persistent storage is unavailable the queue falls back to memory instead of dropping writes. Queued bodies that cannot be read yield an empty key rather than raising. _(beh-033; observed)_
- Offline day keeping on the device: a foreman records a whole day (project, date, note, worker or machine lines with hours or clock times, cost code, optional device label and device-captured time) and the day is placed in a device-side queue under a stable per-day entry key. Each save of the same day queues the day's entire current state under a fresh operation identifier but the same entry key; the queue is persistent where the device allows it and in memory otherwise. When connectivity returns the queue drains in recording order; an item is removed only after the server answers in a way that means stop resending (applied, replayed, rejected, conflict); retryable trouble leaves it queued. The roster and cost pickers are warmed from earlier loads so the screen still works after the link drops. The day may be marked to be sent for approval on arrival. _(beh-034; observed)_
- Server-side replay safety for offline days: delivery is at-least-once, so every submission is keyed by the entry key within a durable server-side ledger shared with other field records. A key never seen creates a draft timesheet (with an offline marker carrying the entry key, the device time as a non-trusted note, the server's own arrival time and the device label) and records the key against it; a key already tied to a timesheet is not written twice. The submission carries the day's full state, so reapplying it is idempotent. _(beh-035; observed)_
- Redelivery versus correction: when a key's timesheet already exists and the incoming day equals it (same date, same note, same set of lines, compared on values rather than spelling: hours by numeric value, timed lines by the hours their times produce, instants by value, order ignored; server-stamped metadata ignored) the answer is replayed and nothing changes, whatever state the office has moved the timesheet to. If the content differs and the timesheet is still a draft, its lines, date, note and offline marker are replaced wholesale (answer: updated), subject to the payroll lock on both the old and new day. If it differs and the timesheet is no longer a draft the correction is refused as a conflict stating the office state and that approved days are corrected by reversal. _(beh-036; observed)_
- Sending an offline day on for approval is attempted when requested and the day is still a draft; if validation or a bad-request guard refuses, the day is kept as a draft and the answer says it was stored but not submitted (the hours are never discarded); other failures propagate. The answer reports whether the day ended up submitted. _(beh-037; observed)_
- Withdrawing an offline day by its entry key is remembered even when the key is unknown, so a withdrawal that overtakes its own creation blocks the later creation (conflict: the day was withdrawn on the device; enter it as a new day if the hours were real). A repeat withdrawal answers already withdrawn. Only a draft timesheet is deleted by withdrawal (subject to the payroll lock); a day already submitted or approved cannot be withdrawn from the device (conflict), so approved hours are only undone by reversal. _(beh-038; observed)_
- Entry key ownership: a key already used by a different kind of field record is refused as a conflict (the device must mint a new key); a key that belongs to a different project than the one in the request is refused as not found, so a stale key replayed after the active project changed cannot touch another project's day. A key whose earlier attempt claimed it but never produced a timesheet is treated as new, so a failed attempt cannot lose the day. Two racing deliveries of one key keep only one ledger entry; the loser's insert is discarded without discarding the timesheet. Lines must still obey the worker-or-machine rule. _(beh-039; observed)_
- Replay can never move money or claim a worker-day: the offline path only produces drafts or submitted timesheets; approval stays a deliberate office action that posts actuals. _(beh-040; observed)_
- Geofence check summary (inputs and outcome): inputs are the tap position (latitude, longitude, both required and range-checked), the optional accuracy radius (stored but not used in the verdict), and the project's active boundaries each with shape, geometry and tolerance in metres. The verdict is inside when the distance beyond the boundary does not exceed the tolerance. Outcome outside: the clock is saved, marked outside with the distance, set to pending approval, supervisors are notified, the worker sees a non-blocking flagged message, and the timesheet built from that day cannot be submitted until a supervisor approves with a reason. Outcome inside or no boundaries: saved as ordinary with no approval needed. _(beh-041; observed)_

## Inputs

- Timesheet build request: project and one calendar day. _(in-001; observed)_
- Decision request: a reason of bounded length (illustratively 3 to 2000 characters) plus an approve-or-reject choice. _(in-002; observed)_

## Outputs

- A clock event response carries identifiers, worker name, kind, time, position or a purged flag, boundary name, inside flag, outside distance, approval status with reason, approver and time, pairing link, timesheet link, note and creation time. _(out-001; observed)_
- Crew clocking returns the recorded events and the skipped members with reason codes. Retention purge returns how many events lost their position. _(out-002; observed)_

## States and transitions

- Clock approval status: not required (inside or no boundaries) stays final; pending moves to approved or rejected by a decision; rejected can move to approved; approved is final. _(st-001; observed)_
- Worker clock state: not clocked in to clocked in (in) to not clocked in (out); no other transitions are accepted at capture. _(st-002; observed)_
- Consent: never asked to granted to withdrawn and back to granted; withdrawal erases positions, regrant does not restore them. _(st-003; observed)_
- Timesheet: draft to submitted to approved to reversed (original) with a new approved mirror timesheet created at reversal. _(st-004; observed)_

## Timing and ordering

- Day boundaries for clocks, status, timesheet building and listing are UTC calendar days of the clock-in instant. _(time-001; observed)_
- Retention purge runs after every stored clock for the project and is also available as an administrative action; the cutoff is the start of the UTC day that lies one retention window before today. _(time-002; observed)_
- Queued offline operations replay in the order they were recorded. _(time-003; observed)_

## Edge cases

- A clock exactly at the edge of the tolerance counts as inside (outside amount equal to tolerance passes). _(edge-001; observed)_
- A circle boundary whose centre is missing cannot be saved; judging such an incomplete boundary is not a supported case. _(edge-002; inferred)_
- A replayed offline clock older than the retention window is accepted as a clock but stored without any position. _(edge-003; observed)_
- A shift that crosses midnight belongs to the day on which it started when building timesheets; a clock-out the next day does not create a second line. _(edge-004; observed)_
- When building a timesheet the events fetched span a day either side so a shift started late on the day is paired with a clock-out after midnight. _(edge-005; observed)_
- A clock-in and a clock-out of one worker at the same instant sort the in first. _(edge-006; observed)_

## Errors

- Clock capture failures: disabled clock (unprocessable, coded), missing consent (unprocessable, coded), already clocked in (conflict, coded with the open event), not clocked in (conflict, coded). Boundary or event not found: not found with a plain message advising a refresh. _(err-001; observed)_
- Decision failures: not pending (conflict naming the current status); reason shorter than the minimum (input validation). _(err-002; observed)_
- Timesheet build on a submitted or approved clock timesheet: conflict with a stable locked code naming the day and the state. _(err-003; observed)_
- Timesheet failures: edit of a non-draft (bad request, explaining the lock and the reverse-and-reenter route); submit of a non-draft or empty timesheet (bad request); validation errors on submit or approve (unprocessable with rule identifiers, messages and element references); approve of a non-submitted sheet (bad request); reverse of a non-approved sheet (bad request); line not part of the sheet (not found); locked payroll period (conflict). _(err-004; observed)_

## What it must not do

- A clock outside the boundary is never refused at capture; it is only flagged. _(neg-001; observed)_
- The capability never stores a track of positions, and never stores a position for a worker without recorded consent. _(neg-002; observed)_
- A line may never hold both clock times and an independent typed hours figure; the times decide. _(neg-003; observed)_

## Security

- Location is personal data: it is captured only after recorded consent, only at the tap, erased on withdrawal, erased after the retention window, and withheld from clocks replayed after that window. _(sec-001; observed)_
- Supervisor decisions are accountable: reason required, deciding user and time stored, audit entry written. _(sec-002; observed)_
- Boundary and settings changes need the administrative tier, clocking needs the worker tier, decisions need the approval tier, each with project access. _(sec-003; observed)_
- Security requirement for the destination: people pickers used by clocking, timesheet editing and offline day recording must list only workers and crews assigned to, or explicitly shared with, the open project. A resource with no project assignment must not become visible in every project by default; whether such a shared pool exists, and how it is designated, is a decision point. _(sec-004; inferred)_
- Security requirement for the destination: the machine list offered by every field-time screen, including the offline day recorder, must be narrowed to machines assigned to, or explicitly shared with, the open project, using the same rule as people pickers. _(sec-005; inferred)_
- Security requirement for the destination: the server must verify that a worker or crew named in a clock or crew-clock request belongs to, or is assigned to, the project named in the request, in addition to checking the caller's access to that project; crew expansion must drop members outside the project; and any resource-listing call filtered by project must itself check the caller's access to that project. Without this, a caller with access to one project could clock a worker of another project when consent exists. _(sec-006; inferred)_

## Invariants

- Every stored clock event either has a position or is marked purged; a worker has at most one open shift at capture time. _(inv-001; derived)_
- Paid hours are never negative and never exceed shift length; applied break never exceeds shift length. _(inv-002; observed)_
- An approved timesheet and its reversal net to zero hours. _(inv-003; observed)_

## Notes

- Numeric limits, thresholds (including the missing-clock-out threshold, radius limits, default retention and page sizes), and the UTC day convention are illustrative; the destination chooses its own values. Status words (not required, pending, approved, rejected; draft, submitted, approved, reversed) are generic state names to preserve only where existing stored records rely on them. Retention periods are sourced from the applicable data-protection law or policy, not from this spec. _(compat-001; inferred)_
- Distances use a spherical earth model accurate well within a metre at site scale; equal output requires matching rounding (one decimal for distances, two decimals for hours, a fixed precision for stored positions) but not any particular earth radius constant. _(compat-002; inferred)_

## Non-goals

- No implementation code is generated.
- Do not reproduce origin provenance markers.
- Payroll export profiles and runs, working-time regulation records, productivity analytics and AI cost-code suggestions are neighbouring field-time behavior not specified here beyond what interacts with clocks.
- The screen layout of the offline day recorder and the timesheet editor is not specified; only its queueing, resend and replay behavior is.
- Map rendering details of the boundary editor are not specified.

## Test cases

- **test-001**: Given a circle boundary radius 100 m tolerance 20 m at position (52.0, 13.0), when positions 0 m, 110 m and 300 m north of the centre are judged.  
  Expected: First two are inside; third is outside with outside distance about 200 m (more than 190).
- **test-002**: Given a square polygon with 0 tolerance, when a point inside, and a point about 110 m beyond one edge are judged.  
  Expected: Inside with distance 0; outside with distance between 100 and 120 m.
- **test-003**: Given two overlapping active boundaries, one containing the point and one nearer to it but not containing it, and then a project with no active boundaries.  
  Expected: The containing one is chosen; with none the clock is inside, no boundary, no distance, approval not required.
- **test-004**: Given a boundary save with a circle lacking a radius, then a polygon of two corners, then a negative tolerance.  
  Expected: Each refused as unprocessable listing the matching problem code.
- **test-005**: Given worker Ann without consent, when a clock-in is sent.  
  Expected: Unprocessable with the consent-required code; nothing stored.
- **test-006**: Given consent granted, clock enabled, when a clock-in inside the boundary is sent twice with the same client operation identifier.  
  Expected: One event stored; the second call returns the same event.
- **test-007**: Given Ann is clocked in, when another clock-in arrives; and given Ben is not clocked in, when a clock-out arrives.  
  Expected: Conflict already clocked in (naming the open event); conflict not clocked in.
- **test-008**: Given consent and a boundary, when a clock-in is sent 250 m outside it.  
  Expected: Event stored with pending approval and distance about 250; supervisors named on the boundary and the project owner are notified once each; the call succeeds.
- **test-009**: Given a pending outside clock, when a supervisor decides with a too-short reason, then rejects with a proper reason, then approves, then approves again.  
  Expected: The too-short reason is refused as invalid input; rejection stored; approval after rejection allowed; any further decision on the approved clock is refused as conflict not pending.
- **test-010**: Given a worker with stored positions on three events, when the worker withdraws consent.  
  Expected: All three events remain with positions erased and marked purged; withdrawal time recorded; later clocks are refused until consent is regranted.
- **test-011**: Given retention 30 days, when a clock dated 45 days ago is replayed with consent present.  
  Expected: Accepted but stored without position and marked purged; other events older than 30 days lose their positions.
- **test-012**: Given a crew with members Cy (consented) and Dee (no consent), when the crew is clocked in with operation id op1.  
  Expected: Events for the crew resource and Cy are created; Dee appears in the skipped list with the consent reason code; response status is created.
- **test-013**: Given clock events in 08:00, in 09:00, out 17:00 for one worker.  
  Expected: Two shifts: the first stays open and counts as a missing clock-out because it was superseded; the second is closed with 8.00 paid hours.
- **test-014**: Given an open shift started 17 hours ago and another started 2 hours ago by different workers, with a missing-clock-out threshold of 16 hours.  
  Expected: Status counts one missing clock-out and shows only the second worker on site.
- **test-015**: Given shifts 08:00 to 12:00 and 12:00 to 16:00 for one worker, and then 08:00 to 12:00 and 11:00 to 15:00.  
  Expected: No overlap for the first pair; overlap reported for the second.
- **test-016**: Given a closed shift of 8 hours and a project default break of 30 minutes, then a break default of 600 minutes on a 4 hour shift.  
  Expected: Line break 30 min and hours 7.50; second break clamps to 240 min, hours 0.00.
- **test-017**: Given three workers with shifts on one UTC day, one of whom has an unapproved outside clock, when the day's timesheet is built, then submitted.  
  Expected: A draft with three lines is created, the flagged line carries the awaiting-approval note, the clocks are linked; submission is blocked by an error naming the unapproved clock until a supervisor decides.
- **test-018**: Given a draft clock timesheet and a later shift correction, when the day is built again; then after the timesheet is approved, when it is built once more.  
  Expected: Lines are replaced from current shifts; the final build is refused as a conflict telling the caller to reverse first.
- **test-019**: Given a locked payroll period covering the day, when any build, edit, submit, approve or reverse is attempted.  
  Expected: Each is refused as a conflict.
- **test-020**: Given a line with neither worker nor machine, then with both.  
  Expected: Each is refused as unprocessable.
- **test-021**: Given a line with start 22:00, end 06:00 next morning, break 30 minutes and typed hours 3.  
  Expected: Stored hours 7.50 (times overrule typed hours).
- **test-022**: Given lines with: only a start time; start equal to end; 26 hour span; break 480 minutes on an 8 hour span.  
  Expected: Each refused as unprocessable with the matching interval reason.
- **test-023**: Given one worker with lines of 14 and 11 hours on one day with the default cap, and a plant line of 30 hours.  
  Expected: The worker exceeds the cap and the timesheet cannot be submitted; the plant line is exempt.
- **test-024**: Given an approved timesheet of 8 hours, when it is reversed.  
  Expected: A new approved timesheet of minus 8 hours exists linked to the original, which is now reversed; labour cost for the period counts neither.
- **test-025**: Given the clock panel for project P with consent not yet granted, when the person taps clock in, then agrees.  
  Expected: A dialog states the retention days and consent version; no position was read before agreement; agreement records consent.
- **test-026**: Given consent granted and the answer says outside by 250.4 m.  
  Expected: One position read; sent body carries kind, position, accuracy, an operation identifier and a time; a status message mentions 250 m and supervisor approval; no blocking error.
- **test-027**: Given the device is offline and consent is granted, when the person taps clock in.  
  Expected: Nothing is sent; the tap is queued; a status message says it was saved on the device.
- **test-028**: Given today is 2026-10-25, a lone clock-in on 2026-10-20 and a lone clock-in today, and a paired shift on 2026-10-22 with a pending flag.  
  Expected: Days order 10-25, 10-22, 10-20; the 10-20 worker shows missing clock-out with day missing count 1; today's shows open; 10-22 has pending count 1; log window start is 2026-10-12.
- **test-029**: Given an offline day recorded twice with the same entry key and different hours, then a second day with a later date.  
  Expected: Three queued operations with three distinct operation identifiers; entry keys of the first two equal; replay order matches recording order; bodies unchanged.
- **test-030**: Given server answers: created, replayed, conflict with a reason, unprocessable, forbidden, 500, 502, 200 with no body, and a dead link.  
  Expected: Applied, applied, conflict with reason (removed and reported), rejected, rejected, retry, retry, applied with no result id, and the item stays queued.
- **test-031**: Given a status request with two on-site workers, one clock awaiting approval, and shifts today totalling 5.5 hours including one open shift.  
  Expected: On-site count 2 ordered by clock-in time; pending approvals 1; today hours shown as 5.50.
- **test-032**: Given a clock in 23:00 and out 03:00 next day on 2026-05-04.  
  Expected: One line appears on the 05-04 timesheet and none on 05-05.
- **test-033**: Given key K never seen, when a day of 8 hours for worker Ann on 2026-06-11 is delivered twice (second time after a lost response, hours spelled 8.0).  
  Expected: First answer created, second replayed; exactly one timesheet exists; nothing rewritten.
- **test-034**: Given key K already produced a draft of 8 hours, when the same key arrives with 6.5 hours.  
  Expected: Answer updated; the draft now holds 6.5 hours with the offline marker refreshed.
- **test-035**: Given key K produced a day that the office has approved, when the same content, then a corrected content, arrives under K.  
  Expected: Same content answers replayed with no change; corrected content is refused as a conflict mentioning reversal.
- **test-036**: Given a withdrawal for key K arrives before any creation, then the creation arrives; and separately a withdrawal for a key whose day is already approved.  
  Expected: The creation is refused as a conflict (day withdrawn); the approved-day withdrawal is refused as a conflict and the day stays.
- **test-037**: Given key K was used for a record of another kind, then a key of project P replayed against project Q.  
  Expected: First refused as conflict advising a new key; second refused as not found; no data touched.
- **test-038**: Given a requested-submit offline day with an invalid line.  
  Expected: Day stored as a draft and the answer says stored but not submitted.
- **test-039**: Given a clock-in request for a worker who is not assigned to the project named in the request, by a caller with access only to the named project, with consent recorded for the worker elsewhere.  
  Expected: Per the security requirement, the request is refused and nothing is stored; the exact status code is a destination decision.
- **test-040**: Given the worker, crew and machine pickers opened for project P while other projects own their own resources and a pool of unassigned resources exists.  
  Expected: Only resources assigned to or explicitly shared with P are listed; resources owned by other projects never appear; unassigned resources appear only if the destination's shared-pool decision allows it.

## Open questions (decisions for QC Manager)

- Decision point: all day boundaries use UTC days; for sites far from UTC a shift late in the local day may land on the next UTC day. Decide whether to use project-local days.
- Decision point: the device-supplied clock time is accepted without a future-time check; decide whether to bound it (for example not later than now plus a small slack).
- Decision point: overlap between shifts treats touching end/start as no overlap, and overlap between timesheet line intervals is strict-inequality as well; confirm both are intended and consistent.
- Decision point: polygon outside-distance may use a local planar approximation; confirm that is acceptable for very large polygons.
- Decision point: consent withdrawal is available at the worker permission tier while consent reading is at the read tier; decide who may record or withdraw consent on behalf of a worker.
- Decision point: rejected clocks still block submission as unapproved; clarify whether a supervisor can resolve a rejected clock short of correcting the timesheet.
- Decision point: building a timesheet from clocks only includes closed shifts, so open shifts produce no line; decide whether they should be listed as incomplete lines instead.
- Decision point: shared-pool visibility. Workers, crews and machines with no project assignment are currently visible in every project; decide whether to keep a shared pool at all, how it is designated, and whether it requires an explicit per-project opt-in.
- Decision point: machine list scoping. Decide the rule that narrows machine pickers to a project and apply it to every field-time screen, including the offline recorder.
- Decision point: server-side membership. Decide whether capture endpoints require worker membership in the project (assignment or home project), whether crew expansion drops members outside the project, and whether the resource listing call itself verifies the caller's access to the filtered project.
- Decision point: entry keys are unique per device-minted value across all field records; decide whether keys should be scoped by project and record kind rather than refused on collision.
- Decision point: a submission with no authenticated identity creates the day but records no replay key, so a replay would create duplicates; decide whether anonymous submissions should be refused.
- Unknown: the exact conflict versus replay answer when an identical day arrives for a key whose timesheet was reversed by the office is not specified; decide it.
- Unknown: how daywork mirroring, payroll-period locking, rate resolution and cost-actual publication behave in detail is not specified here and should be covered by the payroll and cost specs.
- Unknown: working-time record, overtime split, rounding-increment and week-start settings are not specified; treat as separate field-time slices, with any statutory limits sourced from applicable law.
