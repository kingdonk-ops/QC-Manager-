# 16. Site logistics

Spec `spec-site-logistics-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Per-project delivery coordination for a construction site. Access gates have daily opening hours and optional load or dimension limits. Inbound or outbound deliveries are booked into time windows, optionally on a gate. A manager approves or rejects each booking, and an approval holds the gate slot exclusively. Approval is refused when the window is outside effective opening hours, when the load exceeds the gate limit without a covering special-load permit, when the hourly delivery cap would be exceeded, or when another approved booking already holds an overlapping window. Deliveries carry lines that can be booked against planned line items of the project's priced quantity plan, so every planned line item can be read back as a ledger of delivered, booked and outstanding quantity. Laydown zones are a simple register that can link to a planned site area; area-level planning checks (balance, allocation size, overlap, stage storage and setup) belong to a plan check set. Every record carries per-user action verdicts so the screen can disable or hide actions.

## Behaviour

- A gate belongs to one project and has a name, a daily opening time and closing time as 24-hour clock text (illustrative defaults 07:00 and 18:00), a per-slot capacity as a small positive integer (illustrative default 1), optional notes, an optional access-kind label, and optional non-negative limits for axle load, gross weight, height, width, length and turning radius. Gates list in ascending name order. The destination chooses its own bounds and defaults. _(beh-001; observed)_
- A gate must always close later than it opens. This is checked on creation and again on every change, using the stored value for whichever side was not supplied. _(beh-002; observed)_
- Deleting a gate keeps its deliveries; they simply become gate-less and remain visible. The board shows a gate-less delivery with a neutral no-gate marker. _(beh-003; observed)_
- A laydown zone belongs to one project and has a name, a short capacity description, a free usage note and an optional link to a planned site area. A link to an area of another project, or to an unknown area, is refused as not found. Zones list in ascending name order. _(beh-004; observed)_
- A delivery booking carries: required supplier name, optional contact name and phone, vehicle type, materials description, a time window with an end strictly after its start, a status (default requested), purchase-order reference, notes, an optional gate, an optional link to a planned transport of the same project, a direction of inbound or outbound (default inbound), an optional gross weight in tonnes (non-negative, at most two decimals), an optional equipment item link, an optional scheduling-location link, an optional flow label, a bounded number of lines, and free metadata. Metadata supplied on a change is merged into existing metadata. The destination chooses text length limits and the line cap. _(beh-005; observed)_
- The delivery lifecycle has five states: requested, approved, rejected, arrived and completed. Approve moves a requested or rejected booking to approved. Reject moves a requested or approved booking to rejected and releases its slot. Approving an already approved booking, or rejecting an already rejected one, succeeds without change. A booking that has arrived or completed can no longer be approved or rejected. Moving to arrived and completed is done through an ordinary edit; the screen offers a mark-arrived action on approved bookings and a mark-completed action on arrived bookings to users who may edit. _(beh-006; observed)_
- Every approve or reject records, on the booking, a last-decision note holding the decision, who made it, when, and the optional reason. _(beh-007; observed)_
- Delivery lines are either linked to a planned line item or free-standing. A free-standing line needs a description. A linked line takes its description, unit and item number from the planned line item, not from the request, so quantities against one line item always share that item's unit. A free-standing line keeps whatever item number it was given, which is how a line whose planned item was later deleted keeps its item-number snapshot across unrelated edits. Quantity is positive decimal text (default 1), description and unit are cut to bounded lengths, and lines keep their input order. _(beh-008; observed)_
- A line referencing an unknown planned line item is refused, naming the missing id. A line referencing a line item that belongs to another project is refused. Lines are replaced as a whole on change: omitting the lines leaves them untouched, supplying a list (including an empty one) makes the booking carry exactly that list. _(beh-009; observed)_
- Delivery listing is chronological by window start and can be narrowed by day (any booking whose window touches that day), by gate and by status. The board groups bookings by the calendar day of their window start, shows a count per day, and offers day, gate and status filters with a clear-day control. _(beh-010; observed)_
- Each board row shows the time window, the supplier, indicators for the planned line items carried (each leading to that item, with free-standing and detached lines presented differently and a hint that the original planned item was deleted), materials description, gate, vehicle type, a status indicator, and the action controls the user is allowed. _(beh-011; observed)_
- Per project statistics report: total deliveries, counts per status, number of gates, number of laydown zones, number of approved deliveries whose window has not yet started, number of deliveries carrying at least one line linked to a planned line item, and number of distinct planned line items with at least one delivery line. _(beh-012; observed)_
- The planned-quantity coverage view reads the project's deliverable planned line items in plan order. Only leaf items count: a row that owns children, or is marked as a section heading, is a heading and is excluded. For each line item it reports planned quantity, unit rate, planned total, delivered quantity, booked quantity, outstanding quantity, delivered value and a count of delivery lines. Delivered means lines on arrived or completed bookings; booked means lines on requested or approved bookings; a rejected booking counts toward neither quantity (its lines are still counted in the line count). Outstanding equals planned minus delivered minus booked and is not clamped, so it can be negative. Delivered value is delivered quantity times the line item's current unit rate. An over-delivered indicator is shown per line item; the clear case is delivered quantity alone exceeding planned quantity (its exact basis is an open question). _(beh-013; observed)_
- Stored quantities and rates of planned line items that are blank or not numeric read as zero so the coverage table always renders. Delivery lines whose planned item is outside the requested view are ignored. The coverage view accepts an optional single-group filter, an optional text filter on item number or description, and a bounded row cap; the response states the total before the cap, a truncated flag, the project currency, the number of linked line items, the sum of delivered value over returned rows, and the number of detached lines (lines whose planned item was deleted after booking but whose item-number snapshot remains). The same view feeds the line-item picker in the booking dialog. _(beh-014; observed)_
- Opening-hours check: when a booking names a gate, its window must lie inside the gate's daily hours on the site wall clock. The effective hours are the later opening and the earlier closing of the gate and the project's delivery hours from its logistics settings (the settings apply only where they are narrower). A window that exactly fills the effective hours is accepted. A window that spans two site calendar days is refused when effective hours exist. A gate or settings entry with no hours is treated as unrestricted. Handling of malformed hours is an open question. _(beh-015; observed)_
- Site clock handling: the project's logistics settings state an IANA time zone. Window instants are converted to that zone before comparing time of day. A window supplied without any offset is interpreted as the site wall clock when a zone exists, otherwise stored labelled as UTC and never read as a clock. When the site has no zone, the hours check is skipped, the booking is accepted, and the booking response carries a warning stating that opening hours were not checked until the site time zone is set (naming which project setting ends the warning). The offset of the instant as received is never used as the site clock and UTC is never assumed. _(beh-016; observed)_
- Slot exclusivity: any path that produces an approved booking on a gate (create as approved, change into approved, approve action) refuses when another approved booking on the same gate has an overlapping window. Windows are half-open, so back-to-back windows are allowed. The refusal names the clashing window. The booking being re-approved never clashes with itself. Bookings without a gate are never clash-checked. _(beh-017; observed)_
- Gate load check: an approved booking whose gross weight exceeds the gate's gross-weight limit is refused unless a granted special-load permit, linked to the booking's transport, covers the booking window. Coverage is judged on site calendar dates (validity dates inclusive on both ends) and on the permit's allowed weekday and time-of-day windows, which may run overnight into the next day. An unset limit or an unset weight is never exceeded. When a granted permit exists but the site has no time zone, the permit cannot lift the limit and the refusal additionally reports the missing zone. _(beh-018; observed)_
- Hourly delivery cap: when the project's logistics settings define a maximum number of deliveries per hour, an approval is refused if the count of approved bookings starting within the same site clock hour, including this one, would exceed the cap. The booking being changed is excluded from the count. With no cap nothing is checked. With a cap but no site time zone the approval is refused with a missing-time-zone reason. _(beh-019; observed)_
- Which checks run when: creating a booking as requested runs the hours check (if a gate is named), link validity and flow-label validity. Creating as approved, changing into approved (using the values the booking will have after the change), or approving additionally runs load, hourly cap and slot clash. The approve action also re-runs the hours check, because gate hours or rival bookings may have changed since the request. _(beh-020; observed)_
- A flow label on a booking must be one defined in the project's logistics settings, otherwise the request is refused. Equipment item and scheduling-location links must belong to the booking's project. _(beh-021; observed)_
- Per-record action verdicts: every gate, zone and delivery returned by the API can carry a verdict per action (edit, delete, and for deliveries approve and reject), each stating whether the action is allowed, whether it applies at all, and a refusal reason. For approve and reject the reason is the one the real write would give; permission lack is reported as such. Approve does not apply to an approved booking, reject does not apply to a rejected booking. A separate board-level verdict says whether the user may add a gate, zone or delivery. _(beh-022; observed)_
- Screen behavior from verdicts: an action the record refuses is shown disabled with a localized explanation as its hint and cannot be triggered; an action the user has no right to is not shown at all; an action not applicable is absent; an absent verdict counts as allowed. The add-delivery control stays disabled until the server verdict arrives; a failed verdict read is announced with a retry control and keeps the control disabled; with no active project nothing is requested and nothing is refused. An unchecked-hours warning is shown on the row and does not stop approval. _(beh-023; observed)_
- Deleting a gate, a laydown zone or a delivery first asks for confirmation; cancelling deletes nothing. _(beh-024; observed)_
- Plan checks relevant to laydown and gates, each reported as a pass row or as findings with a localized sentence and suggestion: site time zone must be set (error); gate hours were checked (warning); delivery rate respected (error); area balance closed (warning); allocation within its area (error); no overlapping areas of different kinds (warning); active stage has storage or laydown allocation (error); active stage has site setup allocation (error); every laydown zone mapped to a planned area (warning); gate load respected (error); gate limits known (warning, when a gate states no load or dimension limit at all); quiet hours respected (error). Severities are illustrative. Other planning rules exist in the same check set but are outside this unit. _(beh-025; observed)_
- Area balance for a stage: the site total is the stage's site-total allocation, falling back to the declared site area; the counted area is the sum of allocations of kinds flagged as counting toward balance, grouped by their balance group; the balance is closed when the absolute difference is within a tolerance percentage of the site total. With no site total the balance is reported as not closed with a no-site-total reason and no percentage. The difference percentage is rounded to two decimals. _(beh-026; observed)_
- An allocation larger than its area is a finding (an area of unknown size cannot be exceeded). Two areas of one stage with different kinds whose outlines overlap, in the same coordinate frame, are a finding; same-kind pairs, site-total pairs and pairs lacking outlines are ignored. An active stage lacking any storage or laydown allocation, or lacking any site-setup allocation, is a finding each. _(beh-027; observed)_
- Quiet hours: an approved delivery or transport whose window touches the site's quiet period (which may run overnight) is a finding unless a granted night-work permit covers the whole window. _(beh-028; observed)_
- Three delivery checks are offered to the destination's validation framework: delivery within gate hours (error, one result per booking, plus one project-level warning when the zone is missing), no overlap between approved bookings on a gate (error, one result per approved booking checked against the earlier ones), and deliveries within planned quantity (warning, one result per planned line item that has at least one line, silent for untouched items, ignoring free-standing lines). _(beh-029; observed)_
- Booking, approval and rejection each publish a lifecycle notification (project, delivery, gate, supplier, window, status, acting user) for other modules to react to; creating directly as approved publishes both a booked and an approved notification. Publication does not block the request. _(beh-030; observed)_
- Demonstration data for the board (gates, zones, deliveries) is created only for designated demonstration projects, never for customer projects. Whether the destination wants demonstration data at all is an open decision. _(beh-031; observed)_

## Inputs

- Gate create/change input: project, name (required, whitespace trimmed, bounded length), opening and closing time as HH:MM 24-hour text, per-slot capacity, notes, access kind, the six limits as non-negative decimals with bounded precision (two decimal places), metadata. _(in-001; observed)_
- Delivery create/change input follows beh-005, with bounded text lengths for supplier, contact, phone, vehicle type, purchase-order reference and flow label, and for each line's quantity text, item number, description, unit and note. On change every field is optional; explicitly clearing the window, status or direction to empty is refused as a missing field. _(in-002; observed)_
- Approve and reject accept an optional bounded-length reason; the body itself may be omitted. _(in-003; observed)_
- Coverage query input: project, optional group filter, optional bounded search text, row limit with a bounded maximum. Delivery list query input: project plus optional day, gate and status. _(in-004; observed)_

## Outputs

- Quantities, rates and money cross the interface as canonical decimal text, never floating point. Delivery and gate responses return stored decimals; line quantity is returned as text; a missing quantity reads as 0. _(out-001; observed)_
- Delivery responses include the record's own fields, its lines in order, per-action verdicts and a list of warnings describing checks that were not made; each warning has a code, a severity and the project setting that would end it. The only warning observed is the unchecked-opening-hours one. _(out-002; observed)_
- A refusal of a booking is returned as a client error carrying a stable machine-readable reason and a human message. Refusals observed: outside gate hours, slot taken, gate load exceeded, delivery rate exceeded, site time zone missing, flow label unknown, delivery already on site. Plan-check refusals that would otherwise be validation errors are reported with the same client-error status family used for booking refusals. _(out-003; observed)_

## States and transitions

- requested -> approved (approve action or change); requested -> rejected; approved -> rejected; rejected -> approved (re-approval re-runs every approval check); approved -> arrived; arrived -> completed. Arrived and completed bookings refuse approve and reject. Whether other transitions through ordinary edits should be allowed is an open question. _(st-001; observed)_
- Plan-level lifecycles (stage planned -> active -> closed, plus lifecycles of other planning records) are transition tables owned by the planning area; they are context only for this unit. _(st-002; observed)_

## Timing and ordering

- Approvals that produce an approved booking are serialised per project and gate: the checks and the write happen as one isolated step, so two concurrent approvals cannot both pass the rate or slot check. A request for a slot does not wait behind an approval. _(ord-001; observed)_
- The approve action re-reads the booking after the serialisation step begins; if another approval already decided it, the result is the approved booking unchanged. _(ord-002; observed)_
- Validation rows for overlap are produced in input order, each approved booking compared only with those already seen on its gate. _(ord-003; observed)_

## Edge cases

- End not after start is refused at every layer (input validation, change path, hours check). _(edge-001; observed)_
- A booking with a gate from another project is refused; an unknown gate is not found. A booking naming a transport from another project or unknown is not found. _(edge-002; observed)_
- A change request with no effective fields returns the record unchanged and performs no checks. _(edge-003; observed)_
- A delivery line with no planned-item link and no description is refused; free-standing cargo such as a welfare unit or a skip is accepted and never affects planned-quantity coverage or over-delivery findings. _(edge-004; observed)_
- A window on a clock change day converts correctly because windows are instants and the site zone is applied at comparison time. _(edge-005; inferred)_
- On the screen, a date and time typed for the site is sent as the same instant wherever the planner sits when the project settings name a zone, and shown back as the site hour; without a usable zone it uses the reader's own clock. _(edge-006; observed)_

## Errors

- Unknown gate, zone or delivery identifiers answer not found. A gate or zone of another project is not exposed to a caller without access to that project. _(err-001; observed)_
- A zone link to an area of another project, or an unknown area, answers not found. _(err-002; observed)_
- A failed delivery action on the screen shows an error notice carrying the server message; a failed list read shows a recovery panel with retry rather than an empty state. _(err-003; observed)_

## What it must not do

- Touching windows on one gate do not clash. Requested bookings and bookings of other statuses are never clash-checked and hold no slot. _(neg-001; observed)_
- Reading verdicts never changes data and never blocks concurrent writers. _(neg-002; observed)_
- Delivery booking never writes to the planned quantity plan; the plan is read-only input and the source of truth for what a linked line says. _(neg-003; observed)_

## Security

- Three permission tiers apply: reading is open to viewers, creating and changing gates, zones and deliveries needs editor level, and approving or rejecting needs manager level because it holds or releases a gate slot. Every operation also verifies that the caller has access to the owning project. Other manager-level permissions of neighbouring areas are outside this unit. _(sec-001; observed)_
- Single-record reads and changes resolve the record first and then verify project access using the record's own project. _(sec-002; observed)_
- Demonstration seeding, if offered, is gated to demonstration projects only, because inventing a delivery inside a live project would be a data incident. _(sec-003; observed)_

## Invariants

- At most one approved booking holds any instant on a gate. _(inv-001; observed)_
- Delivered and booked quantity buckets never overlap and a rejected booking is in neither. _(inv-002; observed)_
- Every path that can produce an approved booking runs the same approval checks. _(inv-003; observed)_
- Time-of-day, weekday and calendar-date rules are always evaluated on the site wall clock, never on the offset an instant happens to carry. _(inv-004; observed)_
- A gate's closing time is always later than its opening time. _(inv-005; observed)_

## Notes

- Compatibility is behavioral only. The destination keeps its own names, routes and data layout and chooses its own numeric bounds and defaults. Decimal text for quantities, instants with explicit offsets for windows, and 24-hour HH:MM text for gate hours are the value formats to preserve semantically. _(cmp-001; derived)_
- Message sentences for findings and refusals are localized in the origin; the destination needs its own localisation, with a fallback that turns an unknown reason code into readable words. _(cmp-002; observed)_

## Non-goals

- No implementation code, schema, route or identifier is carried across.
- Other site-planning capabilities (for example customs, utilities, heavy-transport permitting, complaints and just-in-time alignment) are out of scope for this unit.
- A site inventory ledger is a neighbouring capability and is not specified here.
- Exact screen layout, colors, icons and wording are not requirements.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Given a gate open 07:00 to 18:00 and a site time zone, when a delivery is booked for 09:00 to 10:00 site time, it is accepted; when booked for 06:00 to 06:30 it is refused as before opening; when booked for 17:00 to 19:00 it is refused as after closing.  
  Expected: Only the in-hours booking is stored; refusals state which side of the hours failed.
- **ts-002**: Given the same gate, a booking exactly 07:00 to 18:00 is accepted; a booking from 09:00 on one day to 09:00 the next day is refused for spanning two days.  
  Expected: Boundaries are inclusive; multi-day windows are refused.
- **ts-003**: Given a gate with no configured hours, any window including 03:00 to 04:00 is accepted; given an end before the start, the booking is refused regardless.  
  Expected: Unconfigured hours restrict nothing; reversed windows are always refused.
- **ts-004**: Given a project whose logistics-settings delivery hours are 08:00 to 16:00 and a gate open 07:00 to 18:00, a booking at 07:30 to 08:30 is refused; a booking 08:00 to 16:00 is accepted.  
  Expected: The narrower of project-settings and gate hours applies.
- **ts-005**: Given a site with no time zone and a gate with hours, when a delivery is booked at a time outside those hours, it is accepted and the response carries a warning that hours were not checked; setting a zone and re-approving applies the check.  
  Expected: Booking succeeds with a warning; the board row shows the warning and still allows approval.
- **ts-006**: Given an approved booking on gate A from 09:00 to 11:00, a second request on gate A 10:00 to 12:00 is approved by a manager.  
  Expected: The approval is refused, naming the clashing window; the second booking stays requested.
- **ts-007**: Given an approved booking on gate A from 09:00 to 10:00, a request on gate A from 10:00 to 11:00 and another on gate B 09:00 to 10:00 are both approved.  
  Expected: Both approvals succeed; touching and different-gate windows do not clash.
- **ts-008**: Given two requested bookings that overlap on one gate, when the first is rejected and then the second is approved.  
  Expected: Approval succeeds because a rejected booking holds no slot.
- **ts-009**: Given a booking that has arrived, when a manager approves or rejects it.  
  Expected: The action is refused as already on site; the record is unchanged and its verdicts say the action is refused.
- **ts-010**: Given a gate limit of 40 tonnes gross, a booking of 45 tonnes is approved without any permit, then again with a granted special-load permit linked to its transport and valid on the booking's site date, then with the permit's allowed time windows excluding the booking hours.  
  Expected: Refused without a permit; accepted with a covering permit; refused again when the time windows do not contain the booking.
- **ts-011**: Given a project cap of 2 deliveries per hour and two approved bookings starting in the 10:00 site hour, a third booking starting at 10:45 is approved; a fourth starting at 11:05 is approved.  
  Expected: The third is refused naming the hour, count and limit; the fourth is accepted.
- **ts-012**: Given a cap is set and the site has no time zone, a manager approves a booking.  
  Expected: The approval is refused with a missing-time-zone reason.
- **ts-013**: Given two managers approving two overlapping requests on one gate at the same moment.  
  Expected: Exactly one succeeds; the other is refused as slot taken.
- **ts-014**: Given a planned line item of 100 cubic metres at a given rate, deliveries carry lines of 30 (requested), 20 (approved), 40 (arrived) and 500 (rejected).  
  Expected: Delivered 40, booked 50, outstanding 10, delivered value 40 times the rate, line count 4, not over-delivered.
- **ts-015**: Given the same planned line item with a completed line of 140.  
  Expected: Outstanding is minus 40 and the line item is flagged over-delivered; the validation check reports a warning naming the item number; a line item nobody booked against yields no row.
- **ts-016**: Given a planned line item with a blank or non-numeric quantity and a delivery line whose planned item was deleted after booking.  
  Expected: The quantity reads as zero, the coverage table still renders, the detached line is counted in the detached total and shown as unlinked on the board.
- **ts-017**: Given a booking with a line referencing a planned line item of another project, and another with an unknown line item.  
  Expected: Both are refused; a free-standing line with a description is accepted.
- **ts-018**: Given a linked line sent with a different unit and description than the planned line item.  
  Expected: The stored line uses the line item's unit, description and item number.
- **ts-019**: Given a booking with three lines, a change omitting lines, then a change sending one line, then a change sending an empty list.  
  Expected: Lines remain three, then exactly the one sent, then none.
- **ts-020**: Given a viewer, an editor and a manager requesting the same requested booking.  
  Expected: The viewer sees no approve, reject, edit or delete actions; the editor sees edit and delete but no approve or reject; the manager sees approve and reject, with approve disabled and explained when the server would refuse it.
- **ts-021**: Given the add-delivery verdict is still loading, then fails, then is retried successfully.  
  Expected: The control is disabled while loading, remains disabled with a visible retry notice on failure, and enables after a successful retry; with no project selected nothing is fetched.
- **ts-022**: Given the page opened with a section value in its address, then another section chosen, then the default chosen, then an unknown value.  
  Expected: The named section opens; the address records non-default choices; the default leaves it bare; the unknown value shows the delivery board.
- **ts-023**: Given a delete is started on a gate, cancelled, then started and confirmed.  
  Expected: Nothing is deleted until confirmation; the gate's deliveries survive without a gate.
- **ts-024**: Given a stage with a site total of 10000 square metres, a tolerance percentage and counted allocations summing to 9700, then 9000, then no site total at all.  
  Expected: Closed when within tolerance, not closed with the difference reported otherwise, and not closed with a no-total reason when there is no total.
- **ts-025**: Given an active stage with only a site-setup allocation, an allocation larger than its area, and two areas of different kinds with overlapping outlines.  
  Expected: Findings are reported for missing storage, for the oversized allocation and for the overlap.
- **ts-026**: Given demonstration-data seeding is run over a customer project and a demonstration project.  
  Expected: Only the demonstration project receives gates, zones and deliveries.
- **ts-027**: Given a day filter for a given date and a booking from 23:00 that date to 01:00 the next day.  
  Expected: The booking appears under that date's filter; the board groups it under the date of its start.
- **ts-028**: Given a manager approving a booking, then rejecting it with a reason.  
  Expected: Each decision is stored with who, when and the reason; notifications are published for each; the slot is free after rejection.

## Open questions (decisions for QC Manager)

- Per-slot capacity on a gate is stored, shown and edited but never used by any check: approved bookings on a gate are strictly exclusive. Decide whether the destination should enforce a capacity greater than one (concurrent approved bookings up to the capacity) or keep exclusivity and treat capacity as informational.
- Changing a booking through an ordinary edit can set any status, including moving backwards or creating a booking directly as arrived, completed or rejected; only the approve and reject actions refuse bookings that are already on site. Decide whether the destination wants a strict lifecycle table instead.
- Without a site time zone the opening-hours check only warns and the booking proceeds, while the hourly cap refuses approval outright. Decide whether this asymmetry is wanted in the destination.
- The day filter on the delivery list and the upcoming-approved count appear to use a fixed universal day boundary rather than the site's wall-clock day; confirm whether the destination should use the site day.
- Only gross weight is checked for a delivery against a gate; axle load and dimensions are checked only for planned transports. Confirm whether deliveries should also carry and check those.
- The over-delivered indicator considers only delivered (arrived or completed) quantity, so a line item with more booked than planned can show a negative outstanding quantity without the indicator. Confirm whether booked excess should also be flagged.
- Gate or project hours that are malformed, or where closing is not after opening, are silently treated as unrestricted. Decide whether the destination should instead reject such configuration or refuse bookings.
- Whether the destination wants demonstration data for the board at all, and how it would be gated, is undecided.
- The timeline and planned-quantity coverage sections of the page, the booking dialog, and the planning section screens were inspected only for their data needs, not for detailed interaction; a follow-up pass may be required if exact screen flows matter.
- A neighbouring inventory capability was not analysed and needs its own unit if required.
- Large portions of the wider planning area were not read in detail; only the rules that touch delivery booking, gates, laydown and area balance were captured.
