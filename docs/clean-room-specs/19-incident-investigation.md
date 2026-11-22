# 19. Incident investigations and CAPA

Spec `spec-incident-investigation-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Behaviour of formal incident follow-up: a root-cause investigation record attached to a safety incident (with a choice of analysis method, a three-state lifecycle and closure immutability), two corrective-action workflows (a lightweight incident-scoped four-step workflow and a project-level corrective and preventive action register with a structured why-chain and an effectiveness check), the incident record rules those workflows depend on, and neighbouring safety indicators and exports. Project isolation is enforced through the incident the work hangs off. Observed inconsistencies are listed as decision points in the open questions, not as requirements. All numeric limits, thresholds and tone cutoffs are indicative; the destination chooses its own values.

## Behaviour

- An investigation selects exactly one analysis method from four options: why-chain (default), cause-and-effect diagram (fishbone), timeline, or strengths/weaknesses/opportunities/threats. Any other value is rejected as invalid input. _(ii-b001; observed)_
- An investigation is created with status in progress by default; allowed statuses are in progress, completed and abandoned. Findings and recommendations default to empty text with a generous maximum length; leading and trailing whitespace in text inputs is trimmed. _(ii-b002; observed)_
- An optional report link on an investigation (bounded length) is accepted only when it is an http or https address, a site-relative path beginning with a slash, or a scheme-less value; any other scheme (script, data, file and similar) is rejected as invalid input. A blank link is treated as absent. _(ii-b003; observed)_
- Completing an investigation is allowed only from in progress; it sets status completed and stamps the completion time with the current instant. Abandoning is likewise allowed only from in progress, sets status abandoned and also stamps the closure time. Completing or abandoning an investigation that is already completed or abandoned is refused with a conflict outcome that names the current status. _(ii-b004; observed)_
- Both closing actions write a best-effort entry to the activity trail recording actor, the from-status, the to-status and the linked incident; a failure to write the trail entry never blocks or reverses the closing action. _(ii-b005; observed)_
- Listing investigations: when a project is supplied the list covers investigations whose linked incident belongs to that project (optionally filtered by status); when only an incident is supplied the list covers that incident; when neither is supplied an empty list is returned rather than an error. Paging applies with a default page size and an upper cap (the origin used a modest default and a cap of a few hundred; destination chooses). _(ii-b006; observed)_
- A lightweight corrective action belongs to an incident, carries a required description (non-empty, bounded length), an optional assignee and an optional due date, and always starts in the pending state when created, regardless of any status value supplied in the request. _(ii-b007; observed)_
- Verification notes supplied on a lightweight corrective-action transition are appended to the existing notes (separated by a line break) with a UTC timestamp and the target state as a prefix, so earlier notes are never overwritten. When the target state is verified, the verifying user and the verification time are recorded. _(ii-b008; observed)_
- Listing lightweight corrective actions: with an incident supplied, only that incident's actions are returned; with only a project supplied, actions of all incidents of that project are returned (empty when the project has no incidents); with neither, an empty list. A status filter and offset/limit paging apply. _(ii-b009; observed)_
- A project-level corrective and preventive action (CAPA) records its originating kind (incident, job safety analysis, permit, audit or observation), an optional originating record reference, a required title, a description, an optional owner, a required target date, a status (default open), and an optional root-cause category chosen from seven values: people, method, material, machine, environment, management, other. Text fields have bounded lengths. _(ii-b010; observed)_
- A structured why-chain can be recorded on a CAPA as an ordered list of question-and-answer pairs (each text non-empty and bounded). The chain must contain at least three and at most ten steps; fewer than three or more than ten is rejected as invalid input before the CAPA is even looked up. An optional root-cause category supplied with the chain updates the CAPA's category; omitting it leaves the category unchanged. _(ii-b011; observed)_
- Recording a why-chain on a completed or cancelled CAPA is refused with a conflict outcome, because the chain is part of the closure record. _(ii-b012; observed)_
- Completing a CAPA (manager-level action) records the completion time and any verification notes; escalating a CAPA moves it to overdue; cancelling moves it to cancelled. Each is allowed only where the CAPA state machine permits it, otherwise a conflict outcome naming the attempted hop is returned. Completion and escalation emit a notification for dashboards and write a best-effort activity-trail entry; cancel writes a trail entry only. _(ii-b013; observed)_
- An effectiveness check may be recorded only on a completed CAPA (otherwise conflict). It records the checking time and checker. If marked effective, optional notes are appended to the verification notes with an effective marker. If marked ineffective, the CAPA is reopened to in progress and a failed-check marker (with the notes when given) is appended to the verification notes. _(ii-b014; observed)_
- A CAPA whose target date is already in the past at creation produces a warning-level finding that is logged and retained but does not block creation. _(ii-b015; observed)_
- An incident record has: a title, a calendar date (real date in year-month-day form), optional location, a type (injury, near miss, property damage, environmental, fire), a severity (minor, moderate, major, severe, critical; default minor), a required description, optional injured-person details, optional treatment (first aid, medical, hospital, fatality), days lost (non-negative, bounded above by a very large upper limit, default 0), optional root-cause text, an embedded list of simple corrective-action entries (description, responsible person, due date, status open, in progress or completed), a regulator-reported flag, a status (reported, investigating, corrective action, closed; default reported), optional map coordinates within valid latitude and longitude ranges, and free-form extra attributes. _(ii-b016; observed)_
- Each incident receives a per-project human-readable number made of a fixed incident prefix and a zero-padded sequence one higher than the highest existing sequence in that project; entries with unparseable numbers are ignored when computing the next value, and a concurrent collision is retried a bounded number of times before failing. Whether numbers may be re-used after the highest-numbered incident is deleted is a decision point (see open questions). _(ii-b017; observed)_
- Incident dates are stored in a canonical year-month-day form. Incident listing is newest-created first, paged, and filterable by type and status; the total reflects the filtered set. _(ii-b018; observed)_
- Incident validation distinguishes errors (the write is refused with a coded invalid-input outcome) from warnings (the write proceeds, warnings retained). Errors: incident date later than today by more than one day of timezone slack; fatality treatment recorded with severity below major; lost days above zero on an incident type in which nobody is hurt (near miss, property damage, environmental). Warnings: fatality, hospital treatment or critical severity without the regulator-reported flag; closed status with severity major or higher and no root-cause text. _(ii-b019; observed)_
- A partial update to an incident re-checks only the fields it touches, merged over stored values; when the update does not change the date, the date rule is skipped so an old record with a now-rejected date can still be edited. A partial update of the free-form extra attributes is merged into the existing attributes rather than replacing them, because the per-incident exposure-hours figure used by frequency-rate indicators is kept there. _(ii-b020; observed)_
- Creating an incident sends a warning-type in-app notification to the project owner (body truncated to a short length, with a deep link to the incident) and publishes a creation notification for other consumers; a failure to notify is logged and does not fail the creation. _(ii-b021; observed)_
- Regulatory notification deadlines can be looked up per regulatory regime. For each regime the lookup returns severity classes, the roles to be notified, a maximum notification period and a reference to the governing regulation. The destination sources the supported regimes, severity classes and notification periods from applicable regulation and its maintainers; this specification lists no period values. Which regimes are accepted and which is the default is a destination decision. _(ii-b022; observed)_
- A recordable-incident log can be exported as comma-separated text for a chosen project and calendar year (within a plausible year range). Only incidents flagged as recordable and whose date begins with the requested year are included. Columns cover case number (falls back to the incident number), injured person name, job title, date, location, description (line breaks collapsed to spaces), days away, days restricted, a fatality yes/no column and an other-recordable yes/no column. The fatality column is yes only when treatment is fatality; other-recordable is yes only when not fatal and both days away and days restricted are zero or absent. Empty cells are blank. Download is an attachment named from a filename-safe slug of the project name (or project identifier) and the year. _(ii-b023; observed)_
- Frontend: the investigations register lives under the incidents area of the formal safety workspace (first of seven areas). It supports a text search over incident reference and findings, shows loading placeholders, a recoverable error card with retry, and an empty state offering to open an investigation. Creating one asks for the incident reference, a start date, the method and optional findings. _(ii-b024; observed)_
- Frontend: arriving from the incident screen with an investigate intent and an incident identifier opens the creation form pre-filled with that incident exactly once; the intent parameters are then removed from the address so refresh or back-navigation does not repeat it. An address parameter selects the initial area; unknown values fall back to incidents. Areas are reachable by keyboard arrow navigation and expose tab semantics. _(ii-b025; observed)_
- Frontend headline strip: open investigations counts those not completed and not abandoned; overdue corrective actions counts those whose target date is before today and whose status is neither completed nor cancelled; active permits counts permits in active status; days since last lost-time incident is read from the server. Tone rules (cutoffs illustrative, destination chooses): a short streak reads as error, a moderate streak as warning, a long streak as success, no data neutral; overdue count zero success, otherwise error. If the list sources fail the strip is hidden; if only the summary fails the days figure shows no record. _(ii-b026; observed)_

## Inputs

- Investigation creation requires an incident reference (identifier) and a start timestamp; lead person, method, findings, recommendations, status and report link are optional with defaults. _(ii-i001; observed)_
- Investigation partial update may change lead, completion time, method, findings, recommendations, status and report link; it cannot change the linked incident. _(ii-i002; observed)_
- Lightweight corrective-action transition input is a target state (one of pending, in progress, verified, closed) and optional notes of bounded length. _(ii-i003; observed)_
- Effectiveness input is an effective flag (default true) and optional notes of bounded length; completion input is optional verification notes of bounded length. _(ii-i004; observed)_

## Outputs

- Investigation responses expose identifier, incident reference, lead, start, completion, method, findings, recommendations, status, report link and created/updated times. CAPA responses additionally expose the why-chain, root-cause category, effectiveness check time and checker. _(ii-o001; observed)_
- Incident responses also expose recordable flag, case number, days away, days restricted, root-cause method and root-cause tags, alongside the core incident fields; incident lists return items with total, offset and limit. _(ii-o002; observed)_

## States and transitions

- Investigation: in progress to completed (complete action) and in progress to abandoned (abandon action) are the only action-driven transitions; completed and abandoned are terminal for the actions. _(ii-t001; observed)_
- Lightweight corrective action: pending to in progress, in progress to verified, verified to closed; no skipping, no backward moves, closed is terminal. Any other target is a conflict whose message names the rejected hop and lists the allowed next states (or none). _(ii-t002; observed)_
- CAPA: open may go to in progress, completed, overdue or cancelled; in progress to completed, overdue or cancelled; overdue to in progress, completed or cancelled; completed and cancelled are terminal except that a failed effectiveness check reopens a completed CAPA to in progress. _(ii-t003; observed)_
- A general edit of a CAPA cannot move it to completed, cancelled or overdue (those require the dedicated actions) and cannot leave a terminal state; moving to any other state must follow the state machine. Only real changes are refused, so a form that resends the stored status or notes unchanged still saves its other fields. _(ii-t004; observed)_
- Incident status vocabulary runs reported, investigating, corrective action, closed. The origin applies no transition guard to incident status beyond the vocabulary and the closed-needs-root-cause warning; whether to add guards is a decision point. _(ii-t005; observed)_

## Timing and ordering

- For a why-chain request the step-count bounds are evaluated before the CAPA is loaded and before the closure-record check; for lightweight corrective-action and CAPA transitions the project-access check runs before the state-machine check so an invalid-hop message cannot confirm a foreign record. _(ii-o003; observed)_
- Project-access checks on investigation actions run before the immutability or state conflict is evaluated. _(ii-o004; observed)_

## Edge cases

- Content edits (findings, recommendations, method, lead, report link) to a completed or abandoned investigation are refused with a conflict explaining that closed records are immutable. How a mistakenly closed investigation is reopened is a decision point (see open questions). _(ii-e002; observed)_
- The verification notes and root-cause category of a completed or cancelled CAPA cannot be changed by a general edit when the value differs from the stored one; an unchanged value is tolerated. _(ii-e003; observed)_
- A completed or cancelled CAPA cannot be deleted (it is the closure record); an open CAPA raised by mistake should be cancelled instead. Deleting writes a best-effort trail entry containing a snapshot (project, truncated title, status). _(ii-e004; observed)_
- The incident screen's days-lost input is clamped to the permitted range: values above the upper bound become the bound, negative or empty or non-numeric input becomes zero, ordinary values pass through. _(ii-e005; observed)_
- Incident indicators that rely on exposure hours treat missing, non-numeric or non-positive hour values as zero rather than corrupting a denominator; a non-numeric value is logged and ignored. _(ii-e006; observed)_
- When incidents exist but none has a parseable date, the days-without-incident indicator is reported as unconfirmed (no number) rather than a large or blank reassuring value; with no incidents at all it reports none; unparseable dates are counted and surfaced. _(ii-e007; observed)_

## Errors

- Unknown investigation, corrective action, CAPA or incident identifiers yield not-found outcomes; a record belonging to a project the caller cannot access also yields not-found so existence is not revealed. _(ii-x001; observed)_
- Invalid state hops, closure-record edits, terminal deletions and effectiveness checks on non-completed CAPAs return conflict outcomes; out-of-vocabulary values, unsafe links, short or long why-chains and incident rule errors return invalid-input outcomes. _(ii-x002; observed)_

## What it must not do

- Creating a lightweight corrective action does not honour a requested status other than pending; no transition other than the single forward step is ever accepted. _(ii-n001; observed)_
- The incident create and update inputs do not accept the root-cause method or root-cause tags attributes, although they are readable on responses. _(ii-n002; observed)_

## Security

- Permission tiers for investigations: viewing requires viewer level, creating and general editing editor level, completing or abandoning manager level. For CAPAs: viewing viewer, creating, editing, cancelling and recording a why-chain editor, completing, escalating and effectiveness checks manager, deleting manager. For lightweight corrective actions: viewing viewer, creating and transitioning (including verifying and closing) editor level. _(ii-sec001; observed)_
- Investigations and lightweight corrective actions have no project of their own; every read, create, edit and action resolves the project through the linked incident and applies the project-access check, so another project's incident cannot be investigated, listed or driven by quoting its identifier. _(ii-sec002; observed)_
- Project-scoped lists for CAPAs and the other registers apply the project-access check; the recordable-incident export requires viewer permission plus project access. _(ii-sec003; observed)_
- State changes and destructive operations are funnelled through a best-effort activity trail so that an auditor can answer who closed or deleted a record and when; trail failures are swallowed. _(ii-sec004; observed)_

## Invariants

- A closed investigation's content cannot change through a content edit; a closed CAPA's closure record (notes, root-cause category, why-chain) cannot be rewritten or deleted except through the explicit reopen-on-failed-check path. _(ii-inv001; observed)_
- Corrective-action notes are append-only through transitions and effectiveness checks. _(ii-inv002; observed)_
- Incident numbers are unique per project; the next number is always one above the highest existing sequence, so deleting a non-highest incident never produces a duplicate. _(ii-inv003; observed)_
- Observation and incident risk tier boundaries are identical, using a five-by-five matrix: score is severity times likelihood (each 1 to 5); illustrative tiers are 1 to 5 low, 6 to 10 medium, 11 to 15 high, 16 to 25 critical. An observation in the top two tiers triggers a high-risk notification on creation, and on update only when the score crosses upward from the lower tiers into the higher ones. _(ii-inv004; observed)_

## Notes

- Frequency-rate indicators in the safety statistics follow common public safety-statistics conventions: total recordable rate is the recordable count times 200000 divided by total exposure hours; lost-time frequency rate is the lost-time count times 1000000 divided by hours; both rounded to two decimals and both absent (not zero) when total hours are not positive. An incident is recordable when its recordable flag is set or its treatment is medical, hospital or fatality; lost-time when days lost exceed zero. Hours come from a per-incident exposure figure kept in the free-form extra attributes. _(ii-cn001; observed)_
- Threshold banding of a rate against a safe baseline (all numbers illustrative, destination chooses): unknown when no rate; green at or below baseline; yellow above baseline up to an upper margin expressed as a percentage of the baseline; red above that margin; with a zero baseline any positive rate is red. Baselines are configurable per indicator. A non-green overall band publishes a threshold notification; the worst band picks the headline message. _(ii-cn003; observed)_
- Trend direction over the most recent few periods that have a computed lost-time rate uses a least-squares slope with a small symmetric dead-band (illustrative): clearly negative improving, clearly positive declining, otherwise stable; too few usable periods is unknown. Period keys are year-month or ISO year-week; incidents with unparseable dates fall into one unknown bucket that is excluded from rolling averages (roughly twelve months or fifty-two weeks). _(ii-cn004; observed)_
- All numeric limits in this specification (text lengths, page sizes and caps, ranges, retry counts, timezone slack, tone cutoffs, baselines, margins, slopes) are indicative behavioural parameters; the destination chooses its own values. The frequency-rate multipliers are public safety-statistics conventions and may be kept. _(ii-cn005; derived)_

## Non-goals

- Reproducing the origin's tables, field names, route layout, permission identifiers, event names or notification keys.
- Reproducing the origin's user-facing wording, translations or visual design.
- Specifying regulatory notification tables or periods; the destination sources them from applicable regulation.
- Hazard registers, toolbox talks, certifications and the project frame that sit beside this workflow.
- Do not reproduce origin provenance markers.

## Test cases

- **ii-test-001**: Given an incident exists in a project the caller can access, when the caller opens an investigation naming that incident with no method chosen, then it is created in progress with the why-chain method and empty findings.  
  Expected: Success outcome for creation; status in progress; method is why-chain; findings and recommendations empty.
- **ii-test-002**: Given an investigation request with a method outside the four allowed options, when it is submitted, then it is rejected as invalid input.  
  Expected: Invalid-input outcome; nothing stored.
- **ii-test-003**: Given a report link using a script or data scheme and another using a plain https address, when each is submitted on a new investigation, then the first is rejected and the second accepted.  
  Expected: Unsafe scheme rejected as invalid input; https and site-relative links accepted; blank treated as no link.
- **ii-test-004**: Given an in-progress investigation and a manager, when it is completed, then status becomes completed with a completion time; when the same action is repeated, then a conflict naming the current status is returned.  
  Expected: First call succeeds with completion time set; second returns conflict; abandon behaves the same and also stamps a closure time.
- **ii-test-005**: Given a completed investigation, when an editor patches its findings, then the patch is refused with a conflict.  
  Expected: Content patch conflicts; the closed content is unchanged. Reopen handling is left to the destination decision.
- **ii-test-006**: Given an investigation linked to an incident of another project that the caller cannot access, when the caller reads, edits or completes it, then not-found is returned every time, including for an invalid action.  
  Expected: Opaque not-found; no conflict message that would confirm existence.
- **ii-test-007**: Given neither a project nor an incident scope in the list request, when investigations are listed, then an empty list is returned.  
  Expected: Empty list, success outcome.
- **ii-test-008**: Given a new lightweight corrective action created with a requested status of closed, when it is read back, then it is pending; when moved straight to verified, then a conflict names the hop and the only allowed next state.  
  Expected: Status pending on creation; skip refused with conflict listing in progress as allowed.
- **ii-test-009**: Given a lightweight corrective action moved to in progress then to verified with notes at each step by a known user, when read, then it shows the verifier and verification time and a notes history containing both entries in order with timestamps and target-state prefixes.  
  Expected: Notes appended, never overwritten; verifier and time set on entering verified only.
- **ii-test-010**: Given a project with two incidents each having corrective actions and a status filter, when actions are listed by project, then actions of both incidents appear, filtered by status; a project with no incidents returns an empty list.  
  Expected: Project-wide aggregation through incidents; empty when none.
- **ii-test-011**: Given a CAPA with two why-chain steps, when recorded, then invalid input is returned; with eleven steps, invalid input; with three steps and a root-cause category, success and the category is updated; with three steps and no category, the stored category is unchanged.  
  Expected: Bounds 3 to 10 enforced; category optional.
- **ii-test-012**: Given a completed CAPA, when a general edit tries to set status to open, change the verification notes or record a why-chain, then each is refused with a conflict; when the same edit resends unchanged notes plus a new title, then it succeeds.  
  Expected: Closure record protected; unchanged values tolerated.
- **ii-test-013**: Given an open CAPA, when a general edit tries to set status to completed, cancelled or overdue, then a conflict names the dedicated action; when it sets in progress, it succeeds.  
  Expected: Action-only statuses refused on edit; permitted hop accepted.
- **ii-test-014**: Given a completed CAPA, when an effectiveness check says ineffective with notes, then the CAPA returns to in progress with a failed marker appended; given an open CAPA, when an effectiveness check is attempted, then a conflict is returned.  
  Expected: Reopen path works only from completed; notes appended.
- **ii-test-015**: Given a completed CAPA, when a delete is attempted, then a conflict is returned; given an open CAPA, when deleted, then it is removed and a trail entry with a snapshot is written best-effort.  
  Expected: Terminal CAPA kept; open CAPA deletable.
- **ii-test-016**: Given an incident with fatality treatment and minor severity, when it is created, then it is refused; with a near-miss type and two lost days, refused; with a hospital treatment and no regulator flag, accepted with a warning.  
  Expected: Errors block; warnings do not.
- **ii-test-017**: Given an incident dated several days in the future, when created, then refused; dated tomorrow, accepted (timezone slack); when later patched without touching the date, no date rule runs.  
  Expected: One-day slack; patch skips untouched-date rule.
- **ii-test-018**: Given existing incident numbers with sequences 1 and 3 and one malformed number in a project, when a new incident is created, then its sequence is 4; sequence 2, which was never used or was removed earlier, is not assigned to a new incident while a higher number exists.  
  Expected: Next sequence is maximum plus one over existing numbers; malformed numbers ignored; no duplicate numbers.
- **ii-test-019**: Given incidents with 1 recordable and 1 lost-time among 400000 total hours, when statistics are requested, then total recordable rate is 0.5 and lost-time frequency rate is 2.5; with no hours, both are absent.  
  Expected: Rates per the formulas, two decimals; absent without hours.
- **ii-test-020**: Given an illustrative baseline of 2.0 and an illustrative upper margin of 150 percent of baseline, when a current rate of 2.0 is banded it is green, 2.5 is yellow, 3.5 is red, and an absent rate is unknown.  
  Expected: Band boundaries at the baseline and at the margin above it; unknown without a rate.
- **ii-test-021**: Given an incident that is recordable and fatal in a given year and another non-recordable one, when the recordable-incident export for that year is requested, then only the first appears with the fatality column yes and other-recordable no; a different year returns only the header.  
  Expected: Filter by flag and year; derived yes/no columns; attachment filename from project slug and year.
- **ii-test-022**: Given the days-lost input receives an enormous number, a negative number, an empty string and an ordinary number, then it yields the upper bound, zero, zero and the ordinary number.  
  Expected: Clamped to the permitted range.
- **ii-test-023**: Given the workspace is opened with an investigate intent and an incident identifier, when it loads, then the creation form opens pre-filled once and the intent parameters disappear from the address; reloading does not reopen it.  
  Expected: One-shot pre-fill; address cleaned.
- **ii-test-024**: Given three investigations (one in progress, one completed, one abandoned) and one CAPA overdue by target date and one completed past its date, when the strip loads, then open investigations is 1 and overdue is 1.  
  Expected: Counts follow the stated rules.
- **ii-test-025**: Given an editor-level user, when they try to complete an investigation or a CAPA, then permission is denied; a manager succeeds.  
  Expected: Closing actions need manager level; lightweight corrective-action verification needs only editor level (see open question).

## Open questions (decisions for QC Manager)

- Decision: should the destination keep the incident-level root-cause method and tag attributes as writable? The origin stores and returns them but accepts no input for them, and the vocabulary documented for the stored method includes a structured cause-tree technique that the investigation does not offer. Which method vocabulary should the destination use?
- Decision: the origin lets a general edit of an investigation set status without any transition check, and reopening does not clear the earlier completion time. Should the destination require a dedicated reopen action that clears completion time and records an audit entry?
- Decision: the origin does not verify that the incident named on a new investigation exists, and skips the project-access check when it cannot be resolved. Should the destination reject unknown incident references?
- Decision: any editor can verify and close lightweight corrective actions (the same permission as creating them), whereas project CAPAs require manager level to close and to check effectiveness. Should verification and closure of the lightweight workflow be restricted to a higher role or to someone other than the assignee?
- Decision: two corrective-action workflows coexist (incident-scoped four-step and project-level CAPA). Should the destination merge them into one, and if so which state machine and permission tiers apply?
- Decision: the origin has two safety-rate calculations that disagree. The statistics variant treats an incident as recordable when the flag is set or treatment is serious, rounds to two decimals and reports absent rates when hours are not positive. The key-indicator variant takes hours as a request parameter, ignores the flag and counts by treatment or lost days, rounds to more decimals, and reports zero rates when hours are zero. Which definition is authoritative for the destination?
- Decision: the origin's incident rules treat fire incidents inconsistently (not listed among types with no injured person, while the stored type vocabulary differs from the rule wording for injury); confirm the intended type vocabulary and which types may carry lost days.
- Decision: investigation methods, why-chain bounds and CAPA categories reflect lean and regulatory guidance; confirm whether the destination should use the same bounds and vocabularies or the organisation's own.
- Decision: confirm which regulatory regimes the destination must support for notification deadlines, who maintains the periods, and how they are sourced from applicable regulation.
- Decision: the origin reuses an incident number when the highest-numbered incident is deleted; should the destination guarantee that numbers are never re-issued?
- Unknown: how the origin's investigation detail view presents completion, abandonment and report links was not inspected in this pass.
