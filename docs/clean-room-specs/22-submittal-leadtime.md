# 22. Submittal lead-time warnings

Spec `spec-submittal-leadtime-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A submittal register (items the contractor sends to a reviewer for approval before ordering or installing) that answers three recurring schedule questions from stored values and today's date: how long an item has been with the reviewer and whether that exceeds the contract's review period; by what date an approval must be granted for a long-lead item to reach site when needed (required-on-site date minus lead time); and how many days late that approval already is. Unknown inputs yield an explicit unknown, never a guess or default. Derived figures appear on every row, in register header counts, as list filters, in advisory validation findings, and as badges. The remaining submittal lifecycle (statuses, review stamps, revision history, permissions, attachments, exports) is summarised more briefly.

## Behaviour

- Date reading rule: a stored date is read from its first ten characters as year-month-day; anything shorter or unreadable counts as absent (not an error). A whole-number input is a non-negative integer; negatives, booleans and non-numbers count as absent. 'Today' is a date supplied by the caller (the current UTC calendar date in production) so results can be pinned in tests; all day counts are whole calendar days with no working-day calendar. _(beh-001; observed)_
- Approval needed-by date = required-on-site date minus (lead time in weeks times seven days). It is the last day an approval still lets the item arrive when the site needs it. If either the required-on-site date or the lead time is absent the result is unknown. No default lead time is ever assumed. _(beh-002; observed)_
- Approval late days (the at-risk measure) = the number of days today is past the needed-by date, floored at zero (zero means the date has not passed or is today). It is unknown when the needed-by date is unknown, when today is unreadable, when the item already carries a release outcome (approved or approved as noted), or when the status is outside the pursued set. Statuses where lateness applies: draft, submitted, under review, returned for revision, rejected. Closed and approved items are excluded. An item is flagged late exactly when this number is greater than zero. The rule applies to any item with both inputs, whether or not it is flagged long-lead. _(beh-003; observed)_
- Submit-by date = approval needed-by date minus the review period in days: the last day to submit so that one full review still ends by the needed-by date. Unknown when either input is unknown. _(beh-004; observed)_
- Review due date = date submitted plus review period in days; unknown when the item was not submitted or has no review period. Review overdue days = days today is past the review due date, floored at zero, but only for items currently with the reviewer (submitted or under review); unknown for other statuses, for an unknown due date or unreadable today. An item is overdue when this number is greater than zero. _(beh-005; observed)_
- Days in review = calendar days from date submitted to date returned when a return date exists; otherwise, only while the item is with the reviewer, from date submitted to today; unknown when never submitted, when the item is not with the reviewer and has no return date, or when the end date precedes the start date. _(beh-006; observed)_
- Unknown is distinct from zero throughout: derived figures that cannot be determined are returned empty and displayed as an empty cell; zero means determined and not late. There is no default review period. _(beh-007; observed)_
- Effective review outcome is the stored reviewer decision for the current revision; if none is stored and the status is itself a decision (approved, approved as noted, revise and resubmit, rejected) that status is the outcome, so older records still read correctly; otherwise none. The stamp code is the stored code or, if none, a default short code defined per outcome (the destination chooses the default code set); none when there is no outcome. The may-proceed flag is true for approved and approved as noted only. The resubmit-for-record flag is true only for approved as noted when the latest history entry for the current revision recorded it. _(beh-008; observed)_
- Register header counts are computed over the project's items as of today: total; per status, type and discipline in first-seen order without zero-filling (an item with no discipline counts under an empty code); per outcome always listing all four outcomes with zero counts and the default stamp code; awaiting review (submitted or under review); of those, overdue (past the review period) versus review-period-unknown, which never overlap and together do not include items inside their period; long-lead total; long-lead items still open for approval (status in the pursued set and not released); of those, the ones with no computable needed-by date (because lead time or required-on-site date is missing); and approval-late count (items flagged late by the rule above, regardless of long-lead flag). _(beh-009; observed)_
- Advisory validation (register rules) reports findings and never blocks any action: a long-lead item without a lead time (error severity, because its needed-by date cannot be computed); an item still unapproved past its approval needed-by date (warning, reporting days late and the date); a required-on-site date earlier than the submission date (error); a material-type submittal (product data or sample) without a manufacturer (warning); a resubmission at revision 2 or later with no recorded review of the previous revision (warning); and a stamped outcome that contradicts status (error: a decision status with a different stamped decision, an item still with the reviewer that already carries a stamp, or a closed item stamped as returned for revision). No stamp is not a contradiction. Each finding has a localised message and a suggestion; messages exist in more than one language and other languages fall back to a default language. _(beh-010; observed)_
- Submission-time advisory checks (also on demand): reviewer assigned; required review date present; required review date not before the submission date (a past date means late on arrival); a minimum review window between submission and required date (warning, because urgent items exist; skipped when the date is already before submission to avoid double-reporting; the destination chooses the minimum, observed on the order of two weeks); specification section present; approver differs from reviewer (warning); at least one linked scope item (warning). Findings are folded into a structured state-change log entry on submit but do not refuse the submit; if the advisory check itself fails the submit proceeds. _(beh-011; observed)_
- Filtering: the list accepts status, type (nine types: shop drawing, product data, sample, mock-up, test report, calculation, method statement, certificate, warranty), discipline code, review outcome, review code, long-lead flag, review-overdue flag and approval-late flag, plus sort field and direction (default newest first), and a bounded page size. The two derived-figure filters depend on today's date, so they are applied after the stored-value filters, then the page is cut; their total reflects only matching rows. Sorting is allowed only on stored values (creation time, number, title, type, discipline, status, outcome, manufacturer, the three review dates, required-on-site date, lead time), never on derived figures. _(beh-012; observed)_
- Input bounds: review period 0 to 365 whole days; lead time 0 to 260 whole weeks; required-on-site date as a calendar date; discipline normalised (trimmed, lower-cased, spaces and hyphens to underscores) then must be a short lower-case code starting with a letter (letters, digits, underscores, bounded length), and any code outside the default list is accepted and displayed as stored; country of origin upper-cased two-letter code; manufacturer, model and supplier length-bounded, blank means absent. Values beyond bounds are rejected as invalid input. The form pre-validates the same bounds and shows a range message. These ranges are observed values; the destination chooses its own limits. _(beh-013; observed)_
- Long-lead handling in the form: ticking long-lead reveals lead time and makes it required (save disabled until a valid value exists); unticking hides the lead time and clears its value; a row that has a lead time but no flag still shows the lead time so stored data is never hidden. On the server the lead time is not required by input validation; the missing lead time is reported by the advisory rule above and counted in the header. _(beh-014; observed)_
- The server offers a default discipline vocabulary (a set of common building trades, each with a short mark and a localised label; the destination chooses its own set). The form offers a pick list plus an 'other' entry to type a project-specific code, and opens in typed mode when an existing value is not in the list. A material-type submittal with no manufacturer shows a non-blocking prompt. _(beh-015; observed)_
- Due-date badge (client, based on the filer's required review date): shows nothing when the date is missing or malformed, or when the status is approved, approved as noted, rejected, closed or returned for revision (the item is with the submitter and the date will reset on resubmission). Otherwise, measured in whole UTC calendar days from today: negative shows an error-level 'overdue by N days'; zero shows a warning-level 'due today'; 1 to 7 shows a warning-level 'due in N days'; more than 7 shows nothing. Submitted and under review are treated the same. Band boundaries are observed values; the destination may tune them. _(beh-016; observed)_
- With-reviewer-age badge: shown only while status is submitted or under review and a submission date is readable. The day count is the server's days-in-review figure when supplied (used as given, no subtraction on the client); otherwise whole UTC calendar days from submission to today, clamped at zero. Under 3 days: nothing. 3 to 7: neutral. 8 to 13: warning. 14 and over: error plus screen-reader-only text that the review-time guideline is breached. The 14-day figure is a review turnaround guideline. Band boundaries are observed values; the destination may tune them but should keep the ordering of bands. _(beh-017; observed)_
- Server-supplied figures are authoritative on screen: the register prints days in review, days overdue and days late exactly as the server sent them and never recomputes them from dates. The needed-by deadline shown in edit mode is also the server's. _(beh-018; observed)_
- Lifecycle summary: statuses are draft, submitted, under review, approved, approved as noted, revise and resubmit, rejected, closed. Allowed moves: draft to submitted; submitted or under review to under review or any of the four decisions; approved or approved as noted to closed; revise and resubmit to draft or submitted; rejected to draft or closed; closed is terminal. A plain edit may only move an item to draft, submitted or under review; decisions and closing must use the dedicated submit, review or approve actions, otherwise the edit is refused as forbidden; an illegal move is refused as a client error naming the allowed moves. A closed item cannot be edited. _(beh-019; observed)_
- Submit (from draft or revise and resubmit only): status submitted, date submitted set to today (UTC), return date cleared; revision becomes 1 for a first submission or increases by one when replacing an already-returned revision (after revise and resubmit, or a rejection taken back to draft), in which case the previous stamp and code are cleared from the current revision (they remain in history); the item moves into the reviewer's court when a reviewer is assigned. _(beh-020; observed)_
- Review (from submitted or under review only): records decision, reviewing user, return date today, stamp outcome, stamp code (as supplied or the default code), appends a history entry (revision, outcome, code, submitted and returned dates, reviewer, notes, resubmit-for-record flag which can only be true for approved as noted), and stores trimmed review notes. Responsibility moves to the original submitter for revise and resubmit or rejected, otherwise stays with the reviewer. Approve (from submitted or under review) sets approved, records approver, return date today, clears the responsible party, stamps the outcome; approving an already approved item returns it unchanged (idempotent). _(beh-021; observed)_
- A resubmission at revision N with a history entry for revision N-1 is shown as 'revision N replaces revision N-1, which came back as <code> (<outcome>)' with the reviewer's notes and a 'current revision, no decision yet' line; the review dialog offers outcome choices with a short hint of what each means for ordering, a stamp-code input whose placeholder is the default code for the chosen outcome, and a corrected-copy-for-record option shown only for approved as noted. Wording is illustrative; the destination uses its own copy. _(beh-022; observed)_
- Deleting is refused (conflict) for approved, approved as noted and closed items because they are the approval record. State changes emit a structured log record, state-change event notifications and an audit record; event publication failure never breaks the action. _(beh-023; observed)_
- Insights (count-and-age only, no money): days open from creation to now for open items, or to last update for done items (approved, approved as noted, rejected, closed); overdue flag means open and the filer's required date earlier than now; average days to approve over approved items only; who-owes-the-next-move derived from status alone (draft awaiting submission, revise and resubmit awaiting resubmission, done closed out, else awaiting review); counts by type, status, and by creation month. _(beh-024; observed)_

## Inputs

- Create or edit inputs relevant to lead time: required-on-site date, long-lead flag, lead time in whole weeks, review period in whole calendar days, filer's required review date, plus the other register fields. Edits are partial; the form sends only changed values and sends an explicit empty value to clear one. _(in-001; observed)_
- Review input: one of four decisions, optional notes (bounded length), optional stamp code (short, bounded), optional resubmit-for-record flag. Approve input: optional notes and optional stamp code. _(in-002; observed)_
- List and summary inputs: project (required), filters and sort as in the filtering behavior; an optional as-of date may exist internally but production uses the current UTC date. _(in-003; observed)_

## Outputs

- Every submittal response carries the derived figures: days in review, review due date, review overdue days, approval needed-by, approval late days, submit-by, effective outcome, stamp code, may-proceed and resubmit-for-record, each empty when not determinable; dates as calendar dates. Records lacking the underlying inputs return the affected figures empty and still render. _(out-001; observed)_
- The summary response lists the as-of date used, the counts in the header behavior and the code-count breakdowns; the vocabulary response lists types, default disciplines (with marks), the four outcomes (with default codes) and the sortable fields, all labelled in the requested language with a default-language fallback. _(out-002; observed)_
- The validation report lists each rule with severity, category, pass flag, localised message, element reference (submittal number, else a title excerpt), and suggestion; the UI lists only the rules that did not pass, each with its suggestion. _(out-003; observed)_

## States and transitions

- At-risk status of an item changes with time without any edit: a long-lead item with known inputs moves from not late to late when today passes its needed-by date and stays late while it remains unapproved in a pursued status; it stops being late the moment it is approved or approved as noted, or is closed. _(st-001; derived)_
- Resubmission resets the review clock: date submitted becomes the new submission date and return date clears, so days in review and review due date restart. _(st-002; derived)_

## Timing and ordering

- Derived figures are computed at read time for each request against the current UTC date; nothing is stored, so they change daily without edits. The edit form shows the stored-values-derived deadline only until an input is touched, then says it will be recalculated on save. _(ord-001; observed)_
- A register shortcut opens its cut alone: choosing an outcome chip clears other filters; filters chosen manually combine and all of them also apply to the export. _(ord-003; observed)_

## Edge cases

- As-of date equal to the needed-by date yields zero late days (not late); one day after yields one. A negative difference is floored at zero. A zero lead time makes the needed-by date equal the required-on-site date. A zero review period makes review due the submission day. _(edge-001; derived)_
- Item with a lead time but no required-on-site date, or the reverse, has no needed-by date and is never reported late; if it is long-lead and awaiting approval it is counted in the 'cannot compute' header figure. _(edge-002; observed)_
- An item with no review period, awaiting review, counts as period-unknown, not overdue and not inside the period; the row shows days in review without an overdue suffix. _(edge-003; observed)_
- Dates whose return precedes submission, or future-dated submissions, never yield negative figures: days in review is unknown for backwards dates; client day counts for the with-reviewer-age badge are clamped at zero and hidden below the lowest band. _(edge-004; observed)_
- Older records with a stored status that is a decision but no stored outcome are treated as having that outcome, so an old approved record is not shown as late and counts as released. _(edge-005; observed)_
- A rejected item taken back to draft, and a rejected item left in place, remain in the lateness scope; once resubmitted the item is submitted again and the new revision has no outcome. _(edge-006; derived)_

## Errors

- Out-of-range or malformed lead time, review period, dates, discipline, country code or filter values are rejected as invalid input before any derivation. _(err-001; observed)_
- Review attempted from a status other than submitted or under review, approve from other statuses (except the idempotent approved case), submit from other than draft or revise and resubmit, illegal status moves, and edits to a closed item are client errors; plain-edit moves to decision or closed statuses are forbidden; delete of a released or closed item is a conflict; missing item is not found; approve beyond the per-user rate limit is a too-many-requests error. _(err-002; observed)_

## What it must not do

- No date or deadline is ever guessed: no default review period, no default lead time, no assumed required-on-site date. The edit form never computes the deadline itself. _(neg-001; observed)_
- Advisory findings never block submit, review or approve. A plain edit can never write the review outcome or stamp code; only the review and approve actions can. _(neg-002; observed)_
- Derived figures are not sortable; they are filtered and counted instead. _(neg-003; observed)_
- No working-day calendar, holiday handling, time-zone local day logic or business-hours arithmetic is applied; all counts are calendar days on the UTC date. _(neg-004; observed)_

## Security

- Read, summary, vocabulary, validation report and attachment listing need viewer; create and edit/submit and attachments need editor; delete needs manager. Review and approve require the manager role in addition to edit permission and are the only ways to record a decision; approve is rate-limited per user. All item operations require membership of the item's project. _(sec-001; observed)_

## Invariants

- The register, its header counts, filters and advisory findings all use the same derivation rules, so a finding and the figure beside it cannot disagree. _(inv-001; observed)_
- Late approval means unapproved (no release outcome) after required-on-site minus lead time; review overdue means with the reviewer past the contract period. The two are independent and may both apply. _(inv-002; derived)_
- Overdue and period-unknown header counts never overlap; each awaiting-review item is in exactly one of overdue, within period, or period-unknown. _(inv-003; observed)_

## Notes

- No exact public contract is required. The destination should keep its own naming but must reproduce the derivation rules, the unknown-versus-zero distinction, the status scope for lateness and the filter semantics. Numeric bounds, badge threshold bands and default code sets are observed values; the destination chooses its own, keeping the ordering of bands. _(comp-001; derived)_

## Non-goals

- No implementation code, schema or table design is specified.
- Attachment upload mechanics, export layout and formats, translated message catalogues and the routed-approval engine are only summarised.
- No working-day calendars or per-project holiday calendars are introduced.
- Exact wording, colours and layout of badges and tiles are not specified.
- Graceful degradation against backends that omit derived figures is not required.

## Test cases

- **tst-001**: Given required-on-site 2027-03-01 and lead time 16 weeks, when the needed-by date is derived, then it is 2026-11-09.  
  Expected: Needed-by is 112 days before the on-site date.
- **tst-002**: Given the previous item with review period 14 days and today 2026-11-22, when the submit-by date is derived, then it is 2026-10-26.  
  Expected: Submit-by is needed-by minus 14 days.
- **tst-003**: Given the same item is under review with no release outcome and today is 2026-11-22, when late days are derived, then 13 and the item is flagged late; given today is 2026-11-09 then 0 and not flagged; given today is 2026-11-08 then 0 and not flagged.  
  Expected: Floored at zero; flag only when greater than zero.
- **tst-004**: Given the same dates, when status is approved, approved as noted or closed, or when a stored release outcome exists while the status is a pursued one, then late days are unknown for each; when status is draft, submitted, under review, revise and resubmit or rejected without a release outcome then a number is returned.  
  Expected: Status scope and release outcome control applicability.
- **tst-005**: Given an item with required-on-site but no lead time, one with lead time but no on-site date, one with neither, and a long-lead item among them awaiting approval, when derived, then needed-by and submit-by are unknown for all and never late; the long-lead awaiting item is counted in the cannot-compute header figure.  
  Expected: Unknown is returned, not zero; header counts it separately.
- **tst-006**: Given an item submitted 2026-11-01 with review period 14 days, status under review, today 2026-11-22, when derived, then review due date is 2026-11-15, overdue days 7, days in review 21; with today 2026-11-10 overdue is 0 and days in review 9.  
  Expected: Overdue only past the due date; days in review counts to today while with the reviewer.
- **tst-007**: Given an item with the reviewer and no review period, when derived, then review due date and overdue days are unknown, days in review is still present, and the header counts it as period-unknown and not overdue.  
  Expected: No guess for a missing contract period.
- **tst-008**: Given an item returned on 2026-11-12 after submission on 2026-11-01, when days in review is derived on any later day, then it is 11; given a return date earlier than the submission date then unknown; given a draft never submitted then unknown; given a returned item with no return date and status approved then unknown.  
  Expected: Days in review follows the stated rule.
- **tst-009**: Given a stored status of approved with no stored outcome, when derived, then the effective outcome is approved, the code is the default code for approved, may-proceed is true and late days are unknown; given a stored outcome of approved as noted with resubmit-for-record true in the latest history entry of the current revision, then the resubmit-for-record flag is true.  
  Expected: Legacy records read correctly.
- **tst-010**: Given a project with a mix of items, when the summary is requested, then total equals all items; awaiting review equals items submitted or under review; overdue plus period-unknown never exceed awaiting; long-lead awaiting approval counts only long-lead items in the pursued set without release outcome; approval-late counts any item flagged late; by-outcome lists four outcomes including zeros with default codes; by-discipline puts items without a discipline under an empty code.  
  Expected: Header counts as specified.
- **tst-011**: Given the list with the approval-late filter on, then only items flagged late are returned and the total reflects only them; with review-overdue on, only overdue ones; with both, only items satisfying both; with a status filter too, the stored filter applies first.  
  Expected: Derived filters applied after stored filters, then paged.
- **tst-012**: Given requests for sort by a derived figure such as days in review, or an unknown field, or a page size above the maximum, then each is rejected as invalid input.  
  Expected: Only stored columns sortable; page size capped.
- **tst-013**: Given lead time -1, one above the maximum, 'abc', review period above the maximum, discipline '3d scan', and country 'tr', when saved, then the first four and the discipline are rejected; 'tr' is stored as 'TR'; 'Fire Stopping' becomes 'fire_stopping' and is accepted; the maximum lead time and maximum review period themselves are accepted.  
  Expected: Bounds and normalisation hold.
- **tst-014**: Given the create form, when long-lead is ticked and lead time is empty, then a required message appears and save is disabled; when 16 is entered the message goes and save is enabled; when long-lead is unticked the lead-time input disappears and its value is cleared.  
  Expected: Form rules for long-lead.
- **tst-015**: Given the create form with type product data and an empty manufacturer, then a non-blocking prompt appears; typing a manufacturer removes it; type shop drawing never shows it.  
  Expected: Material prompt without blocking.
- **tst-016**: Given the edit form for an item with server-derived deadlines, when no input is touched, then needed-by and submit-by dates are shown (emphasised if late); when the required-on-site date, lead time or review period is edited, then they are replaced by a recalculated-on-save note.  
  Expected: Client never computes deadlines.
- **tst-017**: Given an edit that changes only the lead time and one that clears the review period, when saved, then the first sends only the lead time and the second sends an explicit empty value for the review period.  
  Expected: Differential payload with explicit clearing.
- **tst-018**: Given today is fixed, when the due-date badge is shown for: no date, malformed date, status approved, closed, rejected, revise and resubmit, a date more than a week away, a past date while submitted, today's date, a date three days ahead while submitted, and a past date while under review, then it shows nothing for the first six cases and for the date more than a week away; error-level overdue for the past dates; warning-level due-today for today; warning-level due-in-N for three days ahead.  
  Expected: Badge bands and suppression rules.
- **tst-019**: Given today is fixed, when the with-reviewer-age badge is shown for: no submission date, draft, approved, revise and resubmit, malformed date, future submission date, one day, five days, ten days and twenty days with the reviewer, then it shows nothing for the first six; nothing for one day; neutral for five; warning for ten; error with a breach note for twenty; and band boundaries at 3 (neutral), 8 (warning) and 14 (error) hold.  
  Expected: Observed band boundaries hold; the server day count overrides the client calculation when supplied.
- **tst-020**: Given rows whose submission dates are far in the future but whose server figures say 25 days in review, 11 days overdue and 20 days late, when the register renders, then it prints 25, plus 11 and 20 late exactly; a fresher item shows 3 days with no overdue suffix and a tooltip saying inside the review period.  
  Expected: Screen uses server numbers verbatim.
- **tst-021**: Given summary counts of 42 total, 9 awaiting, 2 overdue, 4 period-unknown, 6 long-lead of which 3 await approval, and 1 late, when the strip renders, then each figure appears as stated and activating the late figure requests the list with the late filter, marks it active, and activating again removes the filter.  
  Expected: Strip figures come from the summary, not from rows on screen, and open filtered lists.
- **tst-022**: Given an outcome chip activation, then the list request carries only the project, that outcome and the page size; given a discipline chip, the discipline filter; given the type tab, the type filter and the export follows it, and with several filters on, all reach the export and clearing removes all.  
  Expected: Shortcuts and filter combination behavior.
- **tst-024**: Given a submitted item and a manager recording approved as noted with a custom stamp code and resubmit-for-record, when reviewed, then the item is approved as noted, the stamp code is the custom code, a history entry for the current revision is appended with resubmit-for-record true, and responsibility stays with the reviewer; with no code the default code for that outcome is recorded; revise and resubmit returns responsibility to the original submitter and ignores resubmit-for-record.  
  Expected: Stamp and history behavior.
- **tst-025**: Given a revision-2 item whose revision 1 came back as revise and resubmit, when its detail opens, then it states that revision 2 replaces revision 1 and shows the notes and the current-revision line; given revision 2 with no history entry for revision 1 the validation reports the missing link as a warning.  
  Expected: History display and resubmission-linked rule.
- **tst-026**: Given an editor, a manager and a viewer, when each attempts to review, approve, edit and delete, then review and approve require manager; edit and submit require editor; delete requires manager; a plain edit setting status to approved is forbidden; an item in closed status cannot be edited; deleting approved, approved as noted or closed items conflicts.  
  Expected: Role gates and lifecycle guards.
- **tst-027**: Given a long-lead item with no lead time, a material submittal with no manufacturer, an item stamped approved while with the reviewer, and an item unapproved past its needed-by date, when validation runs, then findings are reported for each with the specified severities and the submit action is not refused.  
  Expected: Advisory findings only.
- **tst-028**: Given a draft item, when submitted twice in a row, then the second call fails; given a revise-and-resubmit item resubmitted, then the revision increases by one, the stamp is cleared, the submission date resets to today and the return date is cleared.  
  Expected: Submit rules and clock reset.

## Open questions (decisions for QC Manager)

- Should lateness also apply to non-long-lead items with both inputs present, or only to items flagged long-lead? One option uses the inputs, the other uses the flag.
- Should an advisory finding be allowed to block submission when a long-lead item has no lead time, or only warn?
- The boundary of the highest severity band of the with-reviewer-age badge is ambiguous between two adjacent day counts; confirm the intended boundary.
- Confirm whether the review-period and lead-time ranges are product rules or only input-error guards.
- Should the 'awaiting review' shortcut order items by longest wait first as an explicit rule?
- Severities and exact definitions of some submission-time gate rules are unspecified and need a product decision.
- Export formats, attachments, routed approval and translation catalogue contents were examined at summary depth only.
- The due-date badge uses a filer-set required date while the register uses on-site minus lead time; decide how to present both without confusing users.
- The insights panel compares the filer's required date to the current instant rather than the UTC date; decide whether to unify with the UTC-day convention used elsewhere.
- Should the destination UI degrade gracefully when a backend omits derived figures, or can it assume they are always present?
