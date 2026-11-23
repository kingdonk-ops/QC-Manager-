# 03. Temporary works and scaffold permits

Spec `spec-scaffold-permits-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Behaviour of a project register of temporary works (falsework, formwork, propping, excavation support, access scaffolding, facade retention, crane bases, edge protection, dewatering, hoarding, other) governed by a gated lifecycle: design check, a coordinator-issued permit to load, use, then a permit to strike or dismantle. Clearance to load and to strike is derived only from positive evidence (a live, in-date permit with recorded prerequisites); any item bearing load without such a permit is reported as a compliance breach. Overdue-to-load and overdue-to-strike detection and a design-clearance percentage complete the rollup. Periodic inspection intervals do not exist in the origin; related behaviour that does exist is described and the gap is recorded as an open question. Observed inconsistencies and unenforced rules are carried as decision points, not requirements. Numeric limits (text lengths and similar) are indicative; the destination chooses its own values.

## Behaviour

- An item has: a reference unique within its project (non-empty, short bounded length), a title (non-empty, bounded), optional description (bounded), a family (falsework, formwork, propping, excavation support, scaffold, facade retention, crane base, edge protection, dewatering, hoarding, other), an optional design check category of 0, 1, 2 or 3, optional designer, checker and coordinator names and coordinator user, a status (default identified), optional required load date, required strike date and design due date, optional location, a non-negative sort order, notes, and optional soft cross-references to related records elsewhere in the system (for example formwork assignment, design document, check certificate, schedule activity). _(sp-b001; observed)_
- Item statuses in main-flow order are identified, design brief, design submitted, design checked, approved to load, loaded, in use, approved to strike, struck, removed; on hold is a side status with no position in the flow. _(sp-b002; observed)_
- A permit is issued against exactly one item and has a number (non-empty, short bounded length), a kind (permit to load, permit to strike, permit to dismantle), a status (draft by default, issued, active, expired, closed), the issuing coordinator's name, issued, valid-from, valid-to and closed dates (calendar days, no times), a closing user, a soft reference to an inspection record (identifier-sized), two prerequisite flags (design check accepted, inspection passed; both default false) and conditions text (bounded). _(sp-b003; observed)_
- A permit is valid on a given day only when its status is issued or active and the day lies within its validity window, inclusive at both ends; a missing start leaves the window open on that side and a missing end leaves it open on that side. Draft, expired and closed permits are never valid, and an unknown status never counts as valid. _(sp-b004; observed)_
- An item is cleared to load on a given day only when it has a permit to load that is valid that day and records both prerequisites (design check accepted and inspection passed). If any element is missing the gate is shut. The item's own status does not influence this gate. _(sp-b005; observed)_
- An item is cleared to strike on a given day only when it has a valid permit to strike. A valid permit to dismantle does not open the strike gate. _(sp-b006; observed)_
- A compliance breach exists for each item whose status is loaded or in use that has no valid permit to load on the as-of day (no permit, or a draft, expired, closed or out-of-window one). Each breach reports the item identifier, reference, title and a plain-language reason naming the status and the date. The register is compliant exactly when there are no breaches. The prerequisite flags are not part of the breach test (only validity of a permit to load is); whether they should be is a decision point. _(sp-b007; observed)_
- An item is overdue to load when it has a required load date strictly before the as-of day and its status is none of approved to load, loaded, in use, approved to strike, struck, removed. A required date equal to the as-of day is not overdue; a missing date is never overdue. How items on hold with a past required load date are treated is a decision point (the origin counts them as overdue on the server). _(sp-b008; observed)_
- An item is overdue to strike when it has a required strike date strictly before the as-of day and its status is neither struck nor removed; a required date equal to the as-of day or a missing date is not overdue. Whether items that are still pre-approval or on hold with a past strike date should count (the origin counts them) is a decision point. _(sp-b009; observed)_
- Design clearance percentage is the number of items whose status is design checked or any later main-flow status (design checked, approved to load, loaded, in use, approved to strike, struck, removed; on hold excluded) divided by all items in the register, times 100, rounded half-up to two decimals; for an empty register it is undefined (absent), never zero, and is serialised as a plain decimal string. _(sp-b010; observed)_
- The rollup contains: as-of date, total, status counts with every known status present (zero when empty), category counts for 0, 1, 2, 3 and an unassigned bucket (zero when empty) summing to the total (an out-of-vocabulary value is still counted, never dropped), the design clearance percentage, the compliant flag, overdue-to-load and overdue-to-strike item references (identifier, reference, title, family, status, required dates as text), compliance breaches, and per-item gate indicators. _(sp-b011; observed)_
- The load-status view returns the as-of date, the total, the compliant flag, per-item gate indicators and the breach list. The as-of day defaults to the current UTC date; a malformed as-of value is rejected as invalid input. _(sp-b012; observed)_
- Fail-safe principle: every gate answers cleared only on positive evidence; missing data, unknown statuses, unknown permit kinds or expired windows all read as not cleared or as a breach, never as cleared, and a stray unknown value cannot break the whole-register rollup. _(sp-b013; observed)_
- Independent check rule (error): for design check category 2 or 3, from status design checked onward through approved to strike, a named checker is required and the checker must differ from the designer (comparison ignores case and surrounding spaces). Items still in earlier statuses, or in categories 0, 1 or unassigned, are not subject to the rule. _(sp-b014; observed)_
- Coordinator rule (error): from status approved to load through approved to strike an item must name its temporary works coordinator, by name or by user; earlier statuses may leave it blank. _(sp-b015; observed)_
- Date order rules on items: a required strike date earlier than the required load date is an error; a design due date later than the required load date is a warning. _(sp-b016; observed)_
- Date order rules on permits (errors): valid-to earlier than valid-from; closed date earlier than issued date. Permit-to-load rule (errors, one per missing flag): a permit to load whose status is issued or active must have both prerequisites recorded. _(sp-b017; observed)_
- Validation runs on item and permit creation, and on updates only when at least one rule-relevant field is part of the update (status, category, people, dates, permit kind, validity dates, closed date, prerequisite flags). On update the rules judge the stored record merged with the pending change, and warnings are retained on the operation rather than blocking. _(sp-b018; observed)_
- Item references are unique within a project: creating or renaming an item to a reference already used by another item in the same project gives a conflict; keeping its own reference on update is accepted. _(sp-b019; observed)_
- Items list in ascending sort order then creation time and can be filtered by family, status and category; an out-of-vocabulary filter value is rejected as invalid input. Permits list in creation order and can be filtered by item and status; an out-of-vocabulary status is rejected. _(sp-b020; observed)_
- Deleting an item deletes its permits. Permits can be created, listed and updated (including closing through updating fields) but there is no way to delete a permit on its own. _(sp-b021; observed)_
- A partial update changes only supplied fields; an explicit null clears an optional field and an omitted field is untouched. _(sp-b022; observed)_
- Register screen: four headline figures (items, design clearance percentage or a dash when undefined, items bearing load as the sum of loaded and in use, breaches with error tone above zero); items are shown in expandable rows with a distinct tag and tint when the item is breaching; a search field over reference and title, and filters by status and family; a showing-count; a no-results hint when filters empty the list; loading placeholders. Each item exposes its permits with kind, number, status, validity range and, for permits to load, indicators for the two prerequisites, and can add or edit permits and items in modal forms with validation messages after interaction. _(sp-b023; observed)_
- Lifecycle preconditions as the origin actually enforces them: the intended order is design brief, independent design check (rigour by category 0 to 3), coordinator permit to load carrying design-check-accepted and inspection-passed records, use, then permit to strike or dismantle. Only these are enforced: from design checked onward a category 2 or 3 item needs a distinct named checker; from approved to load onward a coordinator must be named; a permit to load that is issued or active must carry both prerequisite records. Reaching a later status does not itself require an earlier permit, an earlier status or a category; the one status-linked safety test is the breach rule for loaded and in use items. _(sp-b025; observed)_
- Trigger of the bearing-load warning: it is computed per request from current data and fires for an item exactly when its status is loaded or in use and no permit to load on it is simultaneously of status issued or active and within its validity window on the as-of day. Items in any other status (including approved to load, approved to strike and on hold) never trigger it, whatever their permits. _(sp-b026; observed)_
- After a breach the origin does nothing automatically: it changes no status, blocks no edit, sends no notification, publishes no event and writes no trail entry for this module. The breach is only shown (banner, per-item tag, headline figure) and returned by the rollup and load-status views until a valid permit to load is recorded or the item's status is changed. _(sp-b027; observed)_
- Overdue inspections are not computed anywhere: the only inspection-related data are a soft reference and a manual passed flag on a permit, so there is no overdue-inspection list, count or warning. Overdue loads and overdue strikes are computed as in the overdue rules above, by comparing the required dates with the as-of day and the item status. _(sp-b028; observed)_
- Insights derived on the client from the loaded items: counts by family, status and design check category, items added per month, items bearing load, items design cleared, items on hold, items overdue to load (required load date before today and status in a pre-load group that excludes on hold), and average days on the register (live items measured to now, struck or removed items measured to their last update, never negative). No monetary values exist. _(sp-b024; observed)_

## Inputs

- Item creation requires reference, title and family; everything else is optional. Permit creation requires number and kind; the item and project come from the request context, never from the body. _(sp-i001; observed)_
- Dates cross the interface as year-month-day text and are parsed as calendar dates; the permit validity window carries no time of day. _(sp-i002; observed)_

## Outputs

- Item and permit responses echo all stored fields plus identifiers, project, creator and created/updated times; the permit response also carries the item identifier. _(sp-o001; observed)_
- Clearance and overdue results are never stored; they are recomputed from the rows for each request and for the requested as-of day. _(sp-o002; observed)_

## States and transitions

- Item status is changed only by editing the item. The origin applies no transition guard, so any status in the vocabulary may be set from any other, subject only to the validation rules above; whether to add guarded transitions is a decision point. _(sp-t001; observed)_
- Permit status is changed only by editing the permit; the origin has no transition guard and no dedicated issue, activate or close action. Expiry is judged by date window at evaluation time rather than by moving the stored status. _(sp-t002; observed)_

## Timing and ordering

- Project access is checked first on every operation, then the permission; permit operations additionally re-verify that the item belongs to the same project before writing or listing. _(sp-o003; observed)_
- Item creation checks reference uniqueness before running validation rules. _(sp-o004; observed)_

## Edge cases

- Boundary days: a permit whose valid-to equals the as-of day is still valid; the day after it is not. A required load or strike date equal to the as-of day is not overdue; the day before is. _(sp-e001; observed)_
- A register with no items yields total zero, undefined design clearance, compliant true, empty lists and zero-filled count tables. _(sp-e002; derived)_
- An item approved to load without any permit is not a breach (it is not yet bearing load) but its load gate is shut; an item whose permit to load has both prerequisites but whose status is still pre-approval has an open load gate and no breach. _(sp-e003; derived)_
- The actor identifier recorded as creator is stored only when it is a well-formed identifier; otherwise it is stored as absent rather than corrupting the record. _(sp-e004; observed)_
- Percentages round half up: one cleared item out of three reads 33.33, two of three 66.67, one of two 50.00. _(sp-e005; derived)_

## Errors

- Not-found outcomes: an item or permit that is missing, or belongs to another project, or a project the caller cannot access, all give the same not-found result. Listing permits by an item of another project is not-found. _(sp-x001; observed)_
- Conflict on duplicate item reference within a project; invalid input on out-of-vocabulary family, status, category, permit kind or permit status, on bad lengths, on malformed as-of dates, on bad filters, and on validation rule errors (with the failed rules identified). _(sp-x002; observed)_

## What it must not do

- No periodic inspection interval, next-inspection-due date, inspection tag, handover certificate or inspection reminder exists in the origin for scaffolds or any other family. Only a soft reference to an inspection record and a manually set inspection-passed flag on permits exist. _(sp-n001; observed)_
- Scaffold items have no behaviour different from other families; no scaffold-specific rules, vocabularies or screens exist. _(sp-n002; observed)_
- A permit to strike or dismantle is not required to carry prerequisite flags and its prerequisite flags have no effect on any gate; the register does not warn when a strike date has passed and no valid permit to strike exists other than by listing the item as overdue to strike. _(sp-n003; observed)_

## Security

- Reading items, permits, the rollup and the load-status view needs viewer level; creating, editing and deleting items and creating or editing permits need editor level (changes move safety gates). There is no manager-only step for issuing permits in the origin; whether issuing should need a higher role is a decision point. _(sp-sec001; observed)_
- Every operation is scoped by project and checked with a project-access guard that answers not-found for both missing and denied, so strangers cannot read or mutate another project's data; a permit can never be attached across projects. _(sp-sec002; observed)_

## Invariants

- Item reference is unique within a project. _(sp-inv001; observed)_
- A permit's project always equals its item's project. _(sp-inv002; observed)_
- The register is compliant if and only if no item is loaded or in use without a valid permit to load; category counts and status counts always sum to the total. _(sp-inv003; observed)_
- Cleared-to-load implies a valid permit to load exists; a valid permit to load alone without both prerequisites does not clear the gate. _(sp-inv004; derived)_

## Notes

- Design check categories 0 to 3 follow the common temporary works governance convention where rigour of independent checking rises with category; the destination should keep the four values and the independence rule for categories 2 and 3. _(sp-cn001; inferred)_
- Text length limits and similar numeric bounds are indicative behavioural parameters; the destination chooses its own values. The gate, breach, overdue and clearance-percentage rules, the day-boundary conventions and the fail-safe principle are the behaviour to preserve. _(sp-cn002; derived)_

## Non-goals

- Reproducing origin table, field, route, permission or event identifiers, wording or layout.
- Reproducing origin seed data.
- Inventing a periodic scaffold inspection scheduler that the origin does not have (if wanted, it is a new feature to be decided separately).
- Specifying the neighbouring HSE permit-to-work or inspection modules.
- Do not reproduce origin provenance markers.

## Test cases

- **sp-test-001**: Given an item with an issued permit to load valid from last week to next week with both prerequisites recorded, when load status is read for today, then the item is cleared to load.  
  Expected: The item's cleared-to-load indicator is true; no breach.
- **sp-test-002**: Given the same permit but with the inspection prerequisite missing, when load status is read, then the load gate is shut; given both recorded but the status draft, shut; given a window that ended yesterday, shut.  
  Expected: Gate shut in each case.
- **sp-test-003**: Given a permit to load valid with no end date and a start date in the past, when evaluated today, then it is valid; with a start date tomorrow it is not valid.  
  Expected: Open-ended bounds honoured.
- **sp-test-004**: Given an item with only a valid permit to dismantle, when load status is read, then strike gate is shut; with a valid permit to strike it is open.  
  Expected: Only a permit to strike opens the strike gate.
- **sp-test-005**: Given an item in use whose only permit to load is a draft, when the register is read, then one breach appears with a reason naming the status and the date and the register is not compliant; after the permit becomes issued within its window, no breach remains.  
  Expected: Breach list and compliant flag follow the rule.
- **sp-test-006**: Given an item approved to load with no permit and an item loaded with a valid permit to load, when read, then neither is a breach.  
  Expected: No breaches; first item gate shut.
- **sp-test-007**: Given items with required load date yesterday in statuses design checked and approved to load, when read today, then the first is overdue to load and the second is not; with required date today neither is overdue. The outcome for an on-hold item is left to the destination decision.  
  Expected: Overdue rule with settled statuses excluded and boundary day not overdue.
- **sp-test-008**: Given items with required strike date yesterday in statuses in use, struck and removed, when read, then only the in-use item is overdue to strike.  
  Expected: Strike overdue excludes struck and removed.
- **sp-test-009**: Given four items in statuses identified, design checked, loaded and on hold, when the rollup is read, then design clearance is 50.00; with three items of which one is cleared it is 33.33; with none it is absent.  
  Expected: Percentage rules including undefined for empty.
- **sp-test-010**: Given items of two families and categories 1, 3 and unassigned, when the rollup is read, then status counts list all eleven statuses, category counts list 0, 1, 2, 3 and unassigned with zeros where empty, and counts sum to the total.  
  Expected: Zero-filled tables that sum to total.
- **sp-test-011**: Given a category 2 item set to design checked with the checker equal to the designer apart from capitalisation, when saved, then it is refused; with a blank checker, refused; with a different checker, accepted; a category 1 item with the same names is accepted; the same category 2 item still in design submitted is accepted.  
  Expected: Independent check rule on stage and category.
- **sp-test-012**: Given an item set to approved to load with no coordinator name or user, when saved, then it is refused; with a coordinator name it is accepted; while in design brief it is accepted without one.  
  Expected: Coordinator required from approval to load onward.
- **sp-test-013**: Given required load date 2026-03-10 and required strike date 2026-03-01, when saved, then refused; given design due date 2026-03-15, saved with a warning only.  
  Expected: Strike-before-load is an error; late design due is a warning.
- **sp-test-014**: Given a permit to load with status issued and neither prerequisite recorded, when created, then two errors are reported; with status draft, none; a permit with valid-to before valid-from is refused.  
  Expected: One error per missing prerequisite; ordering errors block.
- **sp-test-015**: Given an update that changes only the notes of an item stored in a state that would now fail a rule, when saved, then no rules are run and it succeeds.  
  Expected: Rules run only when a relevant field is changed.
- **sp-test-016**: Given an existing item with reference A in a project, when another item with reference A is created in the same project, then a conflict is returned; in another project it is accepted; renaming an item to its own reference succeeds.  
  Expected: Uniqueness per project.
- **sp-test-017**: Given an item of another project, when a permit is created or listed for it from a project the caller can access, then not-found is returned; when an item is deleted, its permits disappear.  
  Expected: No cross-project attachment; cascade on delete.
- **sp-test-018**: Given a filter by an unknown status or an as-of value that is not a date, when requested, then invalid input is returned.  
  Expected: Vocabulary and date validation at the boundary.
- **sp-test-019**: Given a viewer-level user, when they list items or read the rollup, then it succeeds; when they create an item or permit, permission is denied; an editor can.  
  Expected: Read viewer, write editor.
- **sp-test-020**: Given a register with one breaching item, when the screen loads, then the breach banner is shown first with a count of one and the item's reason, the breaches headline figure has the error tone and the item row is tagged; given no breaching item, the reassurance banner appears instead.  
  Expected: Safety signal first; reassurance only when compliant.
- **sp-test-021**: Given overdue-to-load count 2 and overdue-to-strike count 0, when the screen loads, then the secondary banner mentions only the load count; with both zero it is not shown.  
  Expected: Banner shows non-zero counts only.
- **sp-test-023**: Given an item whose status has been set to loaded while no permit exists at all, when the register is read, then the item appears as a breach and no notification or status change follows; given the item is in use with a valid permit to load, no breach. The origin baseline does not block the save itself (see open questions).  
  Expected: Breach is informational only and driven by status plus permit validity.
- **sp-test-024**: Given any scaffold item with a past required load date and a valid inspection reference but no permit, when read, then no overdue-inspection output exists; only overdue-to-load can apply.  
  Expected: No inspection overdue concept; scaffolds behave like any family.
- **sp-test-022**: Given the as-of date is set to a date after a permit's validity end, when the load status is read with that date, then the item that was cleared today is no longer cleared and a loaded item becomes a breach.  
  Expected: Results depend on the as-of day, not on stored status.

## Open questions (decisions for QC Manager)

- Gap: the requested feature scope mentions inspection intervals for scaffolds, but the origin has no periodic inspection scheduling, interval rule, tag or reminder (only a soft inspection reference and a manual passed flag). Decision: should the destination add a configurable inspection interval (for example, a recurring inspection due date per item with overdue warnings), and if so what interval default and who may record inspections? This would be new behaviour, not parity.
- Gap: the origin has no scaffold-specific behaviour (scaffold is one of eleven families). Decision: does the destination need scaffold-specific fields such as handover date, loading class or erector, or is the generic family enough?
- Decision: the strike gate ignores permits to dismantle; should a permit to dismantle also authorise removal for families that are dismantled rather than struck?
- Decision: the origin allows any status to be set on items and permits without transitions or issue, activate and close actions. Should the destination add guarded transitions and audit entries, especially for permits to load, and who may issue them (the origin gives editors the right)?
- Decision: overdue-to-load treats on-hold items as overdue on the server but the client-side insights exclude them; which is intended? Also overdue-to-strike counts items that have not reached approval to load; confirm that is desired.
- Decision: the breach rule tests only that a valid permit to load exists, whereas the load gate also requires both prerequisites. Should an item bearing load under a valid permit that lacks prerequisites also be flagged?
- Decision: a permit's stored status can remain issued or active after its window ends; the gates ignore it by date, but nothing marks it expired or warns that a live permit is about to lapse. Should the destination add an expiring-soon warning and automatic expiry?
- Decision: there is no permit delete and no item change history; confirm whether permits and changes need an audit trail (this origin writes none for this module).
- Decision: after a breach the origin takes no action (no alert, notification, block or escalation). Should the destination notify the coordinator, block further work, or require a recorded response and who must acknowledge it?
- Decision: because status changes need no preconditions, an item can be set loaded without any design check, category or coordinator for categories 0 and 1; should the destination block entry to approved to load, loaded or in use unless the design check and a valid permit to load exist?
- Decision: the origin has no scaffold tags (green or red handover or in-use markers); the coordinator-recorded inspection-passed flag is the only analogue. Should the destination add tag status for scaffolds?
- Decision: the origin computes today in UTC for as-of defaults; confirm the destination's site time zone rule.
- Decision: warnings produced by item and permit rules are retained on the operation but it is unknown whether they are returned to the caller; the destination should define how warnings are surfaced.
- Unknown: form modal details and the item detail interactions of the origin screen were only skimmed.
