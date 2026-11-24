# 04. Commissioning readiness

Spec `spec-commissioning-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Per-project commissioning of building systems (heating and ventilation, electrical, fire protection, plumbing and similar). Each system owns pre-functional and functional checklists of test items and an issue log. A readiness percentage over applicable functional items, a traffic-light rating and a list of blocking reasons are computed live. A gated action marks a system as commissioned only when the gate is satisfied. A printable commissioning certificate and a spreadsheet export are produced per system, and an aggregate insights view summarises readiness across systems.

## Behaviour

- Readiness is measured only over functional checklist items. Each item is counted as passed, failed, not applicable or pending. Item status text is compared case-insensitively after trimming; any unrecognised or missing status is treated as pending so a malformed value can never count as passed. _(beh-001; observed)_
- Applicable items = total functional items minus not-applicable items. Readiness percentage = passed divided by applicable, times 100, rounded to two decimals. When there are zero applicable items the percentage is 0 and the result is flagged as undefined so callers can show a no-data state instead of a misleading zero. The result never contains non-finite numbers. _(beh-002; observed)_
- A system may be commissioned only when the percentage is defined (at least one applicable functional item), no functional item is failed or pending, and no critical issue is open. Only open issues of the highest severity count toward the gate; issues of lower severity or closed issues never block. _(beh-003; observed)_
- The readiness rating is red when any critical issue is open, any functional item has failed, or the percentage is undefined; green when the system may be commissioned; otherwise amber (only pending items remain, nothing failed). _(beh-004; observed)_
- The readiness breakdown exposes: total, passed, failed, pending and not-applicable functional counts; applicable count; open functional items (failed plus pending); open critical issue count; percentage; defined flag; may-commission flag; rating; an ordered list of human-readable blocking reasons; and a text statement of the formula so the figure can be reproduced by hand. _(beh-005; observed)_
- Blocking reasons: one reason when the system has no functional items; otherwise one reason when every item is not-applicable (at least one must pass); otherwise one reason stating the count of functional items not yet passed; plus an additional reason stating the count of open critical issues when that count is above zero. Reasons can therefore combine (open items together with critical issues). Reason wording is chosen by the destination. _(beh-006; observed)_
- The commission action requires a manager-level permission and project access. It first rejects an already-commissioned system; then asks any registered quality-concept stage veto (an optional extension point) for blocking reasons, and if there are any the action is refused with a conflict outcome listing them; then checks the readiness gate, and if not satisfied it is refused with a bad-request outcome whose message states that commissioning is not possible and lists the blocking reasons (or gives a generic not-ready statement when no reason is listed). _(beh-007; observed)_
- On success the system status becomes commissioned, the commissioning time (UTC, ISO text) and acting user are stored, an optional note (bounded length, for example 2000 characters) is stored in the system's free-form metadata, and a domain event is published carrying project, system, name, type, the readiness percentage at that moment and the user. The updated system is returned with its readiness. _(beh-008; observed)_
- A system reaches the commissioned state only through the gated action. A plain update that sets status to commissioned is refused with a bad-request outcome telling the caller to use the commission action. Other lifecycle values (not started, in progress, tests complete) may be set by update. _(beh-009; observed)_
- Recording a result on a functional checklist item automatically advances the system's lifecycle label, forward only: if the system is not commissioned and the gate is now satisfied the label becomes tests complete; otherwise if the label is not started it becomes in progress; otherwise it is left unchanged. It never regresses a label and never touches a commissioned system. Results on pre-functional checklists never change the label. The live gate, not the label, protects the commission action. _(beh-010; observed)_
- Checklist items carry a sequence number (zero or more), description, status (pending, pass, fail, not applicable), optional result note, verifier and verification time. Recording a result (pass, fail or not applicable only; never pending) stamps the verifier and time; a note of bounded length may accompany it and an omitted note keeps the existing one. Setting an item back to pending through a general update clears verifier and time. Creating an item directly with a real result also stamps verification. _(beh-011; observed)_
- Checklists have a kind (pre-functional or functional; new checklists default to pre-functional), a title, optional description, optional stage identifier linking the checklist to a stage of a quality concept, and free-form metadata. Only functional checklists influence readiness. _(beh-012; observed)_
- Issues belong to a system and carry description, severity (low, medium, high, critical; default medium), status (open or closed; default open), optional resolution, raiser, closer and close time. Moving an issue to closed stamps close time and user; moving a closed issue back to open clears them. Creating an issue already closed stamps them at creation. _(beh-013; observed)_
- Four advisory validation rules guard writes: (a) closing an issue without a resolution is an error for the two highest severities and a warning for lower ones; (b) labelling a system tests complete while it does not satisfy the gate is a finding; (c) passing a functional item while any pre-functional item has failed is an error and while pre-functional items remain pending is a warning; (d) recording a failed result without a note is a warning. Each rule is silent when its condition does not apply. _(beh-014; observed)_
- Project statistics: total systems, counts by lifecycle status, counts by system type, commissioned count, open issue count, open critical issue count, and average readiness percentage across all systems of the project rounded to two decimals. Systems whose percentage is undefined contribute 0 to the average; a project without systems averages 0. _(beh-015; observed)_
- A system may optionally link to an item of a plant or asset register. The link is stored only when a plant register capability exists and confirms the item inside the same project; with no register capability the request is rejected as unprocessable; with an item not found in the project the request is rejected as not found. _(beh-016; observed)_
- System list: filter by lifecycle status and by system type, bounded page size (for example 1 to 100, default 50) with a non-negative offset; every row embeds its readiness breakdown so a traffic light can be drawn without extra requests. Readiness for many systems is computed with aggregate queries rather than per item. _(beh-017; observed)_
- Deleting a system deletes all its checklists, items and issues; deleting a checklist deletes its items. _(beh-018; observed)_
- Certificate document content for one system covers: title; generation timestamp and a reference identifier of the system; system details (project name, system name, type, tag, location, status, and description only when present; empty values show a placeholder); readiness section; checklists section; issues section; a signature block with two parties (commissioning authority and client representative), each with a name-and-signature line and a date line; and a print hint. _(beh-019; observed)_
- Certificate readiness section has three variants: (1) commissioned systems show a prominent commissioned stamp with commissioning date and user when known; (2) not commissioned with defined readiness shows rounded percentage, a ready or not-ready verdict, the rating, counts of passed, failed, pending, not-applicable and open critical, the blocking reasons under a heading when any, and the formula text; (3) otherwise a message that no functional checks have been defined yet. _(beh-020; observed)_
- Certificate checklist section lists every checklist with its kind label, title and a passed-over-total count, and a table of sequence, check, result and note per item (empty note shows a placeholder; a checklist without items shows a no-checks message; no checklists at all shows a no-checklists message). Issues section lists severity, open or closed state, description and resolution (placeholder when empty), or a no-issues message. _(beh-021; observed)_
- Three concepts: a system is the commissionable unit; a pre-functional checklist records installation-readiness checks and a functional checklist records performance tests. Both kinds hold the same item shape and statuses. Only functional checklists feed the readiness percentage and the gate; pre-functional state only produces advisory findings when a functional item is passed. _(beh-025; observed)_
- Not-applicable items are excluded from the readiness denominator (applicable = total minus not-applicable) and never count as passed, failed or open. They still count in the plain items-in-checklist total. Example: five functional items with four passed and one not applicable give 4 of 4 applicable, 100 percent, and no open items. _(beh-026; observed)_
- A system counts as commissioned only when its stored lifecycle status is commissioned, which is to be reachable only through the gated action. Reaching it requires the gate at that moment: at least one applicable functional item, none failed or pending, no open critical issue, and no quality-concept stage veto. Bulk or initial data loading is a separate decision point (see open questions). _(beh-027; observed)_
- Intended counting rules: two different figures are shown in different places and both are required. (1) The readiness figure is passed items over applicable items, with not-applicable items removed from the denominator; it drives the gate, the list traffic light, the insights view and the certificate verdict. (2) The per-checklist counter shown on the certificate and spreadsheet is passed items over all items in that checklist, including not-applicable and pending ones. A commissioned system whose checklist counter reads 4 of 5 while its readiness reads 4 of 4 is therefore consistent when the fifth item is not applicable. For commissioning and readiness decisions the readiness figure (not-applicable excluded) is authoritative. _(beh-028; derived)_
- All user-supplied text in the printable certificate is escaped before inclusion. The document is opened in a fresh window and the browser print dialog is requested after a short delay; if the window is blocked the operation reports failure; if printing is dismissed the window keeps its content. The document is built entirely client-side from freshly fetched checklists, items, issues and readiness (falling back to the readiness already embedded in the system if the fresh fetch fails). _(beh-022; observed)_
- Spreadsheet (delimited text) export: starts with a byte-order mark for spreadsheet compatibility; every cell is quoted with embedded quotes doubled; contains title, generation time, project, system name, type, tag, location, status, then readiness percentage and a yes/no may-commission value only when readiness is defined; then a checklist table (checklist title, kind, sequence, check, result, note, verified-at) and an issue table (description, severity, state, resolution, raised-at). The file name is derived from the system name by lowercasing and replacing runs of non-alphanumeric characters with a single separator, trimming leading and trailing separators, with a fixed fallback word when empty. _(beh-023; observed)_
- Insights view over the loaded systems builds one row per system with name, type label, status label, location, readiness rating label, integer readiness percent, open functional checks, open critical issues and a commissioned flag. A system with undefined or missing readiness is placed in its own no-checks-defined bucket (not red) and contributes 0 percent; a missing or blank location gets a generic no-location label. Built-in views: system count, average readiness, commissioned count, open critical issues, readiness by system type, systems by status, outstanding checks by location, systems by readiness rating. No currency-formatted measure exists. Empty input yields zero rows. _(beh-024; observed)_

## Inputs

- System create or update: project, name (bounded length), system type from a closed vocabulary of building-system categories (for example heating and ventilation, electrical, fire protection, plumbing, mechanical, controls, lifts, security, other; default heating and ventilation), optional tag, optional location, optional description, lifecycle status from a closed list (default not started), optional plant item reference, free-form metadata. Text is whitespace-trimmed. Metadata on update is merged into existing metadata when it is an object. _(in-001; observed)_
- Out-of-vocabulary values for type, status, kind, severity or result are rejected at the edge as unprocessable before any state change. _(in-002; observed)_
- Commission action accepts an optional note of bounded length. _(in-003; observed)_

## Outputs

- Single-system reads, creates, updates and commission responses include the live readiness breakdown; the dedicated readiness read returns the breakdown alone. _(out-001; observed)_

## States and transitions

- System lifecycle labels in order: not started, in progress, tests complete, commissioned. Automatic movement is forward only and only via recorded functional results; commissioned is reachable only through the gated action. Manual updates may set the first three in any order (setting tests complete while not ready is flagged by a rule). _(st-001; observed)_
- Creating a system directly in tests complete status is flagged because a new system has no functional results. _(st-002; observed)_

## Timing and ordering

- Mutating requests persist their change before responding so that the readiness included in the response reflects the committed state. Checks inside the commission action run in order: already-commissioned, quality-concept stage veto, readiness gate. _(ord-001; observed)_

## Edge cases

- A system with only not-applicable functional items is not ready (at least one must pass) and has undefined percentage; a system with no items is likewise not ready and undefined. _(edge-001; observed)_
- A negative or non-numeric open-critical count supplied to the readiness calculation is treated as zero. _(edge-002; observed)_
- An item changed through a general update that sets a new status also refreshes the verification time; updating without status leaves verification untouched. A general status update on an item does not trigger the automatic lifecycle label advance (only the result action does); see open questions. _(edge-003; observed)_

## Errors

- Missing system, checklist, item or issue yields a not-found outcome. Commissioning an already-commissioned system yields a bad-request outcome. Unexpected failure while creating a system yields a generic server-error message (with the request correlation identifier when available) and never exposes storage internals. _(err-001; observed)_

## What it must not do

- Pre-functional results and closed or lower-severity issues never reduce readiness or block commissioning on their own (pre-functional state only produces advisory findings on functional passes). _(neg-001; observed)_
- The commissioning insights and certificate never show currency; a system carries no money. _(neg-002; observed)_

## Security

- Three permission tiers apply: read-level for all reads, edit-level for every mutation, manager-level for the commission action. Every request additionally verifies that the caller has access to the project that owns the target system (resolved through checklist, item or issue to its system). _(sec-001; observed)_
- Certificate output escapes all dynamic text to prevent script injection; no inline script runs in the generated document. _(sec-002; observed)_

## Invariants

- A system is never commissioned while it has an open functional item, an open critical issue, or no applicable functional item that passed, regardless of its lifecycle label. _(inv-001; observed)_
- The readiness percentage shown in the list, the detail, the certificate and the insights always comes from the same server-side breakdown. _(inv-002; observed)_

## Notes

- Compatibility is behavior-only: percentages to two decimals, rating thresholds, gate conditions and the blocking-reason semantics should match; names, routes and wording need not. Numeric limits quoted for text length, note length and page size are ordinary parameters; the destination chooses its own values. _(comp-001; derived)_

## Non-goals

- Reproducing visual styling, colors, layout or exact wording of the certificate or screens.
- Reproducing origin module layout, names or shared component structure.
- Demo or seed data content, including localized seed text.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Given a system with 7 passed, 1 failed, 2 pending and 0 not-applicable functional items and no critical issues, when readiness is read.  
  Expected: Applicable 10, percentage 70.00, defined, cannot commission, rating red (a failure exists), blocking reasons include a reason stating that 3 functional items have not yet passed.
- **ts-002**: Given 5 passed and 3 pending items and nothing failed.  
  Expected: Percentage 62.50, cannot commission, rating amber.
- **ts-003**: Given 4 passed, 2 not-applicable, 0 other, and no critical issue.  
  Expected: Applicable 4, percentage 100, may commission, rating green, no blocking reasons.
- **ts-004**: Given 4 passed items and 1 open critical issue.  
  Expected: Percentage 100 but cannot commission, rating red, blocking reasons contain one entry about the open critical issue.
- **ts-005**: Given a system with no functional items, and another whose items are all not-applicable.  
  Expected: Both: percentage 0, undefined, cannot commission, rating red, distinct blocking reasons; no non-finite numbers.
- **ts-006**: Given item statuses with surrounding spaces and upper case for pass, a mixed-case fail, and an unrecognised word.  
  Expected: Counted as passed, failed and pending respectively.
- **ts-007**: Given a ready system, when the commission action is invoked with a note by a manager.  
  Expected: Status becomes commissioned, time and user stored, note stored in metadata, completion event published with the readiness percentage; response shows commissioned.
- **ts-008**: Given an unready system, when the commission action is invoked; and given an already commissioned system, when invoked again.  
  Expected: First: bad-request with a not-possible statement plus reasons, state unchanged. Second: bad-request already commissioned.
- **ts-009**: Given a quality-concept stage veto reporting a reason for a ready system.  
  Expected: Commission refused with a conflict outcome containing the reason; state unchanged.
- **ts-010**: When an update sets status to commissioned.  
  Expected: Bad-request telling the caller to use the commission action; status unchanged.
- **ts-011**: Given a not-started system, when its first functional item is recorded as pass while other functional items remain pending; then the remaining items are passed.  
  Expected: Label goes to in progress after the first result, then to tests complete once the gate is satisfied; a later failing result does not move it backward.
- **ts-012**: When a result is recorded on a pre-functional item.  
  Expected: System label unchanged; readiness unchanged.
- **ts-013**: Close a high-severity issue without a resolution; close a low-severity one without a resolution; record a failed result without a note.  
  Expected: Findings: error, warning, warning respectively.
- **ts-014**: Close then reopen an issue.  
  Expected: Close stamps time and user; reopen clears both.
- **ts-015**: Project with systems at 100, 50 and an undefined percentage.  
  Expected: Average readiness 50.00 (undefined counts as 0); with no systems average 0.
- **ts-016**: Link a system to a plant item when no plant register exists; then when the register does not know the item in this project.  
  Expected: Unprocessable, then not found; nothing stored.
- **ts-017**: Build insights for a system with undefined readiness, one with a null location, one commissioned, and an empty list.  
  Expected: No-checks bucket and 0 percent; generic no-location label; commissioned flag 1 (others 0); empty list gives zero rows; no currency measure; percent passed through on a 0-100 scale.
- **ts-018**: Generate the certificate for a commissioned system, for a ready-but-uncommissioned system, and for a system with no functional items.  
  Expected: Stamp variant; percentage, verdict, counts and formula variant; no-checks message variant. Names containing markup characters appear escaped.
- **ts-019**: Export the spreadsheet for a system named with letters, digits, spaces and a slash, with a note containing a double quote.  
  Expected: File name is a lowercase slug of the name with runs of other characters collapsed to one separator; quote doubled inside quoted cell; byte-order mark first; readiness rows appear only when defined.
- **ts-020**: A user without project access requests a system, its checklist, an item or an issue belonging to another project.  
  Expected: Request denied or not found; nothing disclosed or changed.
- **ts-021**: Given a checklist of five functional items with four passed and one not applicable, for a commissioned system.  
  Expected: Readiness reads 4 of 4 applicable, 100 percent, no open items; the per-checklist counter on the certificate and export reads 4 of 5; both are consistent and the readiness figure is the one used for gating and verdict.

## Open questions (decisions for QC Manager)

- Decision: should error-severity findings from the four advisory rules block the write, or only be reported to the caller? The reference behavior left this unresolved.
- Decision: the quality-concept stage veto is an extension point supplied by another capability. Is that capability in scope for the destination? Without it the veto does nothing.
- Decision: the automatic label advance happens only on the result action, not on general item updates or item deletion. Confirm whether the destination should keep this asymmetry or recompute on every change.
- Decision: confirm that the open-critical count means issues with the highest severity and open status.
- Decision: may bulk or initial data loading set a system directly to commissioned, bypassing the gate? If allowed, should such records be re-validated against the gate afterwards?
- Decision: demonstration data and seed checklists, including localized content, are out of scope and may be authored fresh if wanted.
- Decision: screen-level behavior of the list, detail, filters and forms is not specified here beyond certificate, insights and gating.
