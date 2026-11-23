# 06. Warranties and defects liability

Spec `spec-warranty-register-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A per-project register of post-handover warranty and defects-liability-period entries, each owned by a responsible subcontractor and carrying key dates, with defect notices raised against it while its period runs. A derived register view reports counts by status and type, entries expiring within a horizon or already expired, outstanding and overdue defects, a per-subcontractor health view, an overall health score, a clean flag, and the list of entries clear for final retention release. An optional, opt-in statutory limitation regime can fill the warranty period and end date from the acceptance date, with advisory findings when a recorded period disagrees with the regime. Defects can hold photo evidence. No defect or expiry notification exists in this register. An adjacent financial-guarantees capability with banded expiry notifications is summarised as context only.

## Behaviour

- A warranty entry has: reference (bounded length, unique within the project), title, element description, responsible subcontractor (link and free-text name), work package, warranty type (workmanship, manufacturer, latent defect, extended, other), handover date, warranty start date, warranty months (bounded non-negative range), warranty end date, optional limitation regime, defects-liability end date, status (in liability period, expiring, expired, closed, on hold; default in liability period), retention release date, contract link, document link, sort order and notes. A duplicate reference in the project is a conflict on create and on rename. _(beh-001; observed)_
- A defect notice has: reference (bounded length), description, optional severity (minor, major, critical), raised date, due date, status (open, rectifying, rectified, rejected, closed; default open), rectified date, responsible party, optional links to a punch item and a non-conformance record, optional map coordinates (latitude -90 to 90, longitude -180 to 180) and a photo list. Only open and rectifying defects are outstanding; rectified, rejected and closed are settled. _(beh-002; observed)_
- A defect is overdue when it is outstanding and its due date is strictly before the as-of date. A defect with no due date, a settled defect, or a due date equal to the as-of date is not overdue. _(beh-003; observed)_
- An entry is expiring when it is not closed, has a liability end date, and that date lies within the closed window from the as-of date to the as-of date plus the horizon (both ends inclusive). An entry without an end date is never expiring; an entry whose end date is before the as-of date is expired, not expiring. Horizon is a whole number of days within a bounded range (for example 0 to 3650, default 30); a horizon of zero includes only entries ending on the as-of date. _(beh-004; observed)_
- An entry is expired when it is not closed, has a liability end date, and that date is strictly before the as-of date. A closed entry is never expiring or expired. Expiring and expired are computed from dates at read time; the stored status text is set by users and is not changed by the passage of time. _(beh-005; observed)_
- An entry is ready for final retention release when it has a liability end date on or before the as-of date and has no outstanding defect. No end date means never ready; a future end date means not ready; any open or rectifying defect means not ready regardless of age; an entry that never had a defect is ready as soon as its period ends. This is a readiness signal only and ignores the stored retention release date. _(beh-006; observed)_
- Derived register contents: as-of date, horizon, entry total, counts per status (every known status present, zero-filled; unknown stored statuses are still counted), counts per warranty type (every type plus an unassigned bucket, zero-filled; entries without a type go to unassigned; unknown types still counted so counts sum to the total), total outstanding defects, overall health score, clean flag, the expiring list, the expired list, the overdue defects list, the retention-ready list and the per-subcontractor list. Entry references in lists carry identity, title, status, subcontractor, work package, type, both end dates, outstanding defect count and a retention-ready flag. Overdue defect rows carry the owning entry's reference and title plus the defect's severity, status and due date. Lists keep input order (creation order within sort order). _(beh-007; observed)_
- Overall health score = share of entries that carry no open and no overdue defect, as a percentage with two decimals (half-up); undefined (no value) when the register is empty rather than zero. Expiry is deliberately not part of the score. The clean flag is true when there are no outstanding defects and no unclosed expired entries, and vacuously true for an empty register. _(beh-008; observed)_
- Per-subcontractor health groups entries by trimmed subcontractor name, with null or blank names grouped as unassigned. Named groups are sorted alphabetically and the unassigned group is last. Each group reports entry total, outstanding defects, overdue defects and a health score computed like the overall score for that group (undefined for an empty group). Group totals always sum to the register total. _(beh-009; observed)_
- Retention-release readiness read returns project, as-of date, total entries, the number ready and the list of ready entry references. _(beh-010; observed)_
- Unknown status, type or severity values never raise in the computations; they simply fail to match a bucket or state test, so a stray row cannot corrupt a rollup or make an entry look ready for release. _(beh-011; observed)_
- Warranty list filters: status, subcontractor, work package, warranty type; ordered by sort order then creation time. Defect list filters: entry, status, severity; ordered by creation time. A defect list for a given entry first confirms the entry belongs to the project (else not found). _(beh-012; observed)_
- Limitation regime is opt-in. Entries without a regime are never examined, derived or flagged. The destination keeps a fixed catalogue of regimes; this spec describes only its structure and lookup behavior and deliberately lists no jurisdictions, statute names or period values, which the destination must source from the applicable law. Each catalogue entry has: a short code, jurisdiction name, country code, statute name, statute reference text, statutory period in whole months, a start basis (acceptance of the works), and explanatory notes. Behavior: lookup by code returns the entry; an unknown, empty or absent code is treated as no regime and is silently inert; the codes are exposed in a canonical order; the same catalogue is available on the client so the form can preview the derived date before saving, and both sides must count identically. Entries are fixed constants rather than editable stored data (see open questions). Any auxiliary informational data per country, such as insurance obligations, is display only and nothing enforces it. _(beh-013; observed)_
- Fields and statuses, summarised: a warranty entry carries identity (reference, title, element description), responsibility (subcontractor link and name, work package), classification (type), dates (handover, warranty start, warranty end, liability end, retention release), period length in months, optional regime, status, links (contract, document) and ordering and notes. Warranty statuses: in liability period, expiring, expired, closed, on hold. Defect statuses: open, rectifying, rectified, rejected, closed. Types: workmanship, manufacturer, latent defect, extended, other. Severities: minor, major, critical. _(beh-021; observed)_
- How the defects-liability end date is determined: it is never calculated by the register. It is a contractual date entered by a person and is deliberately excluded from regime derivation because it decides retention release. The only computed dates are the warranty end date and warranty months, which can be derived from a chosen regime and the acceptance date (warranty start date, else handover date). No formula of handover date plus months equals liability end exists; whether the destination wants one is a decision. _(beh-022; observed)_
- When a create or update request itself names a regime, the warranty months and warranty end date are filled from the regime for whichever of the two the same request did not set; a field set in the same request always wins and is never overwritten. The counting start is the warranty start date if recorded, else the handover date; if neither exists nothing is derived. The liability end date is never derived. Clearing a regime changes no dates. Entries that never name a regime behave exactly as without this feature. _(beh-014; observed)_
- Adding months to a start date keeps the same day number in the target month and, when that month is shorter, uses its last day. The result is the last day on which a claim can still be brought. Zero months returns the start date. _(beh-015; observed)_
- Limitation review examines only entries naming a recognised regime and returns: project, total entries, number reviewed, regimes in use (in catalogue order regardless of data order) and findings (rule identifier and name, severity, entry identity, reference and title, message, suggestion, structured details). Findings: (a) recorded months differ from the regime's months, (b) recorded end date differs from the date counted from the acceptance date, stating the number of days and whether it is later or earlier, (c) no acceptance date exists to count from. All are warnings; a recorded period that departs from the statutory default is lawful when the contract agrees it, so findings never block a save and never rewrite data. A project with no regime in use returns zero reviewed and no findings. If the rule engine fails the review degrades to no findings instead of an error. _(beh-016; observed)_
- Defect photos: a photo upload (bounded size, for example 50 MiB) appends an entry with its evidence record to the defect; if the defect has no map position yet and the photo carries a location, the defect is pinned to it; an existing pin is never moved. Removing a photo by position detaches it and returns its entry; a position outside the list is unprocessable. A separate evidence check warns for each defect marked closed that has no photo. _(beh-017; observed)_
- Defect notifications during the liability period: this register records and tracks defect notices (raised date, due date, status, responsible party, overdue computation, per-subcontractor counts) but sends no notification or alert on raising, becoming overdue or on approaching expiry. _(beh-018; observed)_
- Adjacent context only, financial guarantees: types (bid, performance, advance payment, retention, warranty bond, parent company), direction (given or received), statuses (draft, requested, issued, extended, reduced, released, called, expired) with a fixed transition table (released and called are terminal; expired may only be extended). Live statuses are issued, extended and reduced. A security covering the defects period must outlive completion plus the defects months. _(beh-019; observed)_
- Adjacent context only, expiry alerts for guarantees: a small set of alert bands at descending days-to-expiry (illustratively 60, 30 and 14 days; the destination chooses its own); the tightest band entered applies; negative days left means no band. A daily job (also runnable on demand) processes live guarantees with an expiry date: past expiry with auto-extension configured rolls the date forward by the extension months until it is in the future and sets status extended; past expiry without auto-extension becomes expired; otherwise when the band changed from the last alerted band a warning notification goes to the project owner and the creator, the band is remembered, and an expiring event is published. Extending a guarantee resets the remembered band. _(beh-020; observed)_

## Inputs

- Register and readiness reads accept an optional as-of date in year-month-day form (default today in UTC) and, for the register, a horizon in days within a bounded range. _(in-001; observed)_
- Text fields have bounded lengths (titles and names in the low hundreds of characters, descriptions and notes much longer, link identifiers sized for a UUID string). Out-of-vocabulary status, type, severity or regime values are rejected as unprocessable. Numeric limits are ordinary parameters; the destination chooses its own. _(in-002; observed)_

## Outputs

- Health scores are serialised as plain decimal strings, not binary floats, to avoid rounding drift at the interface. _(out-001; observed)_

## States and transitions

- Warranty status nominally runs in liability period, expiring, expired, closed, with on hold as a side state; it is set by users, not by time. Defect status nominally runs open, rectifying, rectified, closed with rejected as a terminal alternative. No transition table is enforced in the register itself (any listed value may be set by update). _(st-001; observed)_

## Timing and ordering

- All expiry, overdue and readiness evaluations use the single as-of date supplied or today's UTC date, so one register read is internally consistent. _(ord-001; observed)_

## Edge cases

- Empty register: totals 0, health score undefined, clean flag true, all lists empty, status and type counts zero-filled. _(edge-001; observed)_
- Boundary dates: a due date equal to the as-of date is not overdue; a liability end equal to the as-of date is not expired, is expiring, and is already eligible for release if nothing is outstanding. _(edge-002; observed)_
- Acceptance on the 31st plus six months ending in a shorter month lands on that month's last day (leap-aware); an acceptance on a leap day plus a whole number of years lands on the 28th when the target year is not a leap year; year rollover works; a missing or invalid start gives no date. _(edge-003; observed)_

## Errors

- Missing or foreign-project warranty or defect yields not found (both cases look the same); duplicate warranty reference yields conflict; photo position out of range yields unprocessable. _(err-001; observed)_

## What it must not do

- Derivation never invents a date from a missing acceptance date, never overwrites a value supplied in the same request, never moves the liability end date and never touches entries without a regime. _(neg-001; observed)_

## Security

- Read-level permission for reads and edit-level for all changes. Every endpoint is scoped to a project in the request and verifies project access first (a missing project and a denied project look the same). Every referenced warranty is re-verified against the same project in the service layer so a defect can never be attached to or listed under another project's entry. _(sec-001; observed)_

## Invariants

- Every percentage is guarded against a zero base and is reported as undefined, never as zero or an error. _(inv-001; observed)_
- A defect's project always equals its entry's project. _(inv-002; observed)_

## Notes

- Behavior-only compatibility: predicates (expiring, expired, overdue, retention-ready), boundary inclusivity, scoring and grouping rules, month arithmetic and the opt-in limitation semantics should match; names, routes and wording need not. Statutory periods must be sourced by the destination from the applicable law and are not provided here. _(comp-001; derived)_

## Non-goals

- Reproducing legal citations, statute text, jurisdiction lists or explanatory notes from any regime catalogue.
- Reproducing origin layout, naming, comments or screen design.
- Enforcing insurance obligations that may be listed beside some regimes (display only).
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: As of 2026-06-15, horizon 30, entries with liability end 2026-06-14, 2026-06-15, 2026-07-15, 2026-07-16, none, and one closed ending 2026-06-20.  
  Expected: Expired: the 06-14 entry. Expiring: 06-15 and 07-15. Not listed: 07-16, none, and the closed entry.
- **ts-002**: As of 2026-06-15, defects: open due 2026-06-14, open due 2026-06-15, rectifying due 2026-06-01, rectified due 2026-05-01, open without due date.  
  Expected: Overdue: the first and the third only; outstanding count is 4 (rectified excluded).
- **ts-003**: Entries: A ends 2026-06-15 with no defects; B ends 2026-06-10 with one rectified and one closed defect; C ends 2026-06-10 with one open defect; D ends 2026-07-01; E has no end date; as of 2026-06-15.  
  Expected: Retention-ready: A and B only.
- **ts-004**: Four entries, one carrying an open defect.  
  Expected: Overall health 75.00; clean flag false.
- **ts-005**: Empty register.  
  Expected: Health undefined, clean true, empty lists, zero-filled counts, per-subcontractor list empty.
- **ts-006**: Entries with subcontractors named Beta with surrounding spaces, Alpha, null and whitespace only, with defects on Alpha only.  
  Expected: Groups in order Alpha, Beta, unassigned (two entries); totals sum to 4; Alpha health below 100 only if its entry carries a defect; empty-name entries land in unassigned.
- **ts-007**: Entry with unknown status text and unknown warranty type.  
  Expected: Counted under those unknown keys; per-type counts still sum to the total; entry never retention-ready purely because of the unknown value.
- **ts-008**: Using an invented test catalogue (not real legal values) with one regime of 48 months and another of 60 months, create an entry naming the 48-month regime with acceptance (handover) 2026-03-01 and no months or end date; and another naming the 60-month regime with an end date typed in the same request.  
  Expected: First: months 48 and end 2030-03-01 filled. Second: months filled, typed end date kept, and the review reports a warning about the mismatch with the number of days difference.
- **ts-009**: Name a regime from the invented test catalogue on an entry that has neither warranty start nor handover date.  
  Expected: Nothing derived; review reports the missing-acceptance warning.
- **ts-010**: Entry without any regime in a project with three such entries; run the review.  
  Expected: Reviewed 0, no regimes in use, no findings.
- **ts-011**: Add months: 2025-08-31 plus 6; 2027-08-31 plus 6; 2028-02-29 plus 60; 2026-12-31 plus 1; 2026-03-01 plus 0; start empty or invalid.  
  Expected: 2026-02-28; 2028-02-29; 2033-02-28; 2027-01-31; 2026-03-01; no date.
- **ts-012**: Clear the regime on an entry through an update.  
  Expected: Existing months and dates stay; the entry is no longer reviewed.
- **ts-013**: Create two entries with the same reference in one project, and the same reference in two projects.  
  Expected: Second in the same project is a conflict; across projects both succeed.
- **ts-014**: Raise a defect against an entry id that belongs to another project; list defects for that entry id.  
  Expected: Not found in both cases; nothing created.
- **ts-015**: Attach a photo with a location to an unpinned defect, then a second photo with a different location; remove position 5 of 2.  
  Expected: First photo pins the defect; second does not move it; removal at a bad position is unprocessable.
- **ts-016**: Defect closed without photo and another closed with a photo; run the evidence check.  
  Expected: One warning for the first only.
- **ts-017**: Adjacent context: with illustrative alert bands of 60, 30 and 14 days, a guarantee expiring in 50 days, then 29 days, then 13 days, running the daily job each time; then extended.  
  Expected: Notifications at the widest, middle and tightest bands respectively, one per band; none repeated on identical runs; extension clears the remembered band.
- **ts-018**: Adjacent context: live guarantee past expiry with auto-extension of 6 months, expiry 14 months ago; another without auto-extension.  
  Expected: First rolls forward in 6-month steps until in the future and is marked extended; second is marked expired.

## Open questions (decisions for QC Manager)

- Decision: the register nominally has expiring and expired statuses but they are set manually while the derived views use dates. Should the destination automate status changes, or keep the date-derived views only?
- Decision: no notification behavior was observed for defects in this register. Should the destination add alerts (a new requirement) for defects becoming overdue and for approaching liability end, perhaps reusing a banded alert pattern?
- Decision: if banded alerts are reused for warranty periods, which band values suit them? The values in the adjacent context are illustrative.
- Decision: the destination sources statutory limitation periods from the applicable law. Should the regime catalogue be fixed in code or be editable data, and who maintains it?
- Decision: expected outcome for an invalid as-of date in a register query (default to today versus error) is not specified.
- Decision: the as-of date defaults to the UTC date; the destination may prefer the project's local date.
- Decision: screen layout, filters and forms are not specified here.
- Decision: the financial guarantees capability is adjacent and may merit its own unit; only its expiry-alert and status behavior is summarised here as context.
