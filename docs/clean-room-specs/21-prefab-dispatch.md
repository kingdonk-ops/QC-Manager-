# 21. Prefab dispatch gate

Spec `spec-prefab-dispatch-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Off-site (prefabricated) units move through an ordered, forward-only production lifecycle. The one hard gate is stage ordering: a unit cannot be dispatched, delivered or installed until it has reached the quality-assurance stage. Every stage change is audited, milestone events are announced for dispatch and installation, a dispatched unit can be booked in on site by scanning its code, and a derived cost view and earned value follow the stage. The gate is purely stage-ordering based; no inspection results or readiness data feed it (see open questions). Separately, a neighbouring capability schedules crews, workers and equipment on a daily board with conflict detection; it is not a prefabrication release gate and is summarised only as context.

## Behaviour

- The lifecycle has seven ordered stages: design, approved for production, in production, quality assurance, dispatched, delivered, installed. Unit types are pod, panel, module, skid, rebar cage, volumetric and other. _(beh-001; observed)_
- Release for dispatch rule: a unit may enter dispatched, delivered or installed only if its current stage is quality assurance or later. A request that would jump from any earlier stage to any of those three is rejected with a reason that identifies the quality stage and tells the caller to advance to it first. From the quality stage any of the three later stages is allowed directly, and later stages may move among themselves forward (dispatched to installed, delivered to installed). _(beh-002; observed)_
- Advancement is forward only: moving to the same stage is rejected with a reason saying the unit is already at that stage; moving to an earlier stage is rejected with a reason saying stages only advance forward. Rework loops (sending a failed unit back) are not supported. _(beh-003; observed)_
- Stage names are compared case-insensitively after trimming. Either the current or the target stage being unrecognised (including empty) is rejected with a reason that lists the allowed stages; it never raises an unhandled error. _(beh-004; observed)_
- Skipping stages inside the pre-quality range is permitted (the only hard rules are forward-only and the quality gate). The set of allowed targets from a pre-quality stage never contains a post-quality stage unless the unit is at or beyond quality; from the final stage it is empty. Passed quality means being at the quality stage or any later stage. _(beh-005; derived)_
- An advance request may name a target stage and an optional note; with no target, the immediately next stage is used. A unit already at the final stage cannot advance: the request fails with a bad-request outcome saying the unit is at its final stage. Any refusal from the rules above is returned as a bad-request outcome carrying the reason text (not a server error). _(beh-006; observed)_
- A successful advance updates the stage and writes an immutable production-event record (new stage, previous stage, note, user, time) in the same transaction as the stage change, so a rollback leaves no orphan record. A general stage-advanced announcement is published after every advance, plus a dispatch milestone announcement when the new stage is dispatched and an installation milestone announcement when it is installed, each with project, unit, reference, from stage, to stage and user. Announcements are best-effort and detached. _(beh-007; observed)_
- Creating a unit records an opening production event for its initial stage with a fixed default note indicating the unit was registered, and announces a creation event; the unit reference must be unique within the project (conflict otherwise, also on rename) and a random URL-safe code is generated for scanning. _(beh-008; observed)_
- A plain unit update can change reference, type, target install date, drawing reference, model element identifiers, element reference and notes, but never the stage; stage changes must go through the advance action so that ordering, the quality gate and auditing cannot be bypassed. _(beh-009; observed)_
- Receiving by code: the unit is looked up by its code (unknown code yields not found); only a unit currently at the dispatched stage can be received, otherwise a bad-request outcome states that only a dispatched unit can be received and names the current stage. On success the delivery note reference is stored on the unit and the unit advances to delivered with the supplied note or a default note quoting the delivery note reference, with the usual audit and announcements. _(beh-010; observed)_
- Board: columns for every stage in lifecycle order (zero-filled), each with a count and its units; units whose stored stage is not a known stage appear in extra columns so none is dropped; the board materialises a bounded number of units per response (for example 1000) while the stats counts remain authoritative. Statistics return total, counts by stage and counts by type. The stage list is available to clients. Unit timeline is newest first. _(beh-011; observed)_
- Progress fraction of a unit is its stage position divided by the last position (design 0, quality 0.5, installed 1); an unknown stage yields 0. This is the progress proxy and is rounded to four decimals for display. _(beh-012; observed)_
- Cost link: a unit may link to a priced position of the project's estimate and/or a reusable assembly. Only supplied fields change; an explicit null clears a link. A non-null position must exist (else not found) and belong to the unit's project (else bad request). An assembly must exist (else not found) and be either platform-wide or belong to the unit's project (else bad request). _(beh-013; observed)_
- Derived cost view: the position's unit rate is preferred as cost basis; if it is unlinked or no longer resolves, the assembly's total rate is used as fallback; with neither, cost basis and earned value are absent. Earned value = cost basis times the exact stage ratio, rounded half-up to two decimals; design earns 0 and installed earns the full basis. Money is carried as decimal strings, never floats; an unparseable rate is treated as absent. _(beh-014; observed)_
- Insights view (frontend): progress is shown on a 0-100 percent scale from the 0-1 fraction (missing fraction gives 0); decimal-string cost basis and earned value are parsed to numbers (missing link gives 0 so sums are not poisoned); a unit is flagged late when it is outstanding and its target install date is in the past; an installed unit is never late and is counted as installed; the project currency is carried with the monetary measures. _(beh-015; observed)_
- Context only, crew and equipment dispatch board (distinct capability): one day's board has locations (project, yard, shop, rental return) and cards (crew, worker, equipment, rental). Conflicts are detected per day and never hidden: error severity for a person or unit placed at two locations the same day (crews expanded to members) and for a unit that is down for maintenance being sent to a project; warning severity for overdue scheduled maintenance, an operator lacking a certificate type the unit requires, a worker absent that day, and a crew with fewer present members than its minimum. A validation report summarises as errors, warnings or passed. Placing cards does not itself refuse a conflicting placement. _(beh-016; observed)_
- Context only, dispatch board operations: placing a card already at that location that day does nothing; moving a card to a location where it already is that day drops the duplicate; copying a day without replace keeps existing cards; scheduled moves can be booked for today or later and are applied on or after their date, oldest first, idempotently; a unit is shown as maintenance, in transit, assigned or available; a daily plan groups lines per foreman and can be shared as notifications; utilisation reports working days assigned versus idle per unit over a capped date range. _(beh-017; observed)_

## Inputs

- Unit create: project, reference (bounded length), type (default module), initial stage (default design; which initial stages are permitted is a decision point, see open questions), optional target install date, drawing reference, model element identifiers, element reference, notes. Stage and type outside the vocabularies are rejected as unprocessable. _(in-001; observed)_
- Receive request: scanned code, delivery note reference, optional note. _(in-002; observed)_

## Outputs

- A unit response contains stored attributes plus cost basis, cost source (position or assembly), completed fraction and earned value. _(out-001; observed)_

## States and transitions

- Allowed transitions through the advance action: any strictly later stage, subject to the quality gate; none backward; none from installed. Typical path advances one stage at a time and is audited at each step. _(st-001; observed)_

## Timing and ordering

- Within an advance: load unit, resolve target, evaluate rules, update stage, write audit record, flush, then announce. Announcements are issued after persistence. _(ord-001; observed)_

## Edge cases

- The quality stage does not record a pass or fail result; reaching the stage is treated as clearing quality assurance (see open questions). _(edge-002; derived)_

## Errors

- Outcomes: unknown unit or code (not found); duplicate reference (conflict); gate, order, unknown-stage, final-stage and not-dispatched refusals (bad request with reason); foreign-project position or assembly (bad request); unknown position or assembly (not found). _(err-001; observed)_

## What it must not do

- Through the advance and receive actions, a unit that has not reached the quality stage can never become dispatched, delivered or installed; a failed advance changes nothing and writes no audit record. _(neg-001; observed)_
- The release gate does not read inspection results, open non-conformances, punch status, documents or other readiness data (see open questions). _(neg-002; observed)_

## Security

- Three permission tiers apply: read-level for reads, edit-level for create, update, link and delete, and a distinct advance permission (edit-level by default) for stage advances and receipts, so stage movement can be controlled separately from editing. Cost links are validated to the unit's project so references cannot cross projects. _(sec-001; observed)_
- The scan code is an unguessable random token; receipt by code is authorised through the advance permission rather than anonymously. _(sec-002; observed)_

## Invariants

- The vocabulary used for request validation and the transition rules come from one list of stages so they cannot drift apart. _(inv-001; observed)_
- Every stage change leaves exactly one production-event record; the timeline contains the opening record plus one per advance. _(inv-002; observed)_

## Notes

- Behavior-only compatibility: stage order, forward-only rule, quality gate, refusal categories, progress and earned-value arithmetic, and the one-audit-per-advance invariant should match; reason wording, names and routes need not. The board size cap is an ordinary parameter; the destination chooses its own value. _(comp-001; derived)_

## Non-goals

- Rework loops or quality failure handling (deferred; see open questions).
- Reproducing origin layout, naming, message wording or board visuals.
- Rebuilding the crew and equipment dispatch board unless separately approved.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Walk a unit from the first stage to the last, one step at a time.  
  Expected: Every step succeeds; one audit record per step plus the opening record; progress reaches 1.
- **ts-002**: For each pre-quality stage and each post-quality stage, request the jump.  
  Expected: Every combination is refused, the reason mentions quality assurance, and the unit's stage is unchanged with no audit record.
- **ts-003**: A unit at quality assurance advances to dispatched, to delivered and to installed (separate units).  
  Expected: All three allowed; dispatched unit may later go to installed; delivered may go to installed.
- **ts-004**: Request the same stage, then an earlier stage, then an unrecognised stage name, then an empty target.  
  Expected: Refusals mentioning already at stage, forward only, unknown stage, unknown stage; none server errors.
- **ts-005**: Advance a unit whose current stage is given as upper-case design with surrounding spaces to a mixed-case approved-for-production stage name.  
  Expected: Accepted.
- **ts-006**: Advance a unit with no explicit target from in production, and from installed.  
  Expected: First moves to quality assurance; second is a bad request about the final stage.
- **ts-007**: Allowed targets for a unit in production, at quality assurance and at installed.  
  Expected: Quality assurance only from in production (no post-quality stage); all later stages from quality; none from installed.
- **ts-008**: Advance to dispatched.  
  Expected: General advance announcement and a dispatch milestone announcement are issued, no installation announcement.
- **ts-009**: Patch a unit's stage through the plain update.  
  Expected: Stage cannot be changed through update; it is rejected or ignored and the gate cannot be bypassed.
- **ts-010**: Scan the code of a unit at in production, then of a dispatched unit with an invented delivery note reference, then an unknown code.  
  Expected: First refused naming its stage; second advances to delivered, stores the note reference and writes an audit record with a default note quoting it; third not found.
- **ts-011**: Create two units with the same reference in one project.  
  Expected: Second is a conflict; the first unit has an opening audit record and a scan code.
- **ts-012**: Linked rate 42000.00 for a unit at in production (position 2 of 6), at design, at installed; with the position deleted and an assembly linked as fallback; with no link; with an unparseable rate.  
  Expected: Earned values 14000.00, 0, 42000.00; fallback uses assembly rate and source assembly; no link gives absent cost and earned value; unparseable gives absent. Fractions 0.3333, 0, 1 (to four decimals).
- **ts-013**: Link a unit to a position of another project, to a missing assembly, to a project-scoped assembly of another project, and to a platform-wide assembly.  
  Expected: Bad request, not found, bad request, accepted.
- **ts-014**: Board for a project with units in some stages and one with a legacy unknown stage.  
  Expected: Seven ordered columns including empty ones, plus an extra column for the unknown stage; stats counts by stage and type match.
- **ts-015**: Insights rows for: fraction 0.4; fraction missing; cost basis 42000.00 with earned 16800.00; no cost link; outstanding unit with past target date; installed unit with past target date; project currency GBP.  
  Expected: Progress 40; 0; numbers 42000 and 16800; zeros; late 1; late 0 and installed 1; dataset carries the currency and has a currency-formatted measure.
- **ts-016**: Context only: dispatch board day with one worker placed at two locations, a unit under maintenance placed at a project, a crew with 2 of 3 minimum present.  
  Expected: Two error conflicts (double booking, maintenance block) and one warning (crew under minimum); report status errors.

## Open questions (decisions for QC Manager)

- Decision: the release gate is only reaching the quality stage. A fuller release rule combining quality and readiness conditions may be intended; no inspection result, punch status or readiness data feeds the gate. Should the destination add real checks (open non-conformances, failed inspections, missing documents)?
- Decision: unit creation accepts any initial stage, including post-quality stages, so a unit can be registered already dispatched without passing the quality stage. Should the destination restrict initial stages (for example design only), or apply the gate to creation as well?
- Decision: the quality stage records no pass or fail and no rework path exists. Should the destination add a fail-and-return action and a recorded inspection result?
- Decision: the receipt action requires the advance permission only; confirm whether site staff without edit rights should be able to receive by code.
- Decision: the crew and equipment dispatch board is a different capability from prefabrication dispatch. Confirm whether it belongs in this approved slice or in a separate gap.
- Decision: cost-link and unit-link edge cases beyond those described here may exist and were not fully reviewed.
- Decision: screen layouts for the prefab board and the dispatch board are not specified beyond the insights view.
