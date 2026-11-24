# 05. Handover / closeout dossier check

Spec `spec-handover-dossier-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A handover dossier is a closeout package assembled for one recipient in one action. First the package is checked against an editable per-package completeness checklist; findings are classed as errors or warnings and can be scoped to the whole project, one area or one asset. Assembly is blocked by errors unless explicitly overridden by a manager. A passing or overridden request builds an archive with an index document, the bound evidence, resolved punch items with photos, commissioning certificates and a machine-readable manifest, files it as a project document, and optionally delivers an expiring share link by webhook, chat connector or e-mail with a full delivery log. Neighbouring behavior covered as context: the package completeness percentage and the automatic (never auto-applied) evidence suggestions for empty checklist items.

## Behaviour

- The dossier checklist is stored per package and defaults to: required evidence categories (as-built drawings, operation and maintenance manuals, warranties, commissioning, punch closure, signed acceptance); punch items must be resolved (on); resolved punch items must have photos (on); commissioning must be complete (on); acceptance must be signed (on); bound evidence must be verified (off); a default share-link lifetime (for example 30 days). Default values are illustrative starting points; the destination chooses its own. _(beh-001; observed)_
- Checklist normalisation: submitted values are merged over stored values over defaults; unknown keys are ignored; switches are coerced to true or false; categories are lower-cased, trimmed, kept only if they look like category keys (start with a letter, then letters, digits or underscore, bounded length), de-duplicated with order kept; share-link lifetime is clamped to a bounded range (for example 1 to 365 days) and an unparseable value is ignored. Updating the checklist changes only supplied fields. _(beh-002; observed)_
- Scope has a kind (project, area, asset) and a value. Anything unusable (unknown kind, project kind, or empty value) falls back to the whole project; the value is trimmed and cut to a bounded length. A project scope includes every record. An area scope includes a record whose area text equals the scope value case-insensitively or begins with the value followed by a path separator (so a floor includes rooms beneath it); records with no area are excluded. An asset scope includes a record when any of its asset references equals the value exactly (case-insensitive): asset reference, plant item identifier, model element identifier, tag or system identifier. _(beh-003; observed)_
- Overall check status is errors when any failed finding has error severity, warnings when findings exist but none is an error, otherwise passed. Each finding carries rule identifier, severity, message, affected element reference and a fix suggestion. Engine failures are never reported as findings. _(beh-004; observed)_
- Rule 1 (error): every required category must carry evidence, otherwise one finding per missing category with a fix suggestion. A category carries evidence when at least one checklist item of that category is bound to a document or external reference, or is a generated artifact the build produces. The commissioning category may also count as present based on commissioning systems in scope; the exact condition is a decision point (see open questions). A required category with no checklist items at all is missing. _(beh-005; observed)_
- Rule 2 (warning, only when the verified-evidence switch is on): for each required category that is present, all its bound evidence must have been verified by a manager, otherwise one finding per category. Missing categories are not double-reported here. _(beh-006; observed)_
- Rule 3 (error, only when the punch-resolved switch is on): every punch item in scope must be resolved, verified or closed; each open item produces one finding naming it with a fix suggestion. _(beh-007; observed)_
- Rule 4 (warning, only when the punch-photo switch is on): every resolved, verified or closed punch item in scope must have at least one photo; each one lacking a photo produces a finding. _(beh-008; observed)_
- Rule 5 (warning, only when the commissioning-complete switch is on): each commissioning system in scope that is not commissioned produces a finding; in addition one aggregate finding states the total number of open critical issues across systems in scope when that number is above zero. _(beh-009; observed)_
- Rule 6 (error, only when the signed-acceptance switch is on): an acceptance-category checklist item must be bound, otherwise a missing-acceptance finding; when bound it must be fully signed. A bound document counts as signed when the best status of the signing sessions in the same project that relate to that document is fully signed (how sessions are matched to a document is a decision point, see open questions). Best-status order: fully signed, partially signed, awaiting signatures, draft, declined, expired. A bound external link (no document) reports status external and never counts as signed. An unsigned finding states the current signing status. _(beh-010; observed)_
- Per-item findings from rules 3, 4 and 5 are capped per rule (for example at 50 items); when more items exist, one extra finding states how many further items were omitted. When a rule has no failing items it yields nothing that affects status. Finding messages and fix suggestions are localized using the caller's locale. The cap is an ordinary parameter; the destination chooses its own value. _(beh-011; observed)_
- The check-only read returns the overall status, the findings, the normalised scope, the number of punch items in scope and how many are open, the number of commissioning systems in scope, whether acceptance is bound and signed, and per-category present and verified flags. Nothing is persisted. _(beh-012; observed)_
- Requesting a dossier first validates every requested delivery target, then runs the check. When status is errors and the incomplete-override flag is not set the request fails with a conflict outcome carrying a message, the status and the findings; no dossier record is created. Otherwise a dossier record is created in queued state with scope, check status, findings, delivery requests, requester and locale, and a background job is submitted; the response is an accepted outcome with the queued dossier. _(beh-013; observed)_
- Assembling an archive collects: bound documents and the generated artifacts of the package; resolved punch items in scope with a bounded number of photos each (for example up to 20), with photo evidence records kept beside the photos; a machine-readable punch register when there are resolved items; a commissioning certificate summary document when commissioning systems are in scope; an index document (title, project, scope label, build time, check status, findings, file list with sizes, punch table); a manifest (format version, kind, identifiers, scope, build time, checks, completeness counts and gaps, slot summaries, punch count, notes); a plain readme; and a size-and-checksum index of every file. Photos that cannot be read are skipped silently. _(beh-014; observed)_
- The commissioning summary inside the archive lists each system in scope with tag and name, type and readiness percent, a verified-style status when commissioned (otherwise its lifecycle label) and commissioning date; its completeness equals commissioned systems over systems in scope (rounded), it is ready only when all are commissioned, and the gap list names a bounded number of non-commissioned systems (for example up to 50). If it cannot be produced a note is added to the manifest and the build continues. _(beh-015; observed)_
- The archive is a ZIP named with the scope slug (non-safe characters replaced, trimmed, bounded length, a fixed fallback word when empty) and a UTC timestamp. It is stored under the project and filed as a project document tagged for closeout and handover dossier. If filing as a document fails the archive remains downloadable and the dossier simply has no document link. On completion the dossier records file name, SHA-256, size, file count (members plus index), build time and status built. _(beh-016; observed)_
- Delivery channels: download, webhook, chat connector, e-mail. Target validation: unknown channel is unprocessable; e-mail requires an address containing an at-sign and of bounded length (for example at most 320 characters); download needs nothing; webhook and connector require a target identifier that is a valid identifier (else unprocessable) and refers to an existing, active target that is either scoped to this project or global and owned by the requester (else not found). _(beh-017; observed)_
- Delivering requires a dossier in built or delivered state with an archive (else conflict). Every attempt creates a delivery log row. Download deliveries are logged as sent immediately. Other channels create an expiring document share link (lifetime from the request or the checklist default, clamped to the bounded range; optional password; requires a known creating user), then send a localized message with the project title, package title, scope and expiry, plus an optional note of bounded length. A webhook receives a structured payload (project, package and dossier identifiers, scope, check status, file name, checksum, size, file count, link, expiry, note); connectors and e-mail send the message with the link (e-mail body is HTML-escaped). Success requires a 2xx code for webhooks or acceptance for others. A failure is recorded on the row with a truncated detail and never raised to the caller; a success marks the dossier delivered. _(beh-018; observed)_
- Consolidated severity table of the six dossier rules. Error (blocks assembly unless overridden): required document category has no evidence; an in-scope punch item is still open; the acceptance certificate is not bound or not fully signed. Warning (never blocks): bound evidence of a required category is unverified (only when that switch is on); a resolved in-scope punch item has no photo; an in-scope commissioning system is not commissioned or critical issues are open. Rules whose switch is off are silent. Two package-level rules also exist (a required item with no evidence is an error; a bound required item not yet verified is a warning; generated artifacts are exempt) and apply to the package check rather than the dossier check. _(beh-026; observed)_
- Gate override recording: an override is the request flag that allows assembly despite errors. It requires manager-level sign-off. It is recorded on the dossier record as a stored flag together with the requester, the locale, the check status at request time and the full list of findings that were overridden; the index document and manifest also print the check status and findings. No separate audit-log entry for the override was observed in the dossier flow; whether one is wanted is a decision point. _(beh-027; observed)_
- Requirement: package completion and the readiness gate are distinct computations and the destination needs an explicit gate-unavailable state. When the gate information cannot be read or is stale, the interface and API must report that state explicitly; it must be distinguishable from a satisfied gate and from zero outstanding work. While the gate is unavailable, items whose delivery depends on live underlying work must not be counted as delivered, and a full completion percentage must not be presented as readiness. Whether completion and gate come from a single read is a decision point (see open questions). The dossier check is a third, separate computation of its own. _(beh-028; derived)_
- Resending repeats a logged delivery against the same archive with a fresh share link and a new log row that references the original; the archive is not rebuilt. Downloading the archive is allowed only when the archive file exists (else conflict) and is itself logged as a delivery. _(beh-019; observed)_
- Usable delivery targets for a project are the active webhook endpoints and active chat connectors that are scoped to the project or global and owned by the requester. _(beh-020; observed)_
- Package completeness (context) = required checklist items that count as delivered over required items, as a whole percent (100 when nothing is required). An item counts as delivered when its evidence is verified, or when it is a generated artifact that the last build produced and whose live underlying work (open punch items, inspections) is complete; generated items never count before the package has been built. Package status moves draft, in progress (some evidence or delivery), ready (all required delivered), and issued is explicit and terminal. Any change to items or evidence marks the earlier build stale and recomputes. _(beh-021; observed)_
- Issuing a package to the client requires manager-level permission, is idempotent for an already issued package, and is refused with a conflict outcome when no required items exist or any required item is outstanding. A bound item is verified or unverified by a manager-level action; verifying an item with no evidence is a conflict; binding replaces any earlier binding, requires a document or an external link (else unprocessable), and a document must belong to the same project (else not found). _(beh-022; observed)_
- Automatic evidence suggestions: considers only checklist items backed by a project document or a manual upload that currently have no evidence, against all documents of the project. For each such item (in checklist order) the best-scoring unused document is proposed if its score reaches a minimum threshold. A document is proposed for at most one item. Score signals, in descending illustrative weight: category match in either direction (strongest), discipline equality, keyword overlap between the item's key words (including a built-in synonym set for common handover items) and the document name words (per shared word, capped), current revision (small bonus unless explicitly not current), published state (small bonus). Illustrative values only: category 0.4, discipline 0.25, keywords 0.12 per word capped at 0.35, current revision 0.05, published 0.1, threshold 0.3; the destination tunes its own weights and threshold. Each suggestion states item, document, confidence (score capped at 1, two decimals) and a short list of reasons. Suggestions bind nothing; a person confirms each, and the evidence is flagged as machine-suggested until verified. _(beh-023; observed)_
- Insights view (frontend) per checklist item: a missing count of 1 only for required items with no evidence (optional empty items are not gaps); delivered 1 when evidence exists; unverified 1 when evidence exists but is not verified (also when status says bound but the evidence record did not load); machine-suggested-unchecked 1 only when the evidence was machine-suggested and is not verified; blank or missing discipline is labelled as not discipline specific; obligation is required or optional; rows follow checklist order, not arrival order; category and status labels use the same labelling as the checklist; empty input yields no rows; no currency measure; every built-in view refers to an existing dataset and field and view identifiers are unique. _(beh-024; observed)_
- Dossier panel behavior (frontend): the assemble action is disabled while the latest check status is errors and lists the findings; a passing check lets the user assemble, sending a request with project scope, no override and no deliveries; a user without sign-off rights who selects an outbound channel sees a notice that a manager is required. _(beh-025; observed)_

## Inputs

- Check read takes a scope kind (project, area or asset; default project) and an optional bounded-length scope value. _(in-001; observed)_
- Dossier request takes scope kind and value, an incomplete-override flag and a list of deliveries (channel, target identifier, recipient, message, optional lifetime in days, optional password). _(in-002; observed)_

## Outputs

- A dossier record exposes status (queued, built, delivered, plus a failure representation), scope, check status and findings, delivery requests, file name, checksum, size, file count, document link, build time, error and its deliveries. Lists are newest first. _(out-001; observed)_

## States and transitions

- Dossier: queued, then built (archive stamped), then delivered once any delivery succeeds; later deliveries from a delivered dossier are still allowed. Delivery attempt: pending, then sent or failed. _(st-001; observed)_
- Package: draft, in progress, ready, issued (see completeness claim); changes after issue reopen the package to in progress. _(st-002; observed)_

## Timing and ordering

- Request order: validate delivery targets, run checks, decide on block, create record, commit, submit background job. Deliveries requested with the dossier run after the archive is built. _(ord-001; observed)_

## Edge cases

- Capabilities that supply punch items, commissioning systems or signing sessions may be absent; the corresponding collections are then empty and the associated rules find nothing to flag (acceptance still reports missing if no acceptance evidence is bound). _(edge-001; observed)_
- A package with zero required items counts as 100 percent complete. _(edge-002; observed)_
- Pure completeness helper: delivered is clamped into 0..required; negative inputs are a caller error; bands are empty at 0, complete at 100, otherwise partial. _(edge-003; observed)_

## Errors

- Outcomes: blocked assembly (conflict with findings); unknown channel, invalid e-mail, missing target, missing user (unprocessable); unusable target or missing dossier, delivery or package (not found); dossier not built or archive missing or not filed (conflict). _(err-001; observed)_

## What it must not do

- Suggestions never bind evidence on their own; a machine-suggested binding is never treated as verified. _(neg-001; observed)_
- A bound but unverified item is never treated as verified in counts; an optional empty item is never a gap. _(neg-002; observed)_

## Security

- Read-level permission for checklist read, check, list, get, download and target listing; edit-level for checklist update and for requesting a dossier; manager-level for deliver, resend, issue and verify. Requesting a dossier with any outbound delivery or with the incomplete-override flag additionally requires manager-level sign-off. Project access is verified on every package, dossier and delivery. _(sec-001; observed)_
- Delivery targets are checked against project or requester ownership so another user's targets cannot be used; documents bound to a checklist item must belong to the same project (cross-project references look like not found). _(sec-002; observed)_

## Invariants

- A dossier whose check status is errors can be built only by a manager who explicitly overrides; the check status at request time is stored with the dossier and printed on its index. _(inv-001; observed)_
- Completeness percent, required count, delivered count and gap list in the manifest come from the same computation as the package view. _(inv-002; inferred)_

## Notes

- Behavior-only compatibility: error versus warning classification, which conditions generate findings, scope-matching rules and completeness arithmetic should be preserved; names, routes, wording, document layout and formats of internal archive members need not match. Numeric caps, ranges and defaults quoted here are ordinary parameters and the suggestion weights and threshold are illustrative; the destination chooses its own values. _(comp-001; derived)_

## Non-goals

- Reproducing origin layout, naming, message texts, document styling or archive member names.
- National handover form templates.
- Standard asset-data spreadsheet and inspection certificate generation internals of the underlying package build beyond what the dossier consumes.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Given default checklist, an empty package with no acceptance evidence and no punch items, when a project-scope check runs.  
  Expected: Status errors; findings include missing categories and a missing-acceptance finding.
- **ts-002**: Given required category warranty has one bound item and the verified-evidence switch is on but the binding is unverified.  
  Expected: Category counts as present (no error) and one warning for unverified evidence; overall status warnings.
- **ts-003**: Given 3 punch items in scope: one open, one closed with a photo, one resolved with none.  
  Expected: One error for the open item and one warning for the photo-less resolved item.
- **ts-004**: Given 60 open punch items in scope and an illustrative per-rule cap of 50.  
  Expected: 50 per-item error findings plus one finding stating 10 more items omitted.
- **ts-005**: Given an area scope of Level 2 and punch items located at a lower-case level 2 room path, at Level 20, and with no area.  
  Expected: Only the first is in scope.
- **ts-006**: Given an asset scope with a plant item identifier and a system whose tag equals it, and another system with a different tag.  
  Expected: Only the matching system is in scope; commissioning rule evaluates only it.
- **ts-007**: Two systems in scope, one commissioned and one not, with 2 open critical issues in total.  
  Expected: One finding for the uncommissioned system and one aggregate finding mentioning 2 critical issues; severity warning.
- **ts-008**: Acceptance item bound to a document whose signing sessions are awaiting signatures and draft; later all signatures complete; separately the item is bound to an external link only.  
  Expected: First: unsigned finding naming status awaiting signatures. After completion: no finding. External link: unsigned finding with status external.
- **ts-009**: Checklist update with categories given as a padded mixed-case warranty key, the same key in lower case, a key starting with a digit, and a mixed-case key containing an underscore; share lifetime 999.  
  Expected: Categories become the lower-case warranty key and the lower-case underscore key in that order (duplicate and digit-leading keys dropped); lifetime is clamped to the maximum of the bounded range; other settings unchanged.
- **ts-010**: Request a dossier while errors exist, without override; then with override by a manager; then with override by an editor.  
  Expected: First conflict with findings and no record; second accepted and queued with override flag stored; third denied for lacking sign-off.
- **ts-011**: Request with an e-mail delivery without an at-sign, a webhook delivery with no target, and a webhook whose target belongs to another project.  
  Expected: Unprocessable, unprocessable, not found; nothing queued.
- **ts-012**: Build for an area scope with resolved punch items having 25 photos on one item, with an illustrative per-item photo cap of 20.  
  Expected: Archive holds at most the cap of photos for that item; manifest punch count matches; archive name contains the scope slug and a timestamp; dossier built with checksum and size.
- **ts-013**: Deliver a built dossier by webhook returning 200, then by webhook returning 500, then by e-mail with the mail service refusing.  
  Expected: Three log rows: sent, failed with status code, failed with detail; dossier delivered after the first; no exception to the caller.
- **ts-014**: Resend the failed webhook delivery.  
  Expected: New log row referencing the old one, new share link, same archive, no rebuild.
- **ts-015**: Deliver a dossier still queued.  
  Expected: Conflict, no log row for a send.
- **ts-016**: Package with 4 required items: 2 verified, 1 bound unverified, 1 empty; also a package with none required.  
  Expected: 50 percent and in progress; second package 100 percent. Issuing the first is refused with a conflict.
- **ts-017**: Empty warranty item in the warranty category; documents: one named as warranty certificates for a given year, category warranty, published; one unrelated drawing; both current.  
  Expected: Warranty document suggested with high confidence and reasons listing category, name keyword and published; unrelated not suggested; no binding is created.
- **ts-018**: Two empty items both best-matched by the same single document.  
  Expected: Document proposed only for the first item in checklist order.
- **ts-019**: Insights for a required empty item, an optional empty item, a bound item, a verified item, a bound item suggested by machine and a verified machine-suggested item.  
  Expected: Missing counts 1,0,0,0,0,0; unverified 0,0,1,0,1,0; machine-suggested-unchecked 1 only for the fifth kind; blank discipline labelled generic; order follows checklist order.
- **ts-020**: Panel with a latest check of errors, then of passed; viewer without sign-off chooses e-mail channel.  
  Expected: Assemble disabled with findings shown; enabled when passed and request carries project scope without override or deliveries; manager-required notice appears.
- **ts-021**: Given a package with generated items whose live gate information cannot be read.  
  Expected: An explicit gate-unavailable state is reported, distinct from a satisfied gate; generated items dependent on live work are not counted as delivered; full completion is not presented as readiness.

## Open questions (decisions for QC Manager)

- Decision: should the destination compute completion and gate in one read, and what exact user-visible treatment applies to the gate-unavailable state described in the requirement?
- Decision: should an override also create a durable audit entry and require a stated reason?
- Decision: percentage rounding mode (half-up versus another mode) for completeness percentages.
- Decision: suggestion weights and threshold are tunable heuristics. Keep them as illustrative values, or specify only relative ordering of signals (category, discipline, keywords, published)?
- Decision: how should a signing session be matched to a bound document? A loose text match on a free-text document reference can match unintended sessions; an exact reference is preferable.
- Decision: the commissioning category may count as present whenever any commissioning system is in scope even if no certificate evidence exists; confirm the intended condition.
- Decision: assembly and delivery run as background jobs; reuse the destination's existing job mechanism if there is one.
- Decision: confirm the failure representation (status and error text) the destination needs for a dossier build that fails.
- Decision: the content rules of the standard asset-data spreadsheet, inspection certificate and punch closure report within the closeout build are out of scope for this unit and may need a separate unit.
- Decision: per-language message catalogues are not specified; finding text per language is left to the destination.
