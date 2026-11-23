# 02. Hold and witness gates

Spec `spec-hold-witness-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Two cooperating mechanisms govern control points that stop or advise work. (1) Standalone gates of four kinds (hold, witness, surveillance, review): a gate is pending until it is released by a party of sufficient authority, waived (only for the non-hold kinds), or voided; a read-only can-proceed check returns whether any pending blocking gate is attached to a given entity (in the destination: an asset node, asset item, inspection record, task or dossier). (2) Inspection-and-test plan lines of type hold, witness or review: each line may name one predecessor line in the same plan, a line cannot be passed until its predecessor has a passed inspection (so control points release in order), completion needs a number of distinct signers, and a passed hold point needs an explicit manager release before dependent work is satisfied, while a passed witness point is satisfied on passing. Only the gate mechanism has waiving; the plan-line mechanism has no waiver. Enforcement of gates is wired only into handover issuance; elsewhere the check is advisory. Concrete limits, number formats and similar parameters are illustrative; the destination chooses its own values.

## Behaviour

- A gate has a kind (hold, witness, surveillance or review; default hold), a title (required), an optional description, a required authority level (one of four, default contractor quality assurance), an optional linked inspection, an optional linked criterion, an optional attachment target given as a kind (in the destination: asset node, asset item, inspection record, task or dossier) plus an identifier, an optional package reference, a blocks-progress flag and free-form supplementary data. A linked inspection must belong to the same project and be a record of the destination's single inspection register; gates may link any record of that register, including plan lines. A per-project human-readable gate number is assigned at creation from the destination's numbering service (see h-compat-02) and a new gate starts pending. _(h-bhv-01; observed)_
- When the blocks-progress flag is omitted on creation it is derived from the kind: hold blocks; witness, surveillance and review do not. The caller may set the flag explicitly on any kind. _(h-bhv-02; observed)_
- The attachment kind and attachment identifier must be given together or both omitted; one without the other is rejected at input because such a gate could never be found by the proceed check. _(h-bhv-03; observed)_
- Release of a gate: allowed only while pending. The caller must assert an authority level; it satisfies the gate if equal to the gate's required level or higher in the ascending order contractor quality control, contractor quality assurance, third-party inspector, authority having jurisdiction. A lower level never satisfies a higher requirement (a quality-control party cannot release an authority gate). If the gate names a linked inspection and that inspection has not passed, release is refused. If the linked inspection cannot be found, release is refused (see h-err-03). On success the gate becomes released and stores the releasing user, asserted level, release time (caller-supplied or now), optional justification, the caller's network address and a tamper-evident SHA-256 digest of a canonical snapshot of the gate identity (number, kind, linked inspection, attachment target, released level). A notification announces the release only after the release is committed, and an activity-log entry is written on a best-effort basis. _(h-bhv-04; observed)_
- Waiving a gate: allowed only while pending and only for witness, surveillance and review kinds. A hold gate can never be waived (conflict). A non-empty reason is required. The gate becomes waived and stores the waiving user, the time and the reason, and an audit ledger entry is added. No authority-level comparison is applied to a waiver; only the manager-level permission applies (the same permission as release). _(h-bhv-05; observed)_
- Voiding a gate is allowed only while pending and marks it void (no longer applies). Editing a gate is allowed only while pending; its status is not editable directly. Deleting is allowed only for a pending gate; released, waived and void gates are refused because they carry the signed decision that let work proceed. _(h-bhv-06; observed)_
- Can-proceed check: given a project, an attachment kind and an attachment identifier, the system returns whether progress is allowed, plus the numbers and identifiers of the blocking gates. Blocking gates are exactly those attached to that entity in that project, with the blocks-progress flag on and status pending, listed oldest first. Released, waived and void gates do not block; non-blocking witness, surveillance or review gates do not block unless their flag was turned on. The check is read-only and available to read-only users with project access. _(h-bhv-07; observed)_
- Enforcement scope in the reference behavior: handover issuance consults gate state (in the destination this is dossier issue, see h-bhv-23). The handover completion gate reports the count of pending, blocking hold gates (project-wide, or scoped to the package references of the handover package) together with the open non-conformance count; the certificate can be issued only when both counts are zero, or when a manager records an override with a reason that is itself captured as a documentation non-conformance report. _(h-bhv-08; observed)_
- Plan lines: each inspection-and-test plan line has a control-point type of hold, witness or review (default review; review is not a gate), a required signatory count (a small positive integer, illustratively 1 to 10, default 1), an optional responsible role, and an optional single predecessor line that must belong to the same plan. _(h-bhv-09; observed)_
- Releasing in order: when a line has a predecessor, an inspection against that line cannot be completed as passed until the latest inspection result of the predecessor line is passed (see h-bhv-21). The refusal names the predecessor line. Completing as failed or conditional is always permitted regardless of the predecessor, so failures can always be recorded. _(h-bhv-10; observed)_
- Completion of a plan-line inspection requires the count of distinct signing people (not signatures) to reach the line's required signatory count; one person signing in two roles counts once. A line responsible role is ranked (subcontractor lowest, then inspector and designer equal, then general contractor, then client highest) and a signer must rank at or above the named role; unknown or empty roles are ungated. The same person may sign twice only in different roles; the same person and role twice is a conflict, including under concurrent submissions. _(h-bhv-11; observed)_
- When a hold or witness plan-line inspection is completed as passed or failed, a dedicated notification is announced in addition to the generic one; a failed hold point also triggers a high-severity alert and a dashboard recompute. When a hold or witness inspection is completed as failed or conditional, an approval request is announced; an approval is started only if the project has an active approval route configured for hold points, otherwise nothing further happens and release still needs the manager-level permission. _(h-bhv-12; observed)_
- Hold-point release record on plan lines: allowed only if the inspection is linked to a hold or witness line, has passed, and has no release yet. One release per inspection. It stores releasing user, time, optional justification and optional approval-route reference, writes an audit entry and announces a release notification. Requires manager level. _(h-bhv-13; observed)_
- Hold-point status view for a plan-line inspection returns: whether it is a hold point, the predecessor line and whether it has passed, whether the inspection is blocked (predecessor not passed and the inspection not already passed or failed), a blocking reason naming the predecessor, and whether a release exists. _(h-bhv-14; observed)_
- Line-level gate-satisfied query for downstream callers: a review line is always satisfied; a hold or witness line with no inspection is not satisfied (reason: no inspection scheduled); with inspections but none passed it is not satisfied (reason distinguishes a failed inspection from one not yet passed); once an inspection has passed a witness line is satisfied, while a hold line is satisfied only if a release record exists for a passed inspection (otherwise the reason says it passed but has not been released). A fail-closed wrapper refuses with the reason when the line is not satisfied. Because each destination plan line is a single record that is reopened rather than duplicated, its latest result decides (see h-bhv-21). _(h-bhv-15; observed)_
- The plan dependency view lists lines by sequence and shows a four-state light: review (not a gate), passed (an inspection passed), blocked (hold or witness whose predecessor has not passed) and pending (otherwise). It shows which predecessor each line depends on. _(h-bhv-16; observed)_
- How an override is recorded: gates themselves have no override. The override exists only on the handover completion gate. A manager gives a mandatory reason (and optional severity). It is refused with a conflict when the completion gate is already clear and with a client error when the package is already issued or revoked. On success a documentation non-conformance report is raised first (its text lists the outstanding blockers, such as open reports and unreleased holds), and then the package is marked as overridden, storing the overriding user, the reason and, in its supplementary data, the user, reason and the identifier of that report. Issuing the certificate afterwards is allowed because the gate is overridden; the gate state is revalidated at issue time, so a gate that has become blocked again since is refused unless it was overridden. The pending gates themselves stay pending after an override. _(h-bhv-17; observed)_
- Release by a role other than the required one: an asserted authority equal to or higher than the required one is accepted, and a lower one is forbidden. Higher authority may release a lower gate; quality control cannot release an authority gate. A release by a third-party inspector or an authority having jurisdiction is accepted for a quality-assurance gate, and a gate requiring a third-party inspector accepts only a third-party inspector or an authority having jurisdiction. The stored released level is the asserted one, not the required one. _(h-bhv-18; observed)_
- Which kinds may be waived: witness, surveillance and review gates may be waived; a hold gate never can. This is confirmed for the destination. _(h-bhv-19; observed)_
- The destination keeps its plan-line hold engine and adds standalone gates alongside it; the two mechanisms are not merged. The can-proceed answer for an inspection lists blocking gates and, separately, earlier unreleased plan hold points, and is false if either list is non-empty. _(h-bhv-20; derived)_
- Each destination plan line is a single record that is reopened rather than duplicated, so its latest result decides, both for the line-level gate-satisfied query and for any predecessor-ordering check. _(h-bhv-21; derived)_
- Waiver controls: a waiver needs the approval permission and a non-empty reason, records the waiving user and time and adds an audit ledger entry. It has no authority-level check, no justification review, and no signature digest or network address. _(h-bhv-22; derived)_
- Enforcement scope in the destination: gates are advisory, shown as a non-blocking eligibility finding, everywhere except dossier issue, which a pending blocking gate refuses. Plan line submission, scaffold handover and task progression are candidate later enforcement points and are not enforced in this slice. _(h-bhv-23; derived)_
- Gates attach to an asset node, asset item, inspection record, task or dossier. A commissioning attachment is not part of this slice. _(h-bhv-24; derived)_

## Inputs

- Release input: the asserted authority level (required, one of the four), optional justification and optional release time. Waive input: a required non-empty reason. Plan link input: optional predecessor line, optional specification and model references. Release record input: optional justification and optional approval-route reference. Text inputs have bounded lengths chosen by the destination. _(h-in-01; observed)_
- Proceed query input: project, attachment kind and attachment identifier, all required. _(h-in-02; observed)_

## Outputs

- A gate response exposes gate number, kind, title, description, required level, linked inspection and criterion, attachment target, package reference, blocks-progress flag, status, release details (user, level, time, justification, network address, digest), waiver details (user, reason), an approval-instance reference, creator, supplementary data and timestamps. Gate lists are newest first. _(h-out-01; observed)_
- The proceed response returns the project, attachment kind and identifier, a boolean can-proceed result, and parallel lists of blocking gate numbers and identifiers. For an inspection it additionally lists, separately, earlier unreleased plan hold points (see h-bhv-20). _(h-out-02; observed)_
- The gate-satisfied query returns the line, whether it is a hold point, a boolean satisfied result and a human-readable reason when not satisfied. _(h-out-03; observed)_

## States and transitions

- Gate: pending to released (release action), pending to waived (waive action, non-hold kinds only), pending to void (void action). Released, waived and void are terminal and cannot be edited or deleted. _(h-st-01; observed)_
- Plan-line inspection: scheduled may go to in progress, passed, failed or conditional; in progress to passed, failed or conditional; conditional to passed or failed; passed and failed are terminal. Moving to a result by an ordinary edit is refused: results are set only by the completion action, which enforces predecessor and signer rules. Signing is refused once passed or failed. _(h-st-02; observed)_
- Plan status: draft to active or closed; active to superseded or closed; superseded to closed; closed terminal. Activation requires at least one line. Lines and links may be added or changed only while the plan is draft or active. _(h-st-03; observed)_

## Timing and ordering

- Blocking gates are returned oldest first so the numbers appear in creation order; gate lists are newest first; plan lines are shown in ascending sequence. _(h-ord-01; observed)_
- The release notification for a gate is published only after the release has been committed, so a subscriber reading the gate finds it released. _(h-ord-02; observed)_

## Edge cases

- A line may not be its own predecessor, and may not take as predecessor a line that already names it as predecessor (direct two-cycle). Detection of longer cycles is an open question. _(h-edge-01; observed)_
- A gate without an attachment target can still be created, released and listed but will never appear in any proceed check; it still counts in project-wide unreleased-hold totals when it blocks progress. _(h-edge-04; derived)_

## Errors

- Release fails closed: it is refused when the linked inspection cannot be found. The destination's inspection delete guard already prevents deleting an inspection that a gate links. _(h-err-03; derived)_
- Gate errors: releasing, waiving, voiding or editing a non-pending gate is a client error naming the current status; releasing with insufficient authority is forbidden; waiving a hold gate is a conflict; releasing against an unpassed linked inspection is a client error naming the inspection and its status; referencing an inspection or criterion from another project is not-found; a missing gate is not-found; deleting a decided gate is refused with an explanatory reason. _(h-err-01; observed)_
- Plan-line errors: a predecessor from another plan, a line as its own predecessor, a direct cycle, editing a plan that is past active, activating a plan with no lines, passing a line whose predecessor has not passed, completing with too few distinct signers (message shows collected over required), signing below the required authority, duplicate signer and role, releasing a non-hold line or a non-passed inspection or an already released one. _(h-err-02; observed)_

## What it must not do

- Waiving does not exist for plan-line witness points; a witness point there is cleared only by a passing inspection (and signatures), or the inspection may be failed. A waived gate does not record any digest or network address. _(h-neg-01; observed)_
- Waiving a gate checks no party authority level, only the manager-level permission; only release compares the asserted authority with the required authority. _(h-neg-02; observed)_
- Gate state is not consulted by task progression, inspection completion or other downstream actions; outside dossier issue the can-proceed result is advisory only and is shown as a non-blocking eligibility finding (see h-bhv-23). _(h-neg-03; observed)_

## Security

- Access tiers for gates: read at read-only level; create and edit at editor level; delete, release and waive at manager level. For plan lines: read at read-only level, writing and signing at editor level, releasing a hold point at manager level. An editor can create but not release a gate; a read-only user cannot create one. Every call is checked against project membership; foreign tenants get not-found. _(h-sec-01; observed)_
- Release requires both the approval (manager-level) permission and the asserted-authority comparison to pass. The stored digest is deterministic and independent of key order, and changes if any snapshot field (for example the released level) changes. _(h-sec-02; observed)_
- The releasing user asserts the authority level, and release needs the approval permission. The asserted level is stored and hashed. Binding authority levels to user roles or to the competency register is a later option and is not part of this slice. _(h-sec-03; derived)_

## Invariants

- A hold gate is never waived; it is cleared only by a qualified release. _(h-inv-01; observed)_
- Only pending gates change; every decided gate is permanent evidence. _(h-inv-02; observed)_
- A plan-line inspection cannot reach passed unless its predecessor line has a passed inspection and enough distinct people signed. _(h-inv-03; observed)_
- A gate's blocking effect depends solely on its blocks-progress flag and pending status, never on its kind label alone. _(h-inv-04; observed)_
- The destination has one inspection register with a shared identifier space and distinct number formats, so a bare identifier is unambiguous for gates and reports. _(h-inv-05; derived)_

## Notes

- Authority ranking differs between the two mechanisms: gates use four parties (contractor quality control, contractor quality assurance, third-party inspector, authority having jurisdiction) while plan lines use five signer roles (subcontractor, inspector, designer, general contractor, client). The destination keeps both mechanisms with their own vocabularies and does not unify them (see h-bhv-20). _(h-compat-01; observed)_
- Gate numbers come from the destination's numbering service with a quality gate record kind and a fallback prefix, so a project may configure its own scheme. The exact human-readable format is not a compatibility requirement. _(h-compat-02; derived)_

## Non-goals

- No route paths, permission keys, event names, table or field names are specified here.
- Handover package assembly beyond its use of unreleased hold counts is out of scope.
- Approval-route engine internals are out of scope.
- A commissioning attachment for gates is not part of this slice. Approval-route dispositions stay with the deferred plan-line decision, and the frontend pages needed are covered by the plan's frontend work items.
- Do not reproduce origin provenance markers.

## Test cases

- **h-test-01**: Given a blocking hold gate attached to a task and still pending, When the can-proceed query is made for that task, Then it says progress is not allowed and lists the gate number; When a quality-assurance party releases it, Then the query says progress is allowed with no blocking gates.  
  Expected: Not allowed with one blocking gate before release; allowed with an empty list after release.
- **h-test-02**: Given a surveillance gate created without an explicit blocking flag and attached to a task, When the proceed query is made, Then progress is allowed.  
  Expected: Allowed, because the derived blocking flag is off for non-hold kinds.
- **h-test-03**: Given a witness gate with blocking turned on, When a manager waives it with a reason, Then it becomes waived and the proceed query no longer lists it.  
  Expected: Status waived with waiver user and reason stored; not blocking afterwards.
- **h-test-04**: Given a hold gate, When a manager tries to waive it, Then a conflict is returned and the gate stays pending; When an empty reason is given for a witness gate, Then the input is rejected.  
  Expected: Conflict for hold; validation failure for the empty reason; no state change.
- **h-test-05**: Given a gate requiring the authority having jurisdiction, When a party asserting quality control tries to release it, Then it is forbidden; When a party asserting authority-having-jurisdiction releases a gate requiring quality assurance, Then it succeeds.  
  Expected: Lower-ranked assertion forbidden; higher-ranked assertion releases and stores released level, time and digest.
- **h-test-06**: Given a gate linked to an inspection that is still open, When a manager attempts release, Then it is refused naming the inspection status; When the inspection has passed, Then release succeeds.  
  Expected: Client error while unpassed; success after pass.
- **h-test-07**: Given a released gate, When an editor tries to edit, void, release again or delete it, Then each is refused.  
  Expected: All refused; gate unchanged.
- **h-test-08**: Given an editor and a read-only user, When the read-only user creates a gate, Then access is denied; When the editor creates one, Then it succeeds; When the editor tries to release it, Then access is denied.  
  Expected: Read-only user denied; editor creates; editor release denied.
- **h-test-09**: Given a gate create request that supplies an attachment kind without an identifier, or an identifier without a kind, Then it is rejected; supplying both or neither is accepted.  
  Expected: Mismatched pair rejected; matching pair or neither accepted.
- **h-test-10**: Given a handover package scope with one pending blocking hold gate, When certificate issue is attempted, Then it is refused; When the hold is released, Then issue is permitted; When a manager overrides with a reason instead, Then an override record and a documentation report are created.  
  Expected: Refusal while the hold is unreleased; allowed after release; override recorded as a report.
- **h-test-11**: Given a plan with line A (hold) and line B (hold) with B's predecessor set to A, When an inspection on B is completed as passed before any inspection on A passed, Then it is refused naming A; When the same inspection on B is completed as failed, Then it is allowed; After A passes, Then B can pass (given enough signers).  
  Expected: Pass blocked by predecessor, fail always allowed, pass allowed after predecessor passes.
- **h-test-12**: Given a line requiring two signatories, When the same person signs as inspector and as designer and completion is attempted, Then it is refused showing one collected of two required; When a second person signs, Then completion succeeds.  
  Expected: Distinct-person count governs; refusal message shows collected over required.
- **h-test-13**: Given a passed hold-line inspection with no release, When the gate-satisfied query is made, Then it is not satisfied and says it has passed but not been released; When a manager releases it, Then it is satisfied; Given a passed witness-line inspection, Then it is satisfied without any release; Given a review line, Then it is always satisfied.  
  Expected: Hold needs release; witness satisfied on pass; review always satisfied.
- **h-test-14**: Given line B whose predecessor A has no passed inspection, When the hold-point status of a scheduled B inspection is read, Then it reports blocked with a reason naming A; once A passes it reports not blocked.  
  Expected: Blocked true with reason before; false after.
- **h-test-15**: Given line A, When an editor links A as its own predecessor, or links B as predecessor of A while A is already B's predecessor, Then both are rejected.  
  Expected: Self link and direct two-cycle rejected.
- **h-test-17**: Given a package with one unreleased blocking hold, When a manager overrides with a reason, Then the package becomes overridden, a documentation report listing the blockers is raised, the override user, reason and report identifier are stored, and certificate issue is allowed; the hold gate itself is still pending. Given a package whose gate is clear, When an override is attempted, Then a conflict is returned.  
  Expected: Overridden state with audit data; hold remains pending; override refused when nothing blocks.
- **h-test-18**: Given a gate requiring a third-party inspector, When a party asserting quality assurance tries to release it, Then it is forbidden; When a party asserting an authority having jurisdiction releases it, Then it succeeds and the stored level is the authority.  
  Expected: Lower assertion rejected; higher accepted; stored released level is the asserted one, not the required one.
- **h-test-19**: Given pending gates of kinds surveillance and review, When each is waived with a reason, Then both become waived; Given a hold gate, Then waiving is a conflict.  
  Expected: Waivable: witness, surveillance, review; non-waivable: hold.
- **h-test-16**: Given the same canonical gate snapshot with keys in a different order, When the release digest is computed, Then the digest is identical; when the released level differs, Then it differs.  
  Expected: Order-independent, content-sensitive 64-hex-character digest.
- **h-test-20**: Given an inspection with one pending blocking gate and an earlier unreleased plan hold point, When the can-proceed answer is requested, Then it is false and lists the gate and, separately, the plan hold point; Given only the gate is released, Then it is still false; Given the plan hold point is also released, Then it is true with both lists empty.  
  Expected: False while either list is non-empty; true only when both are empty.
- **h-test-21**: Given a plan line whose record passed and was later reopened and failed, When the line-level gate-satisfied query is made, Then it is not satisfied because the latest result decides; Given a successor line that depends on it, When completion as passed is attempted, Then it is refused until the latest result is passed.  
  Expected: Latest result governs both the satisfied query and predecessor ordering.
- **h-test-22**: Given a pending witness gate whose required level is higher than a waiving user's own level, When a user holding the approval permission waives it with a reason, Then it becomes waived, the user and time are stored, an audit ledger entry is added and no digest or network address is stored; Given a user without the approval permission, Then the waiver is denied; Given an empty reason, Then it is rejected.  
  Expected: Waiver governed by permission and reason only; audit entry written; no digest or address.
- **h-test-23**: Given a pending blocking gate attached to a task, When task progression is requested, Then it is not refused and an advisory non-blocking eligibility finding mentions the gate; Given a pending blocking gate scoped to a dossier, When dossier issue is attempted, Then it is refused.  
  Expected: Advisory everywhere except dossier issue.
- **h-test-24**: Given a plan-line record and a checklist inspection in the same project, When a gate is linked to each, Then both links are accepted and each bare identifier resolves to exactly one record; Given the linked plan-line record has not passed, When release is attempted, Then it is refused.  
  Expected: Gates may link any record of the single inspection register; unpassed linked record blocks release.
- **h-test-25**: Given a gate whose linked inspection cannot be found, When release is attempted, Then it is refused and the gate stays pending; Given an attempt to delete an inspection that a gate links, Then it is refused.  
  Expected: Release fails closed; linked inspection cannot be deleted.
- **h-test-26**: Given a user holding the approval permission asserts a third-party inspector level for a gate requiring that level, When the gate is released, Then the stored released level equals the asserted level and the digest changes if the asserted level differs; the asserted level is not checked against the user's roles.  
  Expected: Asserted level stored and hashed; no binding to user roles.
- **h-test-27**: Given a project with no configured numbering scheme, When a gate is created, Then its number uses the fallback prefix from the numbering service; Given a project that configured its own scheme, Then the gate number follows it.  
  Expected: Gate numbers come from the numbering service; exact format not fixed.
- **h-test-28**: Given gates attached to an asset node, an asset item, an inspection record, a task and a dossier, When the can-proceed query is made for each, Then each query lists only the gates attached to that entity; Given a request to attach a gate to a commissioning stage, Then it is not an offered attachment kind.  
  Expected: Five attachment kinds supported; commissioning not offered.

## Open questions (decisions for QC Manager)

- Deferred (product decision pending): Decision point: cycle detection is limited to direct two-cycles. The target should decide whether to detect longer chains.
- Deferred (product decision pending): Decision point: when a predecessor line is deleted its dependants silently lose their upstream condition and can then pass without it; the target should decide whether deletion of a referenced predecessor must be refused instead.
- Deferred (product decision pending): Decision point: an override of the handover gate leaves the underlying holds pending, so later counts still show them; confirm whether the target should close or annotate those gates on override.
