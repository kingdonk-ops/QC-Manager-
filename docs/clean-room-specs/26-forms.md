# 26. Forms library and live preview

Spec `spec-forms-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A library of reusable form and checklist templates built from an ordered list of typed fields, plus per-project filled copies. Authors compose a template in an editor that shows a live, interactive preview of the form as a filler would see it (branching and computed values react as the preview is exercised). Saving a template runs integrity checks and is rejected with a list of located problems if any fail. Starting a fill freezes a copy of the template onto the new draft submission; drafts are saved progressively; completion computes derived fields, enforces required and well-formed answers (honouring show-when and require-when rules), rolls checklist answers into a single pass/fail/n-a result, and makes the record read-only. A completed record can be exported as a plain document and, for some categories, can raise a quality inspection. Behavior is described for re-implementation in a different stack; no origin structure is to be mirrored.

## Behaviour

- There are thirteen field types: section heading (layout only, never answered), short text, long text, number (optional unit), single choice, multi choice, single checkbox acknowledgement, pass/fail/not-applicable, rating, photo evidence (one or more), signature (name and optional image data, plus a timestamp once confirmed), date, and formula (computed, never typed). Template categories are a closed set of six: safety, quality, handover, inspection, commissioning, custom (default custom). Template status is one of draft, published, archived (default published on creation). _(beh-001; observed)_
- Before a template is validated or stored its field list is normalised into a canonical copy (input never mutated). A blank key is derived from the label by lower-casing and collapsing non-alphanumeric runs to single underscores; if that is empty a positional key based on the 1-based field position is used; duplicates get a numeric suffix starting at 2. Explicit keys are only trimmed. 'Required' is coerced to boolean and forced off for section headings. Choice options are trimmed, blanks dropped, duplicates removed. Rating scale defaults to 5. Blank help text becomes absent. Number unit is kept only on number fields. Placeholder, default value, number minimum and maximum, text minimum length and text pattern are kept only on field types where they apply and never on sections or formula fields; a checkbox default is coerced to boolean from common truthy words and a multi-choice default is a list of non-blank strings. Show-when and require-when rules are carried through after cleaning. _(beh-002; observed)_
- Template integrity rules (all reported together, each with the index of the offending field, its key when known, and a stable machine code plus a plain-language message): the template needs at least one field and no more than a bounded maximum; at least one field must be fillable (a template made only of section headings and/or formula fields is rejected); every field needs a known type, a non-blank label and a non-blank key; keys must be unique; a choice field needs at least two distinct options; a rating scale must lie within a small bounded range; a number's minimum may not exceed its maximum; a text minimum length may not be negative; a text pattern must be a valid regular expression; a choice default must be one of the options (single value or every picked value). _(beh-003; observed)_
- Show-when and require-when rules are optional per field. A rule is either one comparison (referenced field key, operator, comparison value) or a group requiring all, or any, of nested rules, with a bounded nesting depth. Operators are: equals, not equals, is one of, is not one of, greater than, less than, greater-or-equal, less-or-equal, is empty, is not empty. A require-when rule can only switch requirement on in addition to a static required flag; it never switches it off. Static checks at save time reject: an unknown operator, a malformed structure, a reference to a field not in the template, a rule that references its own field, nesting beyond the cap, and an 'is one of'/'is not one of' whose value is not a list. _(beh-004; observed)_
- Run-time rule evaluation produces, for every keyed field including section headings, a visible flag and a required flag. A field without a show-when rule is visible. A hidden field is never required and contributes a blank answer to the rules of other fields (so a whole branch collapses). A visible field is required if its static flag is set or its require-when rule holds. Evaluation never fails: an unknown operator on a show-when rule leaves the field visible, on a require-when rule leaves it not required; a rule referencing a missing field is false; a malformed rule is false; a reference cycle is broken so evaluation terminates. _(beh-005; observed)_
- Comparison semantics are type-tolerant. Equality: null equals only null; if either side is boolean, both are interpreted as truth values (common affirmative words are true; common negative words and empty are false; any other text is true); if both parse as numbers (comma decimal accepted) they compare numerically; if either is a list the lists compare as order-insensitive sets of normalised tokens (numeric tokens vs trimmed text tokens, blanks ignored); otherwise trimmed strings compare. 'Is one of' is true when the answer (scalar or list) shares at least one normalised token with the candidate list; an empty candidate list is false; a null answer is false. Ordering operators are false unless both sides parse as numbers. 'Is empty' follows the same emptiness definition as answer completeness. _(beh-006; observed)_
- Rule cleaning on save keeps only recognised structure: group lists (empty or junk sub-rules dropped), referenced key (trimmed, bounded length), operator, and comparison value (booleans and numbers kept; text trimmed and length-bounded; lists flattened to scalars only and count-bounded; objects dropped). A rule that cleans to nothing is treated as no rule. _(beh-007; observed)_
- Formula fields are derived from other fields on the same form via a restricted arithmetic expression (bounded length, tolerant of a leading equals sign). Allowed grammar: numeric literals, references to other fields by key, unary plus/minus, binary add/subtract/multiply/divide, parentheses, and exactly three functions: rounding (one or two arguments; the optional second is a non-negative digit count, rounding half away from zero), minimum and maximum (at least one argument). Anything else (powers, remainder, comparisons, boolean logic, property access, other function names, non-numeric literals, non-finite literals, excessive nesting) is rejected. Arithmetic is exact decimal arithmetic, never binary floating point. No general-purpose code evaluation may be used. _(beh-008; observed)_
- Save-time formula checks: a formula field must have a formula; it must parse in the restricted grammar; every field it references must exist in the template; it must not reference itself; formula fields must not form a dependency loop (every field participating in a loop is reported). A formula reading an ordinary number field never counts as a loop. _(beh-009; observed)_
- Run-time formula computation resolves formula fields in dependency order so a formula can read another formula's result, folds results back into the answer set, and returns plain numbers (whole results as integers, others as decimals). A blank or non-numeric operand is treated as zero by default so running totals work on a partly filled form. A formula that cannot be evaluated (division by zero, unresolved reference cycle, malformed expression) yields an empty value for that field and never raises. Numeric operands may be numbers, numeric strings (comma decimal accepted), or earlier formula results; booleans are not numeric. _(beh-010; observed)_
- Starting a submission requires a project and a template. The template's field list, name, category and version are frozen onto the new submission, which starts in draft with optional title, location, initial answers and free-form metadata, and receives a per-project reference made of a short fixed prefix and a zero-padded sequence number. The next sequence number is one more than the highest existing suffix in that project (so deleting never causes reuse, unparsable existing references are ignored, the first is 001); a uniqueness collision from concurrent creation is retried a small bounded number of times with a freshly read maximum, then fails. _(beh-011; observed)_
- Saving draft progress merges answers key by key into the stored answers (supplied keys overwrite; absent keys are untouched; nothing is deleted by omission), merges free-form metadata, and replaces title/location when supplied. A request that changes nothing returns the record unchanged. _(beh-012; observed)_
- Completing a submission: take stored answers, overlay any answers supplied with the request, compute all formula fields, then validate against the frozen field list. Validation honours show-when/require-when state: hidden fields are skipped entirely (not required, value ignored even if present), layout and formula fields are never required or checked, and a field switched on by a require-when rule is enforced like a statically required one. Every visible required field must have a non-empty answer, and every non-empty provided answer must be well-formed for its type. If any issue exists the request fails with a list of located issues and nothing changes; otherwise answers (including computed values) are stored, status becomes completed, a completion timestamp (UTC) and the completing user are recorded, and the rolled-up result is stored. _(beh-013; observed)_
- Emptiness by type for completeness: null is empty; checkbox is empty unless exactly true (so a required checkbox forces a tick); text, pass/fail, date and single choice are empty when blank after trimming; multi choice is empty without at least one non-blank item; photo is empty for a list with no non-blank item or a blank single reference; signature is present if it has a non-blank signer name or non-blank image data; number and rating are empty when null or a blank string. _(beh-014; observed)_
- Well-formedness of a provided answer: single choice must be one of the options (compared trimmed); multi choice must have every non-blank item among the options; pass/fail must be pass, fail or n/a (case-insensitive); number must parse (comma decimal accepted, booleans rejected) and respect optional minimum and maximum; text must meet optional minimum length measured on trimmed text and, if a pattern is configured, the entire answer must match it (an invalid stored pattern never blocks completion); rating must be a whole number from 1 to the field's scale. Checkbox, date, photo and signature have no consistency check beyond non-emptiness. _(beh-015; observed)_
- Result roll-up on completion looks only at pass/fail/n-a fields: any fail makes the whole result fail; otherwise any pass makes it pass; otherwise any n-a makes it n/a; a form with no pass/fail field, or with such fields all unanswered, has no result. _(beh-016; observed)_
- Editing a template: only supplied attributes change; supplying a field list re-normalises and re-validates it, stores it and increments the template version by one; metadata is merged; tags are cleaned (trimmed, length-bounded, case-insensitive de-duplication, count-bounded). Existing submissions are unaffected because each holds its own frozen copy. Supplying an empty or null field list is rejected as a template with no fields. The editing client sends only what changed (compared by content with the template as originally loaded), so an edit that only renames cannot overwrite fields a colleague added in the meantime. _(beh-017; observed)_
- Duplicating a template creates a new copy (keeping the source's project scope) in draft status at version 1, always an ordinary editable template, with the name suffixed with a copy marker (length-bounded), same description, category, fields and tags, and metadata noting the source template. Deleting a template removes it from the library; submissions already created from it keep working from their frozen copy with the template link cleared. _(beh-018; observed)_
- Library listing: for a given project returns that project's templates plus organisation-wide ones; without a project returns only organisation-wide ones. Optional filters by category, status and text. Ordered by category then name. Paged with a bounded default and maximum page size. Each row carries a count of fillable (non-section) fields. A categories listing always returns all six categories, each with a human label and a count of templates visible in the same scope. _(beh-019; observed)_
- Submission listing requires a project and can filter by status, category and source template; newest first; paged with a bounded default and maximum page size. Summary rows omit the answer payload and frozen field list. _(beh-020; observed)_
- Document export of any submission (draft or completed) is a text-oriented document: template name; reference and status; title and location when present; uppercase result when present; completion time when present; then each frozen field in order, section headings as separated headings, others as 'label: answer'. Answer rendering: empty shown as a dash; checkbox as yes/no; multi choice joined by commas; pass/fail uppercased; signature as 'signed' plus name when known; photos as a count; others as plain text. The file name is the reference with spaces replaced by underscores and a document extension. _(beh-021; observed)_
- Raising a quality inspection from a form: only a completed submission qualifies. If an inspection is already linked the existing link is returned with created=false and nothing new is made (idempotent). Otherwise an inspection is created in the same project with a title of template name plus reference (length-bounded), a description noting the originating form, the form location, one checklist entry per pass/fail field (question = field label, response = the lower-cased answer or none, critical = the field was statically required), inspection type = handover when the form category is handover else general, status completed when the form has a result else scheduled, result copied only when pass or fail, and origin metadata. The submission is then linked back to the inspection. If the destination has no inspection capability the action is unavailable and fails with a not-implemented style error. The filler offers the action only for inspection, quality and handover categories and only when not already linked. _(beh-022; observed)_

## Inputs

- Template create/edit input: name (bounded length, at least 1 character), optional description (bounded), category, status, ordered field definitions, tags, free-form metadata, optional project (omitted means organisation-wide). Per-field inputs have bounded lengths (key, label, help text, unit, placeholder, pattern, formula); rating scale is within a small bounded range; minimum length is non-negative. Field type must be one of the thirteen and category one of the six, otherwise request validation fails before integrity checks. _(in-001; observed)_
- Submission create input: project, template, optional title, location, initial answers keyed by field key, free-form metadata (title and location length-bounded). Draft save input: any of title, location, answers (merged), metadata (merged). Complete input: optional additional answers overlaid before validation. _(in-002; observed)_
- Answer value shapes: text and date as strings; number as number or numeric string (comma decimal accepted); single choice as one option string; multi choice as list of option strings; checkbox as boolean; pass/fail as one of pass, fail, na; rating as whole number; photo as list of image references; signature as an object with name, optional image data and, after confirmation, a signed-at timestamp. _(in-003; observed)_
- Library list inputs: optional project, category, status, text query, offset and limit. Submission list inputs: required project, optional status, category, template, offset, limit. _(in-004; observed)_

## Outputs

- A template is returned with identity, optional project, name, description, category, status, version, full ordered field definitions, tags, an indicator of whether it is a shipped starter, creator, metadata and timestamps. A submission is returned with identity, project, source template reference, reference number, template name/category/version, the frozen field list, title, location, answers, status, result, completion time, completing user, linked inspection reference, creator, metadata and timestamps. _(out-001; observed)_
- Validation failures return a validation-failure response carrying a general message and a list of issues, each with the field index (negative when the problem concerns the whole template), the field key when known, a stable machine code and a plain-language message. Clients branch on the code and may translate; the first issue message is surfaced to the user. _(out-002; observed)_
- Inspection raising returns the inspection identity, its number (when newly created), the submission identity and a created flag. _(out-003; observed)_

## States and transitions

- Submission lifecycle has two states: draft and completed. Draft to completed only through a successful completion. Completed is terminal: further edits and further completion attempts are refused with a client error. Deletion is permitted in either state. _(st-001; observed)_
- Template version starts at 1 and increases by one on every edit that supplies a field list; metadata-only or rename-only edits do not change the version. Template status (draft, published, archived) is a descriptive attribute; whether it gates use is a destination decision (see open questions). _(st-002; observed)_
- Link to inspection: a completed submission goes from unlinked to linked once an inspection is raised; repeated requests keep the same link. _(st-003; observed)_

## Timing and ordering

- On completion, formulas are computed first, then validation runs on the computed answer set, then result and storage. Formula fields are evaluated dependencies-first; fields that are in an unresolved loop are evaluated last and come out empty. _(ord-001; observed)_
- In the filler, 'complete' first persists the latest title, location and answers as a draft save and then runs the completion, so a last-moment edit is not lost. The client pre-checks required fields (visible and required only) and, if any are missing, shows a count and highlights them without calling the server. _(ord-002; observed)_
- Field order in a template is the display order, the export order and the fill order; issue lists are returned in field order followed by whole-template, rule and formula issues. _(ord-003; derived)_
- In the editor and preview, keys are derived from labels exactly as on save while editing, so rules and formulas that reference a not-yet-saved field resolve in the live preview; preview recomputes on every change. _(ord-004; observed)_

## Edge cases

- A value left over from a branch that is now hidden never blocks completion and is not consistency-checked, but it is retained in the stored answers. _(edge-001; derived)_
- A required checkbox that is unticked counts as unanswered; a signature with only a name counts as signed for completeness; a required photo field needs at least one non-blank reference. _(edge-002; observed)_
- Formula with a blank operand yields zero-based results (for example a product with one operand blank gives zero); division by zero yields an empty computed value instead of an error; the stored form therefore may carry an empty value for such a field and completion still succeeds. _(edge-003; observed)_
- A rating answer given as a numeric value with no fractional part (for example 3.0) is accepted as whole; 2.5, 0, or a value above the scale are rejected. _(edge-004; derived)_
- A template of only sections plus formulas is invalid; a template at exactly the maximum field count is valid and one more is not. _(edge-005; derived)_
- Defaults prefill blank fields when a draft is opened in the filler or when the preview starts; they never overwrite an existing non-empty answer, are not applied to sections or formula fields, and are not applied when viewing a completed submission. _(edge-007; observed)_

## Errors

- Template create/edit with any integrity issue: validation-failure response with the issue list; nothing stored. _(err-001; observed)_
- Missing template or submission identity: not-found error. Starting a submission from a project-scoped template that belongs to a different project is reported as not found. _(err-002; observed)_
- Editing or completing an already completed submission: client error with a message that it can no longer be edited or is already completed. _(err-003; observed)_
- Completion with missing required answers or malformed answers: validation-failure response listing every issue; the filler shows the first message, highlights the offending fields and keeps the record in draft. _(err-004; observed)_
- Raising an inspection from a non-completed submission: client error; when the destination lacks an inspection capability: not-implemented style error. _(err-005; observed)_
- Unable to allocate a unique submission reference after the bounded retries: internal failure. _(err-006; observed)_

## What it must not do

- Formula fields are never user-entered, never required, never value-checked on completion, and their stored value is always the server's recomputation, not any client-supplied value. _(neg-001; observed)_
- Editing or deleting a template never alters, invalidates or blocks existing submissions. Deleting a template is not refused because submissions exist. _(neg-002; observed)_
- A malformed rule or formula in an old stored template never crashes completion: rules degrade to show/not-required, formulas to empty. _(neg-003; observed)_
- Draft save does not remove answer keys that are omitted from the request. _(neg-004; observed)_

## Security

- Role tiers: read (library, submissions, categories, export) needs viewer; creating templates, duplicating templates, starting submissions, editing templates, saving drafts, completing and raising inspections need editor; deleting templates and submissions needs manager. _(sec-001; observed)_
- Project scoping: every submission operation requires the caller to be a member of the submission's project; a project-scoped template (read, edit, duplicate, delete) requires membership of its project; organisation-wide templates need only the role tier. Listing templates for a project, and creating a project-pinned template, require project membership. _(sec-002; observed)_
- Formula and rule evaluation must be safe by construction: a whitelist grammar and whitelist operators, no dynamic code execution, bounded length and depth, and bounded repetition so hostile templates cannot hang or crash evaluation. _(sec-003; observed)_
- Text answer patterns are user-authored regular expressions applied to user input on completion; pattern complexity should be bounded by a safe-regex policy chosen by the destination. _(sec-004; inferred)_

## Invariants

- Nothing is stored as a template unless it passes integrity checks; nothing becomes completed unless required and consistency checks pass. _(inv-001; observed)_
- A submission's field list is a frozen copy taken at creation; its template version number records which version it was started from. _(inv-002; observed)_
- Field keys are unique within a template and stable once stored; layout fields carry no answer and are never required. _(inv-003; observed)_
- Client-side logic (integrity checks, visibility, required counting, formula preview) mirrors the server so the editor and filler agree with it; the server is authoritative and recomputes. The client formula preview may use ordinary floating arithmetic while the server uses exact decimals, so tiny differences are possible and the server value is what is stored. _(inv-004; observed)_
- Submission references are unique per project and monotonically increase; they are never reused after deletion. _(inv-005; observed)_

## Notes

- No exact public contract is required (behavior only). Machine codes for validation issues, category keys, field type keys and answer value shapes are chosen by the destination; they must be stable and documented within the destination so editor, preview, filler and server agree. _(comp-001; derived)_
- Numeric limits mentioned here (maximum field count, length bounds, page sizes, retry counts) are ordinary behavioral parameters; the destination chooses its own values but must keep each limit explicit, enforced consistently by client and server, and documented. _(comp-002; derived)_

## Non-goals

- No implementation code, schema or table design is specified.
- A separate document-wording template, layout and clause feature is not covered here.
- Exact starter template content, user-interface wording, colours and layout are not specified.
- Offline filling and photo storage strategy are not specified.

## Test cases

- **tst-001**: Given a template whose fields have blank keys and labels 'Length' and 'Length', when it is normalised, then the keys are two distinct lower-case keys where the second has a numeric suffix of 2; a field with a punctuation-only label and no key at position 3 gets a positional key.  
  Expected: Keys are unique and derived as described; explicit keys are preserved after trimming.
- **tst-002**: Given a template with zero fields, one exceeding the maximum field count by one, one with only section headings, and one with only a section and a formula, when each is saved, then each is rejected.  
  Expected: Each response is a validation failure with a whole-template issue; a template at the maximum field count with one fillable field is accepted.
- **tst-003**: Given a single-choice field with one option, a rating field with a scale below the minimum, a rating field with a scale above the maximum, a number field with minimum above maximum, a text field with an invalid pattern and a choice default not in options, when saved, then each field produces its own located issue.  
  Expected: All issues are returned together, each with field index and key.
- **tst-004**: Given a formula 'length * width' with length 4 and width 3, when computed, then the value is 12; with width blank the value is 0.  
  Expected: Whole results are integers; blank operands count as zero.
- **tst-005**: Given formulas 'base * 2' (doubled) and 'doubled + 10' listed in the opposite order with base 5, when computed, then doubled is 10 and the second is 20.  
  Expected: Dependency order is respected regardless of field order.
- **tst-006**: Given a formula dividing a by b with b 0, when the form is completed, then completion still succeeds and that field is stored empty.  
  Expected: No error is raised; empty computed value stored.
- **tst-007**: Given formulas using power, remainder, attribute access, an unknown function, a boolean operator or a non-numeric literal, when saved, then each is rejected; formulas using rounding with 1 or 2 arguments, minimum and maximum are accepted; a rounding of 2.675 to two digits yields 2.68.  
  Expected: Only the whitelist grammar is accepted; rounding is half-up on exact decimals.
- **tst-008**: Given a formula referencing a missing field, a formula referencing itself, and two formulas referencing each other, when saved, then the first two are rejected individually and both members of the loop are reported.  
  Expected: Unknown reference, self reference and loop issues are all returned.
- **tst-009**: Given a long-text field required and shown only when a single-choice answer equals 'Yes', when the choice is 'No' then the field is hidden and not required; when 'Yes' it is visible and required.  
  Expected: Visibility and requirement states follow the rule; the missing-required list is empty for 'No' and contains the field for 'Yes'.
- **tst-010**: Given a short-text field with a require-when rule 'temperature greater than 30', when temperature is 35 then it is required; when 20 it is not; when temperature is text that is not a number it is not required.  
  Expected: Ordering operators need numbers on both sides.
- **tst-011**: Given a field hidden by its rule whose stored answer is malformed (for example an invalid choice), when the submission is completed, then validation ignores it.  
  Expected: Completion succeeds and the leftover value stays stored.
- **tst-012**: Given rules with an unknown operator, a reference to a missing field, a self reference and a loop between two fields, when saved they are rejected with specific issues; when the same stored snapshot is evaluated at run time, then show-when rules leave fields visible, require-when rules leave them not required, and evaluation terminates.  
  Expected: Static rejection and safe run-time defaults.
- **tst-013**: Given equality rules comparing '5' with 5, 'yes' with a ticked checkbox, a multi-choice answer ['b','a'] with ['a','b'], and an 'is one of' rule with candidates [1, 'x'] against the answers '1.0' and 'y', when evaluated, then the first three equalities hold, 'is one of' holds for '1.0' (numeric token match) and not for 'y'.  
  Expected: Type-tolerant comparison semantics hold.
- **tst-014**: Given a draft with required fields of every type left empty (unticked checkbox, name-only signature, empty photo list, blank text), when completed, then the unticked checkbox, empty photo list and blank text are reported as missing and the name-only signature is accepted.  
  Expected: Issue list matches the emptiness rules per type.
- **tst-015**: Given provided answers: a choice not in options, pass/fail value 'maybe', number 'abc', number below its minimum, number above its maximum, number '22,5', text shorter than its minimum length, text not fully matching its pattern, and ratings 0, 2.5, 6 on a scale of 5, when completed, then each bad value produces its own issue and '22,5' is accepted as 22.5.  
  Expected: Located consistency issues with distinct codes; comma decimals accepted.
- **tst-016**: Given a draft with pass/fail answers [pass, n/a, fail] and another with [n/a, n/a] and another with none answered and another with no pass/fail field, when each is completed, then results are fail, n/a, none, none respectively; with [pass, n/a] the result is pass.  
  Expected: Roll-up ordering fail over pass over n/a.
- **tst-017**: Given a new template at version 1 edited once with a changed field list and then once with a changed name only, when fetched, then the version is 2; submissions created before the edits still show their original fields and version 1.  
  Expected: Version increments only on field-list changes; snapshots unaffected.
- **tst-018**: Given a submission in draft with answers {a:1,b:2}, when a draft save supplies {b:3,c:4}, then answers are {a:1,b:3,c:4}; when a save supplies nothing then nothing changes.  
  Expected: Key-by-key merge, no removals.
- **tst-019**: Given a completed submission, when an edit or a second completion is attempted, then the call fails with a client error and the record is unchanged.  
  Expected: Completed is terminal.
- **tst-020**: Given three submissions created in sequence in a project, the middle one deleted, then a fourth created, when references are inspected, then they are 001, 002, 003 and 004; a second project starts again at 001.  
  Expected: Per-project highest-suffix-plus-one numbering without reuse.
- **tst-021**: Given a viewer, an editor and a manager, when each tries to list templates, create a template, complete a submission and delete a template, then viewer can only list, editor can list/create/complete, and manager can also delete; a user who is not a member of the project cannot touch that project's submissions or its pinned templates but can read organisation-wide templates.  
  Expected: Role tiers and project scoping enforced.
- **tst-022**: Given a project-scoped template from project A and a request in project B to start a submission from it, when requested, then it is reported as not found; an organisation-wide template works in any project.  
  Expected: Cross-project use of pinned templates is refused as not found.
- **tst-023**: Given a completed handover-category submission with pass/fail answers [pass, fail] (first statically required), when raising an inspection twice, then the first call creates an inspection with two checklist entries (first critical), type handover, status completed, result fail and links it; the second returns the same link with created=false.  
  Expected: Mapping as described and idempotent.
- **tst-024**: Given a draft submission, when raising an inspection, then the call fails with a client error; given a completed submission of a category outside inspection/quality/handover, the filler does not offer the action.  
  Expected: Only completed submissions qualify; the interface offers the action by category.
- **tst-025**: Given a submission with a section, a checkbox, a multi-choice with two picks, a signature with a name, three photos and an empty text, when exported, then the document lists the title lines, a section heading, 'yes', the two picks joined by a comma, 'signed' with the name, a count of three photos and a dash; the file name has no spaces.  
  Expected: Rendering matches answer formatting rules.
- **tst-026**: Given an editor with a formula field referencing a number field that is unsaved and has no explicit key, when the author types answers into the preview, then the computed value updates on each change and a show-when field appears and disappears accordingly; with no fillable field the preview shows the empty hint.  
  Expected: Live preview reflects branching and computed values using throwaway state.
- **tst-027**: Given an existing template edited in the editor so only the name changes, when saved, then only the name is sent and a field added by another user in the meantime is preserved.  
  Expected: Differential save does not clobber unrelated changes.
- **tst-028**: Given a draft with configured defaults and one already-answered field, when it is opened in the filler, then blank fields show defaults and the answered field keeps its answer; a completed submission opened later shows only stored answers.  
  Expected: Defaults seed blanks only, drafts only.
- **tst-029**: Given a shipped starter template, when it is duplicated, then a draft copy at version 1 is created, named with a copy marker, and it is an ordinary editable template with a note of its source.  
  Expected: Duplicate semantics hold; the original is untouched.
- **tst-030**: Given tags [' Safety ', 'safety', 'SAFETY', and enough distinct others to exceed the tag count bound], when saved, then tags are trimmed, case-insensitively de-duplicated and capped at the bound.  
  Expected: Tag cleaning rules hold.

## Open questions (decisions for QC Manager)

- Should template status (draft, published, archived) restrict which templates can be used to start a submission, or is it purely descriptive?
- Should shipped starter templates be editable in place or only duplicable?
- Photo answers could be stored inline in the answer payload or as separate attachments with references; which does the destination want?
- Document export fidelity (page count, character-set coverage, long-content handling) is a destination decision; should export support multi-page output and full Unicode?
- Should the server restrict raising inspections to inspection/quality/handover categories, or only the interface?
- Should the result roll-up consider answers in fields hidden by rules, or ignore them?
- Should deletion of completed submissions and of templates in use be restricted by a retention rule?
- The compact checklist runner and issue-attach picker were examined at summary depth: per-item note storage and failed-item issue prefill content are unspecified.
- Should the destination ship its own starter template set, and with what content?
- A document-wording template feature that may share this area needs its own analysis.
