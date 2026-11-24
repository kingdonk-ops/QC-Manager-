# 20. JSA, permits to work, PPE, audits

Spec `spec-hse-permits-audits-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Behaviour of the formal on-site safety registers: job safety analyses (hazard steps, risk score, approval lifecycle, reusable templates), permits to work (typed prerequisites, controlled lifecycle, work window and expiry display), personal protective equipment issue tracking (a company-wide register), and safety audits with weighted findings and scoring. Neighbouring toolbox talks, worker certifications and key indicators are summarised only as context. Observed inconsistencies are carried as decision points, not requirements. All numeric limits, weights and thresholds are illustrative; the destination chooses its own values.

## Behaviour

- A job safety analysis (JSA) belongs to a project and records a task description (non-empty, bounded), optional location, a work date in year-month-day form, an optional preparer, a list of hazard entries, a list of required protective equipment names, a status (default draft), a risk score, and approver and approval time once approved. _(hpa-b001; observed)_
- Each hazard entry has a step description, a hazard description (both non-empty, bounded), severity 1 to 5 (default 1), likelihood 1 to 5 (default 1) and controls text (bounded). _(hpa-b002; observed)_
- A JSA's risk score is the highest severity-times-likelihood product among its hazards (each factor clamped to 1 to 5, unusable entries skipped); an analysis with no hazards scores 0. The score is recomputed whenever hazards are replaced, including when a template is cloned. Illustrative tiers on the five-by-five matrix: scores up to 5 low, 6 to 10 medium, 11 to 15 high, 16 and above critical. _(hpa-b003; observed)_
- Submitting a JSA moves it to under review and publishes a notification with its risk score. Approving (manager level) is allowed only from under review, records the approving user and time and publishes a notification. Activating moves approved to active; archiving is allowed from any non-archived state per the state machine. _(hpa-b004; observed)_
- Content edits to a JSA (task, location, work date, hazards, equipment list) are refused with a conflict unless it is draft or under review, with a hint to revert to draft; approval metadata would otherwise point at changed content. A successful edit writes a best-effort trail entry listing the changed field names. _(hpa-b005; observed)_
- A JSA that is approved, active or archived cannot be deleted (conflict, with advice to archive instead, or a note that an archived one is kept as the record); draft and under-review analyses can be deleted by a manager, with a trail entry holding a snapshot of project, status and a truncated task description. _(hpa-b006; observed)_
- A reusable JSA template library exists at company scope: trade, name, task description, hazard list, equipment list, optional region code, active flag (default true) and a positive integer version. Templates can be listed (filter by trade, region and an active filter that defaults to active only and can also select both or inactive), created, edited and deleted by manager level; read access is viewer level. Text fields have bounded lengths. _(hpa-b007; observed)_
- Cloning a template into a project (requires create permission and project access) copies task, hazards and equipment into a new draft JSA using the supplied work date, optional location and optional preparer, recomputes risk, and publishes a notification with template, new analysis and hazard count. An inactive template cannot be cloned (bad-request outcome); an unknown template is not found. _(hpa-b008; observed)_
- A permit to work (PTW) belongs to a project and records a required permit number (non-empty, bounded), a type from eight options (hot work, confined space, work at height, electrical, excavation, lifting, lockout-tagout, other), description, optional location, a work start and end (timestamps), optional applicant, supervisor and linked JSA, conditions text, approval time and approver, closure checklist flag and notes, and five prerequisite flags (approved JSA, fire watch assigned, extinguisher present, supervisor present, atmospheric test passed). _(hpa-b009; observed)_
- Requesting a permit always creates it in requested state with closure flag false and empty closure notes. A work end that is not strictly after the work start is rejected as invalid input, at creation and whenever an edit changes either bound. A notification is published on request. _(hpa-b010; observed)_
- Window-length warnings (non-blocking, retained as findings): permits of higher-hazard types (hot work, confined space) warn when their work window exceeds a short per-type limit, and any permit warns when its window exceeds a long global limit. The warning compares the work window length to the limit for the permit type. The limit values are illustrative configuration candidates (the origin used one day for the higher-hazard types and about a month globally). _(hpa-b011; observed)_
- Required prerequisites before a permit can become active depend on its type: hot work needs approved JSA flag, fire watch assigned and extinguisher present; confined space needs approved JSA flag, supervisor present and atmospheric test passed; work at height, excavation, electrical, lifting and lockout-tagout each need approved JSA flag and supervisor present; other needs only the approved JSA flag. An unknown type falls back to the approved-JSA requirement only. _(hpa-b012; observed)_
- Activating a permit (editor level) requires the state machine to allow it, every prerequisite for its type to be true (otherwise a conflict listing the unmet prerequisites), and, when a JSA is linked, that JSA to be approved or active (otherwise conflict). On success the permit becomes active and a notification is published. Whether the approved-JSA prerequisite should be derived from the linked analysis is a decision point (see open questions). _(hpa-b013; observed)_
- A prerequisite status view reports, for a permit, the required prerequisites, those met, those missing, and whether it is ready to activate (no missing). Prerequisite flags can be changed by an editor-level user only while the permit is requested, approved or suspended; only supplied (non-null) flags are applied. _(hpa-b014; observed)_
- Approving a permit (manager level) records approver and time and, when conditions text is supplied, replaces the conditions; a notification follows. Suspending is editor level and moves active to suspended; resuming is an activation from suspended, so prerequisites and the linked-JSA check are re-run. Cancelling is editor level and allowed from requested, approved, active or suspended. _(hpa-b015; observed)_
- Closing a permit (manager level) is allowed from active or suspended and requires the closure checklist to be confirmed true (otherwise invalid input); it stores the notes, sets closed and publishes a notification. State validity is evaluated before the checklist condition. _(hpa-b016; observed)_
- General edits to a permit (description, location, window, supervisor, linked JSA, conditions) are allowed only in requested, approved or suspended states; otherwise conflict. Successful edits write a best-effort trail entry listing changed field names. Deleting a permit is manager level and writes a trail entry with a snapshot (project, number, status); which states permit deletion is a decision point (see open questions). _(hpa-b017; observed)_
- A permit dashboard for a project groups permits: those active and in force today, those requested (pending, bounded list size) and those closed whose last update falls on the current UTC date. _(hpa-b018; observed)_
- A protective equipment (PPE) issue records optional recipient user or free-text recipient name and company, issue time, optional issuer, type from eight options (hard hat, safety boots, gloves, harness, respirator, high-visibility clothing, glasses, other), optional size, brand, serial, optional valid-until date, return time, and status (issued by default, in use, returned, lost, damaged). _(hpa-b019; observed)_
- The PPE register is company-wide: an issue record has no project and every project shows the same list. The PPE area shows a note explaining this and the area's tab carries a hover hint with the same meaning. The note must be available in every fully supported language, and untranslated source-language text is not acceptable in a non-source language. _(hpa-b020; observed)_
- PPE date rules (errors): a return time earlier than the issue time is refused; a valid-until date earlier than the issue day is refused. The rules run on issue and whenever a return time or validity date is edited, using the stored issue time for the comparison. _(hpa-b021; observed)_
- The return action sets status returned and the return time to now; whether it may be applied to an already returned record is a decision point. PPE can be filtered by recipient and status and paged with a default and a cap. Issuing requires editor level with a dedicated issuing permission, viewing viewer level, editing editor level, deleting manager level. No project-access check applies (see open questions). _(hpa-b022; observed)_
- A safety audit belongs to a project with a type (internal, external, regulatory, site walk; default internal), conducted time, optional auditor, status (scheduled by default, in progress, completed, cancelled), summary (bounded), optional checklist template reference, and a score and maximum score once computed. _(hpa-b023; observed)_
- An audit finding has an item description (non-empty, bounded), category (PPE, permit, housekeeping, electrical, fire, environmental, other; default other), severity (low, medium, high, critical; default low), a passed flag (default true), an optional evidence link (same safe-link rule: http, https or relative; other schemes rejected) and an optional reference to a corrective action. Adding findings requires audit-conducting (manager) permission and project access via the parent audit; deleting a finding needs delete permission and the same project resolution. _(hpa-b024; observed)_
- Audit scoring: each finding has a weight by severity that rises with severity (illustrative weights of 1, 2, 4 and 8 for low, medium, high and critical; destination chooses); the maximum score is the sum of all weights, the score is the sum of weights of passed findings, and the percentage is score over maximum times 100 rounded to two decimals; with no findings all three are zero. _(hpa-b025; observed)_
- Completing an audit (manager level) is allowed only from in progress (otherwise conflict); it recomputes and stores score and maximum from persisted findings, sets completed, publishes a notification with score and maximum, and writes a trail entry. How an audit reaches in progress is a decision point (see open questions). _(hpa-b026; observed)_
- Frontend audits area: a detail view lists findings, allows adding and deleting findings, completing the audit, and raising a corrective action from a specific finding (the corrective-action creation form opens with its source locked). _(hpa-b027; observed)_
- Permits area (frontend): filter chips for all, requested, active and expired with counts, plus text search over description and permit number; a table of number, description, type, status badge, work end date and an expiry countdown. Countdown tone (cutoffs illustrative): end in the past shows days-ago in the error tone; end today or tomorrow shows today in the error tone; end within a few days warning tone; otherwise neutral; absent end shows a dash. Loading placeholder, recoverable error card and empty state with an issue-permit action are provided. _(hpa-b028; observed)_
- Permit detail (frontend): shows type, status, description, window, conditions and an expiry countdown card; a footer offers only the actions valid for the current status (and a hint that no actions remain for terminal permits); closing first opens a dialog asking for closure notes and explaining the closure is recorded in the audit trail. The prerequisite checklist is editable only while requested or approved, and shows each of the five prerequisite flags. _(hpa-b029; observed)_
- Context only: toolbox talks record topic, time (not in the future beyond a small timezone slack), leader, language, notes and attendees (role worker, foreman or visitor; status present, absent or late) with an attendance count that grows when attendees are added; a topic library has a unique code (duplicate gives a conflict), category general, hazard specific or regulatory, a bounded duration and an active flag. Worker certifications have a type, issue date, valid-until date not earlier than issue, status valid, expired or revoked, and an expiring-soon lookup with a configurable look-ahead that publishes a dashboard notification when non-empty. _(hpa-b030; observed)_
- Context only: a project dashboard summarises counts of analyses, active permits, overdue and open corrective actions, completed audits, talks in the current month, certifications expiring within a configurable window (company-wide), and the average audit percentage across completed audits with a positive maximum (two decimals, absent when none). A separate key-indicator view takes hours worked as a parameter and reports total recordable rate, lost-time frequency rate and days without a lost-time incident. _(hpa-b031; observed)_

## Inputs

- JSA create requires project, task description and work date; update accepts task, location, work date, hazards, equipment and status. Permit create requires project, number, type, work start and end; permit update cannot change type or number. Audit create requires project and conducted time; audit update may change type, time, score fields, status and summary. _(hpa-i001; observed)_
- All text inputs are trimmed of leading and trailing whitespace. _(hpa-i002; observed)_

## Outputs

- Permit responses expose all permit fields plus the five prerequisite flags and created/updated times; the prerequisite status view exposes the permit identifier and type, required, met and missing lists and a ready flag. _(hpa-o001; observed)_
- Audit responses expose score, maximum, status and summary; a computed score response (passed count, failed count, score, maximum, percentage) exists as a shape. _(hpa-o002; observed)_

## States and transitions

- JSA: draft to under review or archived; under review to approved, draft or archived; approved to active or archived; active to archived; archived terminal. _(hpa-t001; observed)_
- Permit: requested to approved or cancelled; approved to active or cancelled; active to suspended, closed or cancelled; suspended to active, closed or cancelled; closed and cancelled terminal. The permit status vocabulary also contains an expired value, but no action in the origin moves a permit there (see open questions). _(hpa-t002; observed)_
- Audit: scheduled to in progress or cancelled; in progress to completed or cancelled; completed and cancelled terminal. _(hpa-t003; observed)_
- Certification: valid to expired or revoked; expired to valid; revoked terminal. (Context only.) _(hpa-t004; observed)_

## Timing and ordering

- For every project-owned record action the project-access check runs before the state or content conflict is evaluated, so conflicts never reveal a record the caller cannot see. _(hpa-o003; observed)_
- Permit activation checks, in order: state machine, prerequisite flags, linked-analysis status; closing checks the state machine before the closure confirmation. _(hpa-o004; observed)_

## Edge cases

- A permit past its work window stays in whatever status it had; no automatic expiry transition exists. A permit counts as in force when its status is active and now lies within the window (start and end inclusive, naive times assumed UTC), but the origin does not surface this determination anywhere user-facing. _(hpa-e001; observed)_

## Errors

- Unknown JSA, permit, audit, template, topic, PPE or certification identifiers give not-found; records in a project the caller cannot access give not-found. _(hpa-x001; observed)_
- Invalid state hops, unmet prerequisites, edits to frozen records, deletion of signed JSAs and duplicate topic codes give conflicts; bad window ordering, missing closure confirmation, date-order rule violations and out-of-vocabulary values give invalid-input outcomes; cloning an inactive template gives a bad-request outcome. _(hpa-x002; observed)_

## What it must not do

- A permit cannot be activated without its type's prerequisites even by a manager; a permit cannot be closed without the closure checklist confirmation. _(hpa-n001; observed)_

## Security

- Permission tiers: viewing viewer level; creating and general editing editor level; deleting manager level; approving JSAs and permits, closing permits, conducting or completing audits, closing and escalating corrective actions, and recording effectiveness checks manager level; activating permits, updating prerequisites and issuing protective equipment editor level; template reads viewer, template writes and deletes manager. _(hpa-sec001; observed)_
- Permission alone does not prove access to a specific project; every project-owned record operation additionally checks project access (non-members get not-found, indistinguishable from missing) to prevent cross-project guessing of identifiers. Company-wide registers (protective equipment, certifications, topic library, templates) rely on permission only. _(hpa-sec002; observed)_
- Evidence and report links rejecting non-web schemes prevent stored script injection when links are rendered. _(hpa-sec003; observed)_
- Updates, deletions and state changes on JSAs, permits and audits write best-effort activity-trail entries; failures there are swallowed. _(hpa-sec004; observed)_

## Invariants

- A permit's work end is always strictly after its work start. _(hpa-inv001; observed)_
- An approved, active or archived JSA's content cannot be altered by a content edit nor deleted. _(hpa-inv002; observed)_
- A permit enters active only with all type-required prerequisites true at that moment. _(hpa-inv003; observed)_
- Audit percentage is always between 0 and 100 and zero when there are no findings. _(hpa-inv004; derived)_

## Notes

- Permit prerequisite sets and window-length limits are domain safeguards derived from published occupational-safety practice; the prerequisite sets are behaviour requirements for the destination but all numeric figures (limits, weights, tier cutoffs, tone cutoffs, paging sizes, text lengths) are illustrative configuration candidates that the destination chooses. _(hpa-cn001; inferred)_

## Non-goals

- Reproducing origin table, field, route, event or permission identifiers or user-facing wording.
- Reproducing the origin's seed demonstration data or translations.
- Scaffold and temporary works permits (separate unit) and incident investigation and corrective-action workflows (separate unit).
- Re-implementing any project-level safety planning or statutory-duty determination module beyond what a later unit assigns.
- Do not reproduce origin provenance markers.

## Test cases

- **hpa-test-001**: Given a JSA with hazards scoring 2x3, 4x5 and 1x1, when saved, then its risk score is 20 and its tier is critical; when hazards are emptied the score is 0.  
  Expected: Score is the maximum product; empty gives zero; recomputed on edit.
- **hpa-test-002**: Given a hazard with severity 7, when submitted, then it is rejected as invalid input; given severity and likelihood omitted, both default to 1.  
  Expected: Bounds 1 to 5 enforced; defaults 1.
- **hpa-test-003**: Given a draft JSA, when submitted then approved by a manager, then it goes under review then approved with approver and time; when an editor then edits its hazards, a conflict is returned; when a manager deletes it, a conflict advising archive is returned.  
  Expected: Approval recorded; content frozen; delete refused for approved.
- **hpa-test-004**: Given a draft JSA, when approve is requested directly, then a conflict is returned naming draft to approved.  
  Expected: State machine enforced on actions.
- **hpa-test-005**: Given an active template and an inactive template, when each is cloned into a project with a work date, then the first yields a draft JSA with copied hazards and recomputed risk and the second is refused.  
  Expected: Clone creates draft; inactive refused with bad request.
- **hpa-test-006**: Given a template list request with no filter value, when listed, then only active templates are returned; with the filter explicitly cleared, both active and inactive are returned.  
  Expected: Tri-state active filter, default active only.
- **hpa-test-007**: Given a permit request whose end equals its start, when submitted, then it is rejected; with end one hour after, it is created in requested state.  
  Expected: Strict ordering; initial state requested.
- **hpa-test-008**: Given an illustrative per-type limit of one day for hot work and an illustrative global limit of about a month, when a hot work permit with a window well beyond one day is created, then it succeeds with a window-length warning; a lifting permit with a window beyond the global limit also warns; a lifting permit with a window beyond one day but within the global limit does not.  
  Expected: Non-blocking warnings per type and global limit.
- **hpa-test-009**: Given an approved hot work permit with only the approved-JSA flag set, when activation is requested, then a conflict lists fire watch and extinguisher as unmet; after setting both, activation succeeds.  
  Expected: Activation gated by type-specific prerequisites.
- **hpa-test-010**: Given an approved permit linked to a JSA still in draft with all flags true, when activation is requested, then a conflict says the linked analysis must be approved; when that analysis is approved, activation succeeds.  
  Expected: Linked-analysis status checked after prerequisites.
- **hpa-test-011**: Given a confined space permit in requested state, when the prerequisite status is read, then required lists approved-JSA, supervisor and atmospheric test, met is empty, missing lists all three and ready is false.  
  Expected: Prerequisite summary matches matrix.
- **hpa-test-012**: Given an active permit, when prerequisites are patched, then a conflict is returned; given a suspended permit, the patch succeeds.  
  Expected: Prerequisite edits allowed only in requested, approved, suspended.
- **hpa-test-013**: Given an active permit, when suspended and then resumed by activation with a prerequisite flag now cleared, then resumption is refused.  
  Expected: Resumption re-runs prerequisite checks.
- **hpa-test-014**: Given an active permit, when closed with the checklist false, then invalid input is returned; with the checklist true and notes, it is closed; closing an already closed permit returns a conflict before checking the checklist.  
  Expected: Closure needs confirmation; order of checks as specified.
- **hpa-test-015**: Given an active permit, when its description is edited, then a conflict is returned; given a requested permit, an edit with an invalid window is rejected, with a valid window accepted.  
  Expected: Edits limited to pre-active states and revalidated windows.
- **hpa-test-016**: Given three permits (one requested, one active in window, one closed today), when the permit dashboard is requested, then each appears in its own group.  
  Expected: Pending, active and closed-today groups.
- **hpa-test-017**: Given permits ending yesterday, today, within a few days and well into the future, when shown, then their countdown tones are error (days ago), error (today), warning, neutral respectively.  
  Expected: Countdown tone rules (cutoffs illustrative).
- **hpa-test-018**: Given a PPE issue with a return time earlier than issue time, when saved, then it is refused; with a validity date before the issue day, refused; with both consistent, accepted.  
  Expected: Date-order errors.
- **hpa-test-019**: Given a PPE register viewed in two different projects, when listed, then the same records appear in both and the company-wide note is displayed in the PPE area.  
  Expected: Company-wide scope and explanatory note.
- **hpa-test-020**: Given every fully supported language, when the company-wide explanatory note is checked, then each language defines it and each non-source language's explanatory sentence differs from the source-language text.  
  Expected: No missing or untranslated entries.
- **hpa-test-021**: Given an issued PPE record, when the return action is applied, then its status is returned and the return time is the current time.  
  Expected: Return stamps status and time.
- **hpa-test-022**: Given illustrative weights of 1, 2, 4 and 8 for low, medium, high and critical, and findings low-failed, medium-passed, high-passed and critical-failed, when an audit is completed from in progress, then score is 6, maximum 15 and the percentage 40.00; completing a scheduled audit returns a conflict.  
  Expected: Score is the sum of passed weights; percentage two decimals; completion only from in progress.
- **hpa-test-023**: Given a finding whose evidence link uses a script scheme, when added, then it is rejected; https and relative links are accepted.  
  Expected: Unsafe schemes rejected.
- **hpa-test-024**: Given an editor-level user, when they approve a permit, close a permit, complete an audit or add a finding, then permission is denied; a manager succeeds.  
  Expected: Manager-only actions enforced.
- **hpa-test-025**: Given a permit belonging to a project the caller cannot access, when any action (including an invalid one) is attempted, then not-found is returned.  
  Expected: Opaque not-found; access check precedes state checks.
- **hpa-test-026**: Given completed audits with percentages 80 and 60 and another with zero maximum, when the dashboard is read, then the average audit percentage is 70.00; with none completed it is absent.  
  Expected: Average of valid completed audits.
- **hpa-test-027**: Given a topic with code already used, when another topic with the same code is created, then a conflict is returned.  
  Expected: Unique topic code.

## Open questions (decisions for QC Manager)

- Decision: should a general edit be allowed to set status on JSAs, audits and PPE without the transition rules and without approval metadata, as the origin permits? The destination may want status changes only through dedicated actions.
- Decision: the origin never moves a permit to an expired state, offers an expired filter in the interface, and has an in-force determination that nothing surfaces. Should the destination add automatic expiry (by work end), a visible in-force indicator, and a ban on use after the window?
- Decision: the approved-JSA prerequisite on a permit is a manually set flag independent of the linked analysis's actual status; should the destination derive it from the linked analysis instead (or require both)?
- Decision: the origin allows deleting a permit in any state, including active, and allows permit numbers to repeat within a project; should the destination block deleting live or closed permits and enforce unique numbers per project?
- Decision: the interface's prerequisite checklist is editable only while requested or approved, while the origin service also allows editing while suspended; which is intended?
- Decision: the origin has a bulk audit-conduct capability that auto-raises a corrective action with a short target period per failed finding, but it is not reachable by users; should the destination raise corrective actions from findings automatically, as a user action, or not at all? The interface lets a user raise one manually from a finding.
- Decision: single-finding creation in the origin does not update the audit's stored score or move a scheduled audit to in progress, and scheduled audits cannot be completed directly; define how an audit becomes in progress and when scores refresh.
- Decision: audit score fields are directly editable by editors in the origin; should scoring be system-computed only?
- Decision: list operations on JSAs, permits, audits, corrective actions and talks lack an explicit read-permission check in the origin (only project access); confirm the destination should require viewer-level permission everywhere.
- Decision: PPE issue records and certifications have no project and no project-access guard; confirm the intended company-wide visibility and whether any tenant boundary is required.
- Decision: the origin contains an unused capability that decides whether a worker is blocked because required certificates are missing or expired; should the destination wire it into permit activation or toolbox or PPE issuance?
- Decision: JSA work dates are validated by shape only in the origin; confirm real-calendar validation in the destination.
- Decision: template hazard lists are accepted as arbitrary items without the hazard entry bounds; confirm they should use the same validation as analyses.
- Decision: the PPE return action in the origin applies to records in any status including already returned ones; confirm whether it should be restricted.
- Decision: audit finding categories, window limits and prerequisite sets cite regional safety practice; confirm which jurisdictions' rules the destination should follow and whether they should be configurable.
- Unknown: the selection logic for permits active today and the full detail views for JSA, audit and toolbox were not inspected; scenario hpa-test-016 and the audits detail behaviour rely on partial evidence.
- Unknown: whether a project-level safety planning and statutory-duty module adjacent to this unit is in scope; it was only skimmed and should be assigned as its own unit if so.
