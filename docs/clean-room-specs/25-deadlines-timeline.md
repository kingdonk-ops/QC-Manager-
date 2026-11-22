# 25. Deadlines register and project timeline

Spec `spec-deadlines-timeline-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A read-only per-project deadline register that gathers still-open dated work from many functional areas, classifies each item as overdue, approaching or on time using whole-day arithmetic, sorts and counts it, and resolves owners; a periodic sweep that proactively notifies owners (falling back to project managers), re-nudges within strict limits, escalates once to managers and gives early reminders for selected sources; and a chronological project timeline built from a persisted subset of significant cross-area events, queryable per project or per record with filters, paging and a stable order, plus its client screen (filters, search, stats, CSV export, record links). All numeric limits, windows and caps in this spec are illustrative; the destination chooses its own values.

## Behaviour

- The register owns no data. It reads dated records that other areas already hold, and an item leaves it only when the source record is closed or its date is changed there. It creates no deadlines of its own. _(ddl-beh-001; observed)_
- Inclusion rule: a record is a deadline when someone is blocked waiting on it and its lifecycle has a state that closes it. Expiry times of sessions, tokens, locks, caches, shares, uploads and jobs are intentionally excluded, and document approvals are excluded because they have their own overdue handling. _(ddl-beh-002; observed)_
- Sources collected are the destination's own record kinds that satisfy the inclusion rule, each with its own date and its own set of closing states. Categories observed in the origin: correspondence response dates; corrective actions on non-conformances; punch items; information request answer dates; submittal required-by dates; variation request decision dates; temporary-works design dates and permit validity ends; defect rectification dates; quality inspection booked dates; compliance document expiry; bid package submission deadlines; signature session expiry; payment-plan claims not yet raised; payment-plan instalments falling due; and records of user-defined modules that declare a due-date field. Per-source nuances: some sources count only records that are in force or already submitted (pre-submission drafts and not-yet-in-force permits are not counted); some keep a record open when it is sent back for rework or paused; for expiry-driven sources an expired record is the most urgent rather than closed; a scheduled inspection whose booked date has passed still counts. _(ddl-beh-003; observed)_
- Closing states are modelled by exclusion: any status not in a source's closing set is treated as still open, so an unknown intermediate state over-surfaces rather than hides work. _(ddl-beh-004; observed)_
- A due value may be a timestamp, a date text, or a date-time text (with or without a trailing UTC marker); it is reduced to a calendar date. Empty or unparseable values mean no deadline and never raise. _(ddl-beh-005; observed)_
- Classification uses date-only arithmetic: days overdue is today minus the due date (signed). Greater than zero is overdue with critical severity; zero up to and including the approaching window ahead is approaching with warning severity (due today is approaching, not overdue); anything further out, closed items and items without a date are on time with informational severity and never appear in the register. _(ddl-beh-006; observed)_
- Register output: items filtered by segment (all means overdue plus approaching), ordered with overdue before approaching, then most overdue first, then by id for stability, then truncated to the requested limit. Overdue and approaching totals are computed from the full classified set before the segment filter and before truncation, so the count chips are stable when the user switches segment. _(ddl-beh-007; observed)_
- Each register item carries: stable source-prefixed id, source key, related record kind and id, project id and name, title, optional human reference number, normalized due date, owner id and display name when resolvable, source-native status, classification, signed days overdue, severity, a relative link to open the record, optional readable source label (for user-defined modules) and optional per-source reminder lead time. _(ddl-beh-008; observed)_
- Owner rules per source: information requests use the assignee or the party holding the next move (a role label that is not a user id is not an owner); correspondence, compliance documents, bid packages and signature sessions use their creator as a best-effort owner; punch items and corrective actions use the assigned or responsible person; submittals the reviewer or next-move holder; variations the next-move holder; temporary-works designs the coordinator; inspections the inspector; permits, defects and payment-plan items have no owner (free-text company names are not owners); user-defined modules use the first user-link field they declare. _(ddl-beh-009; observed)_
- Owner display names are resolved in one batched lookup that tries external contacts first then users. A value that is not id-shaped is echoed as the name (it is already a name). An id-shaped value that resolves to nothing stays empty so the screen shows an unassigned placeholder rather than a raw identifier. Failure of the lookup never blanks the register. _(ddl-beh-010; observed)_
- Per-source isolation: each source is collected independently; a broken or disabled source blanks only its own rows after the working transaction is rolled back. Each source reads at most a bounded number of rows, ordered by due date ascending so the most overdue fall inside the cap. For user-defined modules the cap is applied separately to overdue rows (newest overdue first) and to rows due inside the approaching window (soonest first), with projects taking turns so one project's backlog cannot hide another's reminders. _(ddl-beh-011; observed)_
- Payment-plan claims: a reached instalment on an in-force contract with no live (non-rejected) claim is due at reached date plus the instalment's lag days plus the contract's claim-within-days allowance (the destination chooses a default for contracts that do not set one; invalid, negative or boolean values fall back to that default). Payment-plan instalments: reached or invoiced instalments on active or completed contracts are due at their stored forecast due date. Pending and paid instalments never appear. Reminders go to project managers only, never to the client. _(ddl-beh-012; observed)_
- Each sweep pass also recomputes forecast dates of linked payment instalments whose stamp is missing or older than their schedule activity's last edit (never-stamped first, oldest next, bounded per pass, each in isolation) so the plan cannot stay wrong. _(ddl-beh-013; observed)_
- Overdue sweep (periodic, illustratively hourly; first run after the first interval): for every currently overdue item across all projects, notify the owner if the owner is an active, non-erased user; otherwise notify the project managers (project owner plus default-team members whose role designates managerial responsibility; inactive accounts dropped). If nobody qualifies, nobody is notified. _(ddl-beh-014; observed)_
- Nudge limits, derived from stored notifications rather than a separate table: an item is nudged at most once per spacing interval (illustratively most of a day), at most a small fixed number of times in its life, and only while it is no more than a bounded number of days late (illustratively about a week), so wiping stored notifications cannot restart reminders for old items. The overdue event for the timeline is published only after the nudge write has succeeded. _(ddl-beh-015; observed)_
- Escalation: an item that is later than an escalation grace period (illustratively a few days) and not later than an escalation horizon (illustratively around ten days) is escalated exactly once to the project managers other than its owner (a level marker recorded in notification metadata is also the de-duplication record); no managers beyond the owner means no escalation. An escalation announcement is published for the timeline. _(ddl-beh-016; observed)_
- Early reminders: only some sources get a reminder before the date passes: payment-plan instalments and correspondence (each with its own lead time) and user-defined modules (up to a bounded lead using each module's own setting). One reminder per due date per record and at most a small fixed number of distinct due dates per record (so a slipping forecast cannot become a perpetual mailer). Early reminders are sent after overdue handling and are not counted in the sweep's returned total. _(ddl-beh-017; observed)_
- Each notification created by the sweep is stored in-app with type overdue, escalated or approaching, relative link to the record, metadata naming the source, due date and level, and parameters (source name or label, title, days overdue or days until, plus for information requests, submittals, correspondence and variations the register number, project name and due date in the recipient's own date format). Those four sources use their own register-specific wording only when both a reference number and project name exist; others use generic wording. The same payload is routed to the email channel through the recipient's preferences (hourly/daily users get it in a digest). _(ddl-beh-018; observed)_
- Per-item isolation in the sweep: each item's nudge, escalation and reminder run in their own savepoint so one unwritable row cannot poison the pass; escalation failure does not roll back a nudge. All collection happens before any write. The sweep commits once and returns how many fresh overdue nudges it made. _(ddl-beh-019; observed)_
- Register screen: groups follow the server order, each header names the source area and item count; a row shows title, due date (date part only), a days chip (overdue by N days, due today, or due in N days), owner or an unassigned placeholder, and humanised status. Clicking or pressing Enter on a row opens its link. States: no project selected, loading, error with retry, and an empty state that explains dates must exist upstream. Changing segment refetches with that segment. _(ddl-beh-020; observed)_
- Register insights dataset: one row per item with title, source, owner (or an unassigned placeholder for blank), severity, standing, due month (sortable year-month, dash when absent), overdue flag, approaching flag and days late. Days late equals days overdue only for genuinely late items and is zero otherwise so averages are not dragged down by items not yet due. Built-in cards: items tracked, overdue total, approaching total, worst slip; charts: overdue by source, overdue by owner, severity split, average slip by source. No currency measure exists. Empty register yields no rows. _(ddl-beh-021; observed)_
- The timeline is a read view over a persisted activity log. A bridge listens to all in-process domain events, keeps only significant ones, maps each to one stored row and writes in bounded batches, never affecting the publisher (failures are logged and swallowed). _(ddl-beh-022; observed)_
- Significance is decided by event name only, using an allowlist made of whole event families plus individually named events drawn from otherwise noisy families. Coarsely, the origin favoured lifecycle, approval, cost, commercial, field, safety and quality events and excluded high-volume technical events. Non-string or empty names are not significant. Governing rules: every listed event must actually be published and must carry a project id at every publish site. The destination defines its own allowlist. _(ddl-beh-023; observed)_
- Mapping of an event to a row: module and record kind are derived from the leading segments of the dotted event name; action is the full event name verbatim; project comes from the payload's project identifier (more than one key spelling accepted); record id is taken from the payload using a fixed precedence that ends with any other identifier-like key that is not a project, tenant, parent, owner or actor reference; actor is taken from the first present of several actor keys but only if it parses as a user id (names or emails are dropped); a shallow copy of the payload is stored as metadata. A non-mapping payload is treated as empty. _(ddl-beh-024; observed)_
- A mapped row that has neither a project nor a record id is unreachable by any timeline query, so it is dropped with a warning instead of stored. _(ddl-beh-025; observed)_
- Project timeline membership: a row belongs to a project's timeline when its parent project equals the project, or when the row was logged directly against the project record itself. _(ddl-beh-026; observed)_
- Project timeline query: optional filters on module (several allowed), action (several allowed), record kind, acting user, and inclusive from/until bounds on creation time; bounded page size and offset of 0 or more. Response: entries, total under the same filters, and echoed limit and offset. Order is newest first with row id as a tiebreaker so paging neither drops nor repeats rows when many rows share a timestamp. _(ddl-beh-027; observed)_
- Record history query: given a project, a record kind and a record id, returns that record's rows newest first across every area, with total and the same paging limits. It is scoped to the project in the query itself because record ids are only unique by convention, so a user authorised for one project cannot read another project's history by guessing an id. _(ddl-beh-028; observed)_
- Timeline entry fields: id, record kind, record id, action, module, from-status, to-status, parent kind and id, actor id, reason, metadata map and creation time. _(ddl-beh-029; observed)_
- Timeline integrity rules are available to the validation engine over any slice of rows: a row with neither project nor record is an error (unreachable); a row on a project feed that names no record is a warning (cannot be opened); a row that lost an actor its payload named is a warning; a system event with no named actor is normal. _(ddl-beh-030; observed)_
- Timeline screen behaviour: fixed page size; module selector offers modules present on the loaded page; selecting a module, applying advanced filters, clearing, or switching project resets to the first page; the until date is treated as end of that day; search matches action, record kind, module and reason within the current page only; row shows actor name when resolvable (user list loaded only when the viewer may list users), a readable action label (module prefix and repeated words dropped, sentence case), module badge, record kind, status change, reason and relative time (just now, minutes, hours, days, then a calendar date after one week). Selecting a row toggles a detail panel with action, module, record kind and id, timestamp, actor or a system label, status change, reason, pretty-printed metadata and a go-to-record button when a route can be built. _(ddl-beh-031; observed)_
- Timeline screen summary: total events (server total), count of active modules and top modules and top actions on the loaded page; clicking a module in the summary filters by it. CSV export covers the currently shown (search-filtered) rows with fixed columns (date, action, module, record kind, record id, from status, to status, reason), quotes escaped by doubling, and is disabled when empty. A project must be chosen (route or active project) otherwise a prompt is shown. _(ddl-beh-032; observed)_
- Record links from the timeline: only a fixed set of record areas have a navigable route; rows from other areas show no link. Rows applied by the AI assistant link to the record they wrote: a stored in-app link wins if it is a same-app absolute path (paths starting with two slashes or a backslash, other origins and script schemes are rejected); a task row links to its project's task list with the record selected; an undo row never links; anything else has no link rather than a guessed one. _(ddl-beh-033; observed)_

## Inputs

- Register query: required project, segment all/overdue/approaching (default all), optional single-source filter, approaching window within a bounded range (destination chooses the default), limit within a bounded range. The sweep considers every project and uses a window of zero for overdue detection. _(ddl-in-001; observed)_
- Manual sweep: optional project scope in the request body, though the sweep itself is global across projects. _(ddl-in-002; observed)_
- Timeline project query inputs as in the behavior above; record-history query inputs are project, record kind, record id, limit, offset. _(ddl-in-003; observed)_

## Outputs

- Register response: capped items, overdue total, approaching total and generation time. Sweep response: number of fresh overdue nudges made. Timeline response: entries, total, limit, offset. _(ddl-out-001; observed)_

## States and transitions

- An item moves on time, then approaching (within the window), then overdue as days pass, and leaves the register when its source closes it; a date change in the source re-classifies it immediately. _(ddl-st-001; derived)_
- Per overdue item notification lifecycle: first nudge, further nudges after the spacing interval up to the nudge cap, one escalation after the grace period, silence after the nudge horizon (nudges) or the escalation horizon (escalation). _(ddl-st-002; derived)_

## Timing and ordering

- Illustrative parameters, all chosen by the destination: sweep interval of about an hour; nudge spacing of most of a day; nudge cap of a few; nudge horizon of about a week; escalation grace of a few days; escalation horizon of about ten days; early-reminder cap of a few distinct due dates; per-source early-reminder leads from a few days up to about a month; bounded per-source read cap; bounded forecast-recompute count per pass. Symbols used in scenarios: spacing S, nudge cap N, nudge horizon H, escalation grace G, escalation horizon E. _(ddl-time-001; observed)_
- Register order: overdue first, most overdue first, id as tiebreak; timeline order: newest first, id descending as tiebreak. _(ddl-time-002; observed)_
- Timeline persistence is batched and asynchronous relative to the publishing request; a short lag between an event and its appearance is expected. _(ddl-time-003; inferred)_

## Edge cases

- An item due today is approaching, not overdue, even at the first second after midnight in any zone, because only calendar dates are compared. _(ddl-edge-001; observed)_
- A corrective action whose parent non-conformance is missing is dropped for lack of project scope. _(ddl-edge-002; observed)_
- The reminder lead for user-defined modules is each record's own module setting up to a bounded maximum; a record outside its own lead window is not reminded even if inside the collection window. _(ddl-edge-003; observed)_
- A user-defined module without a status feature has no way to finish a record, so its records surface until the date is cleared; date-time due fields are compared at midnight UTC. _(ddl-edge-004; observed)_
- An owner id of a deleted or deactivated user falls back to project managers rather than failing the write. _(ddl-edge-005; observed)_
- Event kinds whose publishers send no project id are excluded from the timeline allowlist because they would be unreachable. _(ddl-edge-006; observed)_

## Errors

- Register and timeline access to a project the caller cannot open, or that does not exist, answers not-found (indistinguishable). Register access requires the read permission (any project member); the manual sweep requires manager level. _(ddl-err-001; observed)_
- Out-of-range window, limit or offset values and an unknown segment value are rejected as validation errors. _(ddl-err-002; observed)_
- Screens show a retryable load error for the register and a plain load error for the timeline. _(ddl-err-003; observed)_

## What it must not do

- The sweep never nudges forever, never reminds clients, never notifies inactive accounts, never escalates twice, and never lets a failing source blank the register or stop the sweep. _(ddl-neg-001; observed)_
- A source that owns its own overdue notifications may be flagged so that it appears in the register but is skipped by the sweep to avoid duplicate notifications. _(ddl-neg-002; observed)_
- The timeline does not record events outside the allowlist, events with no project and no record, or anything the log cannot reach; it never writes a record that was rolled back. _(ddl-neg-003; observed)_

## Security

- Register and timeline are project-scoped with the same project access rule as every project route; record history is additionally scoped by project in the query. Notifications written by the sweep are per user, so the global sweep leaks nothing across projects. _(ddl-sec-001; observed)_
- A stored link in a timeline row is followed only when it is a same-app absolute path. _(ddl-sec-002; observed)_

## Invariants

- Register counts equal the pre-segment, pre-cap classified totals; items listed never exceed the limit; no closed or undated item is listed. _(ddl-inv-001; observed)_
- Severity is critical exactly when overdue and warning exactly when approaching. _(ddl-inv-002; observed)_
- Every stored timeline row is reachable by at least one timeline query. _(ddl-inv-003; observed)_
- Timeline paging is stable: the same filters return a consistent total order across pages. _(ddl-inv-004; observed)_

## Notes

- Notification metadata (source, due date, level) written by the sweep is the de-duplication state; destination must keep an equivalent persisted record or the limits cannot be enforced across restarts. _(ddl-compat-001; derived)_
- The register's closing-state vocabularies come from sibling areas; destination should read each sibling's own closing states and keep the exclusion model. _(ddl-compat-002; derived)_
- All numeric windows, spacings, caps, limits and horizons in this spec are illustrative; the destination chooses its own values and need not match any stated number. _(ddl-compat-003; derived)_

## Non-goals

- No source code, identifiers or message strings are reproduced.
- Do not reproduce origin provenance markers.
- Exact visual design of the register, charts and timeline is not specified.
- The insights panel framework and the translation tables are outside this unit.
- The destination is not required to mirror the origin's module structure, naming or event vocabulary.

## Test cases

- **ddl-test-001**: Given a due date equal to today, tomorrow, and two days ago with a three-day window, when classifying, then results are approaching (0), approaching (-1) and overdue (2) with severities warning, warning and critical; a date four days ahead is on time.  
  Expected: Date-only arithmetic and window edges as stated.
- **ddl-test-002**: Given due values as a timestamp, a date text, a date-time text, a date-time text ending with the UTC marker, an empty string, and gibberish, then the first four reduce to dates and the last two mean no deadline without error.  
  Expected: Defensive parsing.
- **ddl-test-003**: Given an item whose status is in the source's closing set and another with an unknown status, both past due, then only the unknown-status item is listed.  
  Expected: Exclusion model.
- **ddl-test-004**: Given five overdue items with different lateness, three approaching items and a limit of four, when requesting all, overdue-only and approaching-only, then counts are five and three in every response, all lists the four most overdue first, and approaching-only lists the approaching items.  
  Expected: Pre-cap stable counts and ordering.
- **ddl-test-005**: Given two overdue items equally late, then ordering is stable by id across repeated queries.  
  Expected: Deterministic tiebreak.
- **ddl-test-006**: Given an information request owned by a role label and another by a real user, when listing, then the first has no owner and shows the unassigned placeholder; an id-shaped owner that matches nobody also shows the placeholder, while a free-text name is echoed.  
  Expected: Owner resolution rules.
- **ddl-test-007**: Given one source failing during collection, then rows from every other source are still returned.  
  Expected: Fail-soft per source.
- **ddl-test-008**: Given a reached instalment with lag 10 days on a contract whose claim allowance is 7 days, reached 20 days ago, with no claim, then it is overdue by 3 days; with a rejected claim only it is still listed; with a live claim it is not; a boolean or negative allowance falls back to the default.  
  Expected: Claim due-date calculation.
- **ddl-test-009**: Given a contract that is not yet in force, suspended or terminated, then its instalments never appear; an active or completed contract's reached or invoiced instalments appear at their forecast date.  
  Expected: Contract status gating.
- **ddl-test-010**: Given an overdue item with an active owner, when the sweep runs, then only the owner is notified, an overdue announcement is published, and the sweep returns one; running again within the spacing interval S notifies nobody.  
  Expected: Owner nudge and spacing.
- **ddl-test-011**: Given an item with no owner or a deactivated owner, then the project managers are notified; with no active managers, nobody is.  
  Expected: Fallback recipients.
- **ddl-test-012**: Given an overdue item for which stored notifications show N earlier nudges, then it is not nudged again; given an item later than the nudge horizon H with no stored nudges, then it is not nudged at all.  
  Expected: Nudge ceiling and horizon.
- **ddl-test-013**: Given an item later than the escalation grace G and within the escalation horizon E, with an owner and two other managers, then the owner is nudged and both managers are escalated to once; a second sweep escalates nobody; given the item is later than E, no escalation occurs.  
  Expected: Single escalation inside its window.
- **ddl-test-014**: Given a correspondence letter and a payment instalment each inside its own early-reminder lead, then each gets one early reminder; the same due date never repeats; a changed due date allows another up to the per-record cap of distinct due dates; a source not on the reminder list gets none.  
  Expected: Early reminder rules.
- **ddl-test-015**: Given an information request with a reference number and project name, then the reminder uses register-specific wording with the reference, project and recipient-formatted date; without a project name it uses generic wording.  
  Expected: Wording selection.
- **ddl-test-016**: Given one item whose write fails inside the sweep, then other items are still processed and the sweep completes.  
  Expected: Savepoint isolation.
- **ddl-test-017**: Given a temporary-works permit that is a draft, expired or closed, then it is not listed; an in-force permit past its validity end is overdue.  
  Expected: Permit gating.
- **ddl-test-018**: Given three items, one 12 days late, one due in 6 days and one 10 days late, then slip values are 12, 0 and 10; the overdue flag is set only for late ones; the owner shows the unassigned placeholder for a blank name; an empty register yields no rows and no currency measure.  
  Expected: Insights dataset rules.
- **ddl-test-019**: Given the register screen, when the payload has rows from two sources, then two group headers with counts and an owner name appear; an overdue row shows an overdue-by-two-days chip in the critical style; an empty payload shows the empty message and no table; pending shows loading; failure shows an error whose retry refetches; choosing the overdue segment refetches with the overdue filter.  
  Expected: Screen states.
- **ddl-test-020**: Given events with names inside an allowlisted family, outside it, and individually allowlisted, when the bridge sees them, then only the first and third are stored; a malformed payload does not raise.  
  Expected: Significance filter.
- **ddl-test-021**: Given an event payload with a generic id, a record-kind-specific id and a project id, then the stored row uses the generic id first; given only an unusual identifier-like key it is used unless it is the project, actor or owner reference; given an actor value that is an email, the actor is empty.  
  Expected: Mapping precedence.
- **ddl-test-022**: Given an event with no project and no record id, then it is dropped and a warning logged; given an event with only a record id it is stored.  
  Expected: Unreachable rows are not written.
- **ddl-test-023**: Given ten rows with the same timestamp, when paging with size three, then across four pages every row appears exactly once.  
  Expected: Stable paging.
- **ddl-test-024**: Given rows for a project (parent project equals project) and a row logged directly on the project record, then both appear; a row for another project does not; filters by module list, action list, actor and date range narrow the result and the total reflects them.  
  Expected: Membership and filters.
- **ddl-test-025**: Given the same record id used in two projects, when requesting one record's history under project A, then only project A's rows are returned.  
  Expected: Project-scoped record history.
- **ddl-test-026**: Given a user without access to the project, then both timeline queries and the register answer not-found; given a limit above the configured maximum, validation fails.  
  Expected: Access and bounds.
- **ddl-test-027**: Given validation rule input rows lacking project and record, lacking record only, and naming an actor lost from the row, then findings are error, warning and warning respectively; clean rows pass.  
  Expected: Rule severities.
- **ddl-test-028**: Given an assistant-applied row with a stored same-app link, a stored external link, a protocol-relative link, a script-scheme link, a task row without link, an undo row, and a row from an area with no route and no link, then results are the stored link, none, none, none, task-list link, none and none.  
  Expected: Link safety and fallbacks.
- **ddl-test-029**: Given the timeline screen with a date range ending on a given day, then events late on that day are included; given the CSV export with a quote in a reason, then the quote is doubled; given an empty page, export is disabled.  
  Expected: Filter end-of-day and CSV escaping.

## Open questions (decisions for QC Manager)

- What exact event families and named events belong in the persisted timeline set, and should the destination reproduce any origin set one-for-one or define its own?
- How are user-defined module due-date features declared (field, lead time, done states)? Only their effect on the register was observed.
- Which record-kind coverage is authoritative for the destination register? Origin explanatory copy and actual coverage were out of step with each other.
- How should module names shown in timeline filters be ranked, and which translation entries are needed for each area?
- Should destination keep an hourly sweep cadence and the global (not per-project) scope of the manual sweep?
- Should an expiry announcement for compliance documents be turned into notifications in the destination, given the origin deliberately did not, to avoid double-notifying?
