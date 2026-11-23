# 17. Who may not work today

Spec `spec-work-eligibility-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A per-project register of credentials held by people and firms (licences, certifications, memberships, indemnity cover, registrations, training, regional clearances), plus project-defined requirements saying which credential types bind whom, whether a gap blocks work, and how long a lapse is tolerated. A compliance report joins the two and answers who may not work today and what is about to stop them. A missing, expired-past-grace, suspended or revoked credential blocks; an upcoming expiry never blocks. Status is always derived from dates at read time rather than trusted from storage. The report covers only holders who appear on at least one credential; it does not itself enumerate a site roster, so a person with no credential record at all is not reported. Personnel documents (work authorisation, identity, health certificate and similar) share the status logic but are deliberately kept out of the register and its report. A separate company-document tracker with its own expiry statuses exists alongside and is described only as context.

## Behaviour

- A credential records: holder name (required, bounded length), holder kind person or company (default person), an optional link to a platform user, a credential type, an optional discipline, issuing authority, identifier, jurisdiction, an issue date, an optional valid-until date (absent means it never expires), a reminder lead time in days (non-negative, bounded; illustrative default 30), an optional statutory-notification window in days with a trigger label, an optional manual status, notes, and free metadata. Valid-until may not be earlier than the issue date, on create or change. The destination chooses its own bounds and defaults. _(beh-001; observed)_
- The credential type vocabulary is open-ended in storage but validated at the interface against a built-in neutral list covering: professional licence, certification, statutory membership, professional indemnity, registration, training, accreditation, a few region-specific clearances and tax attestations, a set of personnel-document types (employment contract, work or residence authorisation, identity document, visa, occupational health certificate and similar) and other. The destination defines its own list. _(beh-002; observed)_
- Status derivation, applied on every write and on every read: a credential that is manually suspended or revoked keeps that state; with no valid-until it is active; if today is after valid-until it is expired; if the days remaining up to and including the boundary day are not more than the reminder lead time it is expiring soon; otherwise active. Reads report this derived status together with a signed day count to expiry (negative once expired, zero on the expiry day, absent for perpetual) and a flag that says the stored status has drifted behind the derived one. _(beh-003; observed)_
- Only active, suspended and revoked may be set manually; expiring-soon and expired are always derived. Revoked is terminal: an explicit attempt to move a revoked credential to any other state is refused, and date-based derivation never revives it. Suspended is reversible. A change with no explicit status recomputes the status from the resulting dates. _(beh-004; observed)_
- Listing and filtering by status use the derived status, so a credential that aged into a bucket without being edited still appears under that bucket. Lists are ordered by valid-until ascending with perpetual credentials last. An expiring-soon list returns credentials that are expired or inside their reminder window, ordered by expiry, with a bounded, caller-supplied limit. _(beh-005; observed)_
- A refresh operation writes the derived status back onto records whose stored status drifted, reports how many records were examined and how many were updated, and raises the expiry alert for credentials that lapsed while nobody edited them. Reads are correct without it. _(beh-006; observed)_
- An expiry alert is published only when a credential transitions into expiring-soon or expired (on create, change or refresh), never again while it stays in the same bucket. The alert carries project, credential type, authority, status, valid-until, days to expiry, lead time and previous status, and the holder's name and user link except for personnel documents, whose alerts name nobody. _(beh-007; observed)_
- Verification records that a person checked a credential against its issuing authority: a verification date (default today, never in the future), the verifier, and an optional bounded-length note. Verification can also be retracted, clearing date and verifier. Verification never changes validity: an expired credential that was checked stays expired. _(beh-008; observed)_
- A requirement belongs to a project and names a credential type, an audience (everyone, or a discipline name), a holder kind (person or company, default person), whether a gap blocks work (default yes), a grace period in days (non-negative, bounded; illustrative default 0), a description, and an active flag (default active). Only one requirement may exist per credential type, audience and holder kind within a project; a duplicate, on create or on a change that moves any of the three, is refused as a conflict. Requirement lists exclude inactive ones unless asked and put blocking requirements first, then by type, then by audience. _(beh-009; observed)_
- Compliance report population: holders are the distinct people or firms found on the project's register. Two credentials belong to one holder when they share the same user link; otherwise when they share the same holder kind and the same holder name compared case-insensitively. A holder's discipline is the first non-empty discipline found among their credentials. _(beh-010; observed)_
- A requirement binds a holder when the holder kind matches and the audience is everyone or equals the holder's discipline compared case-insensitively; a holder with no discipline is not bound by a discipline-scoped requirement. _(beh-011; observed)_
- Per bound requirement a holder is assessed against their credentials of that type. With none, the gap reason is missing. Otherwise the best credential is chosen: best derived status first (active, then expiring soon, then expired, suspended, revoked), and among equals the one with the most days left, with a perpetual credential beating any dated one. If the best is active the requirement is satisfied (and counted as unverified when that credential was never verified). Otherwise a gap is reported with the reason expired, suspended, revoked or expiring soon, the credential concerned, its valid-until date and days to expiry. _(beh-012; observed)_
- A lapse inside the requirement's grace period is reportable but does not stop work: an expired gap is within grace when the number of days since expiry does not exceed the grace days. Grace applies only to expired credentials, not to missing, suspended or revoked ones (the scope of grace is an open question). _(beh-013; observed)_
- A holder is blocked, meaning may not work today, when at least one gap is on a blocking requirement, has the reason missing, expired, suspended or revoked, and is not within grace. An upcoming expiry never blocks, and a gap on a non-blocking requirement is only a note. The reasoning is that a credential valid until Friday is valid today. _(beh-014; observed)_
- Report output: the as-of date, the count of active requirements, the count of holders assessed, the count of blocked holders, each holder's row (name, kind, user link, discipline, blocked flag, gaps, satisfied count, unverified count), and the list of requirements that bound nobody. Rows are ordered blocked first, then by name case-insensitively. The holder count tells the reader how many people the report could assess. _(beh-015; observed)_
- Personnel documents are never part of the register. Their types are blocked from creation or conversion through the register, are hidden from listing, expiring-soon, summary, compliance, single read, update, delete and verification (single access answers the same not-found as an unknown identifier), and a requirement cannot name them because the report would list every holder as missing them. A personnel document holds its validity window only: no identifier, notes or metadata. They are created and read through a separate access-controlled personnel area that checks the caller's relationship to the person. The status refresh and expiry alert still cover them. _(beh-016; observed)_
- A summary reports, on derived status: total, counts per status, expiring within an illustrative 30-day horizon (valid-until between today and that horizon, excluding suspended and revoked), expired, never verified, perpetual, and records whose stored status drifted. _(beh-017; observed)_
- A validation run applies seven rules over the project and returns an overall status, a score (absent when nothing was checked, so an empty register scores nothing rather than perfectly), error and warning counts, and findings, each with rule, severity, message, a stable reason code and context. Rules: blocking gap (error: one result per blocking gap that stops work); statutory notification overdue (error: issue date plus notification window is before today and no notification date is recorded in the credential's free metadata); expiring window (warning: not suspended or revoked, not yet expired, and inside its own reminder window); no expiry recorded (warning: only for licence-like families, namely professional licence, certification, statutory membership, professional indemnity and registration); unverified blocking (warning: a holder meets requirements with credentials nobody verified); duplicate identifier (warning: same authority and identifier, compared case-insensitively, on two or more records); unmatched requirement (warning: a requirement binds nobody, silent for an empty register). A clean rule yields one passing row. _(beh-018; observed)_
- The compliance view shows each holder with a clear indicator when blocked, shows a gap inside grace as not stopping work with its remaining grace, shows an expiring-soon gap as a warning, lists unmatched requirements so a mistyped audience is noticed, and distinguishes a failed load from an empty result. _(beh-019; observed)_
- Suspended, revoked and expired credentials are shown with the same alarming tone, since all three mean the credential cannot be relied on today; the label tells them apart. Expiring soon is shown as a warning and active as fine. _(beh-020; observed)_
- The register's insight panel counts credentials by type, authority and status, and puts expiry against holder; lapse length is counted only for credentials already past their date, so upcoming expiries never offset real lapses. No monetary value is attached to a credential. _(beh-021; observed)_
- The screen explains that a register without requirements cannot report anything missing: it is only a record store until requirements are stated. _(beh-022; observed)_

## Inputs

- Credential input has bounded text lengths for discipline, authority, identifier, jurisdiction, notification trigger and notes; the destination chooses them. On change every field is optional. _(in-001; observed)_
- Requirement input has a required bounded-length audience and a bounded description. _(in-002; observed)_

## Outputs

- Credential responses always carry the derived status, the day count to expiry and the drift flag, whatever status is stored. _(out-001; observed)_
- Vocabulary responses give credential types, holder kinds and statuses with labels in the requested language, falling back to a default language. _(out-002; observed)_

## States and transitions

- Credential status: active -> expiring soon -> expired are date-driven and automatic; active or any date-driven state <-> suspended is manual and reversible; any state -> revoked is manual and terminal. _(st-001; observed)_
- Company documents (a neighbouring tracker, context only) derive status from effective date and expiry: past expiry is expired; before the effective date is not yet effective (tested before the reminder window so a future policy is not called expiring); inside the reminder window is expiring soon; otherwise active; cancelled and void are terminal manual states. Alerts fire on entry to expiring soon or expired. _(st-002; observed)_

## Timing and ordering

- The current date used for every derivation is a single reference calendar date taken at the moment of the request (not a site-local date in the origin). Which time zone the destination uses is an open question. _(ord-001; observed)_
- Report rows: blocked holders first then by name case-insensitively; requirement lists: blocking first; credential lists: soonest expiry first, perpetual last. _(ord-002; observed)_

## Edge cases

- On the expiry day a credential is expiring soon (or active with zero lead time), not expired; the day after it is expired. _(edge-001; derived)_
- A reminder lead time of zero still treats the expiry day itself as expiring soon; a negative effective lead is treated as zero. _(edge-002; derived)_
- A holder who has only some credential types is measured against every requirement that binds them, so the types they lack appear as missing gaps; a firm appears only against requirements for companies. _(edge-003; observed)_
- Two holders typed with different spelling or case of one name and no user link are one holder; two typed names without links in different holder kinds are different holders. _(edge-004; observed)_
- A requirement for a discipline spelled differently from any recorded discipline binds nobody and is surfaced as unmatched rather than counted as met. _(edge-005; observed)_
- A holder with several credentials of one type is judged on the best one, so an old expired one beside a valid one does not block. _(edge-006; observed)_

## Errors

- Unknown credential, or one on a project the caller cannot access, answers one identical not-found; unknown or inaccessible requirement likewise. _(err-001; observed)_
- Refusals: personnel-document type through the register; identifier, notes or metadata on a personnel document; valid-until before issue date; explicit move out of revoked; verification date in the future; duplicate requirement scope (conflict); requirement for a personnel-document type. _(err-002; observed)_

## What it must not do

- An upcoming expiry never blocks work and the report never blocks on a non-blocking requirement. _(neg-001; observed)_
- Verification does not alter validity; reading never writes status back. _(neg-002; observed)_
- The report cannot name somebody it was never told about. A person with no credential record, such as a new starter who brought nothing, does not appear and is not reported as missing anything. _(neg-003; observed)_
- Nothing in this area refuses work elsewhere (site entry, time capture, delivery access); it only reports. _(neg-004; inferred)_

## Security

- Permission tiers: reading for viewers, creating and changing credentials, requirements and verifications and running refresh at editor level, deleting at manager level. Every operation verifies project access; cross-project identifiers cannot be used to probe existence. _(sec-001; observed)_
- Personnel documents are personal data. They are separated from the register by design, carry no identifier or free text, expire-alert without naming the person, and are accessible only through a personnel area that checks the relationship to the person and audits reads. _(sec-002; observed)_
- Change operations record who changed a non-personnel credential or any requirement and when. _(sec-003; observed)_

## Invariants

- The status shown anywhere is the one derived from dates on that day; a response never pairs an active status with a negative day count. _(inv-001; observed)_
- Filtering by status and labelling by status use the same rule, so a filter and a label never disagree. _(inv-002; observed)_
- Blocked holders equal exactly those with at least one blocking, non-grace gap of missing, expired, suspended or revoked reason. _(inv-003; observed)_
- At most one requirement exists per project, credential type, audience and holder kind. _(inv-004; observed)_

## Notes

- The register is jurisdiction-neutral: country-specific obligations, such as notify an authority within a number of days, are data on the record, never logic. Statutory or regulatory periods must not be hard-coded; the destination sources them from the applicable law. Only behavior is carried over; the destination uses its own names, layout, bounds and defaults. _(cmp-001; observed)_

## Non-goals

- No implementation code, schema, route or identifier is carried across.
- Skills or competencies other than credentials are not modelled in this area and are not invented here.
- Personnel files, site access control and crew time capture are other capabilities and are not specified here.
- Exact screen layout, colors and wording are not requirements.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Given a credential valid until 2027-01-31 with an illustrative 30-day lead, evaluate its status on 2026-11-01, on 2026-12-31, on 2027-01-01, on 2027-01-31 and on 2027-02-01.  
  Expected: Active on 2026-11-01 (91 days left); active on 2026-12-31 (31 days left, outside the lead time); expiring soon on 2027-01-01 (exactly 30 days left, boundary inclusive); expiring soon on 2027-01-31 (zero days left); expired on 2027-02-01.
- **ts-002**: Given a credential with no valid-until, and one manually suspended with a future date, and one revoked.  
  Expected: Active, suspended, revoked, regardless of dates; the revoked one cannot be changed to active, the suspended one can.
- **ts-003**: Given a stored status of active on a credential whose date passed last month, list the project's credentials filtered by expired and read the single credential.  
  Expected: It appears in the expired filter and is returned as expired with a negative day count and the drift flag set; a refresh updates the stored value, reports one updated, and raises one alert.
- **ts-004**: Given a credential that moves from active into expiring soon through a change, then is changed again without leaving that bucket.  
  Expected: One alert is published on entry; none on the second change.
- **ts-005**: Given a blocking requirement for a safety certification binding everyone, and two people: one with no certification, one with an expired one beyond grace.  
  Expected: Both are blocked with reasons missing and expired respectively; the blocked count is two; both lead the list.
- **ts-006**: Given the same requirement with an illustrative grace period of 14 days and a certification expired 10 days ago, then 20 days ago.  
  Expected: At 10 days the holder shows a gap within grace and is not blocked; at 20 days the holder is blocked.
- **ts-007**: Given a holder whose only certification expires in 5 days with a 30-day lead.  
  Expected: An expiring-soon gap is reported; the holder is not blocked.
- **ts-008**: Given a non-blocking requirement and a holder lacking that credential.  
  Expected: A missing gap is listed but the holder is not blocked.
- **ts-009**: Given a holder with an expired and a valid credential of the same required type, and another holder whose perpetual licence sits beside a dated one.  
  Expected: The valid one satisfies the requirement and nobody is blocked; the perpetual one is chosen as best.
- **ts-010**: Given requirements scoped to the audience welding and everyone, and holders with discipline Welding, with no discipline, and with discipline Pipefitting.  
  Expected: The welding requirement binds only the first holder (case-insensitive match); the all-audience one binds all; a requirement for audience welders binds nobody and appears as unmatched.
- **ts-011**: Given one person recorded twice as typed names that differ only by case, and another recorded once with a user link and once without a link.  
  Expected: The first is one holder; the linked and unlinked records are two holders.
- **ts-012**: Given a person who is on site but has no credential record at all.  
  Expected: The person does not appear in the report and no gap is raised for them.
- **ts-013**: Attempt to create through the register a work authorisation, then a requirement for a work authorisation.  
  Expected: Both are refused with a message pointing to the personnel area; neither is stored; a personnel-document read through the register answers not found.
- **ts-014**: Create two requirements for the same type, audience and holder kind; then change one into a duplicate.  
  Expected: The second create and the colliding change are refused as conflict.
- **ts-015**: Verify a credential with tomorrow's date, then with today's date and a note, then retract.  
  Expected: Future date refused; today stored with verifier and note; retraction clears date and verifier; status unchanged throughout.
- **ts-016**: Run validation on a project with a blocked holder, a credential issued 40 days ago with a user-entered 30-day notification window and no recorded notification, a licence without an expiry date, and two records sharing an authority and identifier.  
  Expected: Findings: one blocking-gap error, one notification-overdue error, one no-expiry warning, one duplicate-identifier warning; other rules pass. An empty register scores nothing.
- **ts-017**: Given an unknown credential id and an id belonging to a project the caller cannot access.  
  Expected: Both answer the identical not-found message.
- **ts-018**: Given a viewer, an editor and a manager attempting to read, create and delete credentials.  
  Expected: Viewer reads only; editor reads and writes; only the manager deletes.
- **ts-019**: Load the compliance view with a failing request, then with an empty register and no requirements, then with blocked holders.  
  Expected: Failure shows a recovery state, not an empty state; empty register explains that requirements are needed; blocked holders show a blocked indicator and a headline count, and the blocked-only filter lists only them.
- **ts-020**: Given a company document with a start date in the future and an expiry two weeks after it, evaluated today.  
  Expected: It is not yet effective, not expiring soon; once past expiry it is expired; cancelled stays cancelled.

## Open questions (decisions for QC Manager)

- The report assesses only holders who already appear on a credential. A person with no credential record (the most likely case of a missing document) is invisible. Decide whether the destination should assess a project roster or staffing list as the population, and where that roster comes from.
- The assigned area reports who may not work; no refusal at site access, time capture, delivery access or task assignment was found. Decide whether the destination should also enforce, warn or merely report at those touchpoints, and which module owns that.
- Competencies or skills (as distinct from credentials with dates) are not modelled in this area; the gap description mentions competencies. Decide whether competencies are credentials of a training type or a separate concept.
- Personnel documents are excluded from the register and report and are served by a separate personnel area that was not analysed. Decide how the destination should include them in an overall may-work answer without leaking personal data, and obtain the behavior of that area as a separate unit.
- Date derivations use a single reference calendar date rather than the site's local date; near midnight a credential can change state at a different moment than local staff expect. Decide whether the destination should use the project's time zone.
- Grace applies only to expired credentials, not to suspended, revoked or missing. Confirm whether that scope is intended.
- The stored status is only converged when a refresh is run or a record is written; no scheduler for the refresh was seen. Confirm whether the destination should schedule it.
- Expiry alert recipients and delivery channel are decided by subscribers outside this area and were not analysed.
- The company-document tracker (insurance, bonds, permits with coverage amounts, attachments) was only skimmed for its status derivation; it is not a worker-eligibility feature and is context only.
- A holder grouped by name only (no user link) can merge two different people with the same name. Confirm whether the destination should require a link or identifier to merge.
