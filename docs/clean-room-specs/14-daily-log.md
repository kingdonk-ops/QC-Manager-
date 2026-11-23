# 14. Daily site log

Spec `spec-daily-log-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A daily site log records one project day: weather, crew and equipment, work done, delays, safety notes and a drawn sign-off. Two record styles are described generically. A legally sealed diary moves one way through open, closed, signed and archived, with a tamper-evident content fingerprint taken at signing. A structured field report moves through draft, submitted and approved and carries a drawn signature of the site representative. Weather can be obtained automatically for the site location, a record dated ahead of the site's current day is refused or flagged, and signatures are captured by drawing. All numeric limits, windows and thresholds below are illustrative; the destination chooses its own values.

## Behaviour

- Opening a sealed diary for a project day is refused with a validation-style failure when the date text is not a valid calendar date in year-month-day form. The check happens before anything is stored. _(beh-001; observed)_
- Opening a sealed diary is refused with a validation-style failure when its date is later than the current UTC calendar day plus a small slack (illustratively one day). Past dates (back-dating) are allowed. The slack exists so a site ahead of UTC can open its own current day. The refusal message explains that a diary is a contemporaneous record. _(beh-002; observed)_
- Only one sealed diary may exist per project per calendar day; a second creation attempt is refused as a conflict. _(beh-003; observed)_
- A newly created diary starts in the open state with header crew and equipment counts as supplied. _(beh-004; observed)_
- A structured field report records a report date, a report type (illustratively daily, inspection, safety, concrete pour), a weather word from a fixed vocabulary (illustratively clear, partly cloudy, cloudy, overcast, rain, snow, fog, hazy, storm), a temperature within a plausible range, humidity as a whole percent from 0 to 100, short free-text wind and precipitation notes, workforce rows (trade, head count, hours per person), equipment names, work performed, delays with delay hours, visitors, deliveries, safety incidents, materials, photo references, notes, signer name and drawn signature. A report with no stated weather word carries the word clear. _(beh-005; observed)_
- When a field report is created, its site location is taken from coordinates supplied with the request; if either coordinate is missing it is filled from the owning project's stored address. The stored address may state coordinates in several shapes (flat latitude and longitude values, a short pair, or a nested group); a usable pair must be numeric, latitude within -90..90 and longitude within -180..180, otherwise the location is treated as unknown. _(beh-006; observed)_
- When a location is known and an external weather service credential is configured, the field report create flow requests current conditions for that location and stores the returned snapshot on the report: temperature, apparent temperature, humidity percent, wind speed in metres per second, wind direction as one of sixteen compass points derived from degrees (each point spans 22.5 degrees centred on its heading), a text description, an icon code, and rain in the last hour in millimetres (zero when absent). _(beh-007; observed)_
- When the weather snapshot was obtained and the user left temperature or humidity empty, those two report fields are filled from the snapshot; values the user typed are never overwritten. _(beh-008; observed)_
- Automatic weather retrieval for a field report never blocks creation: with no credential, no location, a non-success answer, a network failure or an unreadable answer, the report is created without a snapshot and no error is shown to the caller. The external request has a bounded wait (illustratively 10 seconds). _(beh-009; observed)_
- The sealed diary offers an explicit weather fetch for a project, a target day (year-month-day), a latitude and a longitude (both required, range-checked) and a flag saying whether to keep the result (default keep). This flow does not read the project address; the caller gives the coordinates. _(beh-010; observed)_
- The diary weather fetch uses a forecast-style source for the target day unless that day lies several days before today (illustratively five or more), in which case it uses a historical-archive source. Both are asked for hourly temperature, humidity, precipitation, condition code and wind plus sunrise and sunset for that single day in UTC. _(beh-011; observed)_
- The hourly answer is reduced to one daily summary: mean temperature and mean humidity (rounded to 2 decimals), maximum wind speed in km/h, total precipitation in mm, the most frequent condition code of the day mapped to a short condition label and descriptive text (unrecognised codes map to an unknown label), sunrise and sunset as returned, and the count of hours with precipitation above a small threshold (illustratively 0.1 mm). Missing hourly values are ignored in each statistic. If temperature, humidity, precipitation and condition are all missing the result is treated as unusable. The summary's capture time is midnight UTC of the target day. _(beh-012; observed)_
- The diary weather fetch result reports whether anything was fetched, the target day, the identifier of the stored weather record when kept, and the summary (numbers as text). When the upstream fails, times out (illustratively after 8 seconds) or returns nothing usable, the result says nothing was fetched with an empty summary and no record is stored; this is not an error response. A malformed target day is refused with a validation-style failure. _(beh-013; observed)_
- A stored weather record from the fetch carries a label for the fetch service, the summary figures, the location used and the rain-hour count as extra data. Weather records for a project day are listed newest first using UTC day boundaries, with the current UTC day when no day is given. _(beh-014; observed)_
- A diary becomes sealed by signing. Signing an open diary first closes it automatically, then freezes its content: a deterministic fingerprint (cryptographic hash) is computed over the diary header fields, its entries ordered by time then identifier, and its photos ordered by capture time then identifier. Identical logical content always yields the identical fingerprint. _(beh-015; observed)_
- Each signing creates a signature record with a revision number starting at 1 and increasing by 1 on every re-sign; the previous signature record is replaced, so at most one stored signature exists per diary. The record keeps the fingerprint, signing time, signer identity when known, signer role, optional signer name and optional drawn-signature image data. Allowed signer roles (illustratively owner, supervisor, inspector, client) form a fixed list. The drawn-signature text is optional and length-bounded (illustratively 200000 characters). _(beh-016; observed)_
- After signing, the diary keeps a reference to who signed: the owner role fills the owner signature reference, every other role fills the supervisor signature reference; the reference is the signer name when given, otherwise a shortened prefix of the fingerprint. _(beh-017; observed)_
- Reading an archive signature is allowed only to users who may read diaries and who have access to the diary's project. _(beh-018; observed)_
- A field report's drawn signature is an embedded image (base64 data URI) of an accepted image type, with an empty value also accepted; any other content, an unaccepted type, or a value larger than a size cap (illustratively 2 MiB) is rejected at input validation with an explanatory message. The accepted-type list is a decision point (see open questions). _(beh-019; observed)_
- The signature capture control lets a person draw strokes with a pointer, touch or pen on a blank area; a stroke is committed to the field report value only when the stroke ends (pointer released or leaving the area) and at least some ink exists, producing a PNG image data URI. A clear action wipes the area and sets the value to nothing. When a stored signature exists the control first shows it as an image with a clear action instead of a blank area. The control can be disabled (no drawing, no clear action). The drawing area has an accessible label and a hint asking for the site representative's signature. _(beh-020; observed)_
- A field report moves draft to submitted to approved. Submitting runs the report validation rules with submitted state; approving requires submitted state and records the approver and approval time, writes an audit entry and refreshes downstream labour-log data. Submission fails with a bad-request failure unless the report is a draft; approval fails with a bad-request failure unless the report is submitted. _(beh-021; observed)_
- Editing a field report, deleting it, and linking documents to it are allowed only while it is a draft; otherwise a bad-request failure explains that only drafts are editable. _(beh-022; observed)_
- The diary PDF download carries the document language as a request parameter: the language the caller explicitly picked wins over the interface language; when neither is known no language parameter is sent and the server chooses. The fallback file name uses the diary day, or the diary identifier when the day is unknown, and a server refusal message is passed through unchanged to the user. _(beh-023; observed)_

## Inputs

- Create diary input: project, day text, optional supervisor, free-text weather summary, labour count, equipment count, notes and extra data. _(in-001; observed)_
- Create field report input may include optional latitude (-90..90) and longitude (-180..180) used only to fetch weather; non-finite numbers are rejected. _(in-002; observed)_
- Field report text fields, row counts and numeric fields are length- and range-bounded (illustratively: work performed up to 10000 characters, delays, safety incidents, notes and deliveries up to 5000, visitors up to 2000, signer name up to 255, wind note up to 50, precipitation note up to 100; up to 1000 rows per list; delay hours 0..10000; per-row hours 0..1000000; head count non-negative). The destination chooses its own limits. _(in-003; observed)_

## Outputs

- Create, update, submit and approve of a field report return the report together with any non-blocking validation warnings raised by the rules. _(out-001; observed)_
- The stored weather snapshot of a field report is a small set of named measures (temperature, apparent temperature, humidity percent, wind speed m/s, wind compass label, description, icon code, rain mm in last hour). _(out-002; observed)_

## States and transitions

- Diary: open to closed to signed to archived is strictly one-way. Attempting a same-state or backward move is refused as a conflict that tells the caller the flow is one-way. Closing records the closing time and closer when known and then attempts, without ever failing the close, to publish the day's crew summary. _(st-001; observed)_
- Diary unlock: a signed or closed diary can be reopened with an optional reason by an authorised manager-level user; the reopening is appended to an unlock history on the diary (who, when, previous state, reason), earlier signatures are retained for audit, and a fresh signing creates a new revision. Unlocking an already open diary does nothing. Unlocking an archived diary is refused as a conflict because archive is terminal. _(st-002; observed)_
- Archiving is allowed only from signed; archiving an unsigned diary is refused as a conflict so every archive carries a sealed fingerprint. Signing an archived diary is refused as a conflict. _(st-003; observed)_
- Field report: draft to submitted to approved; there is no path back. A weather snapshot, once stored, is not refreshed by later edits. _(st-004; observed)_

## Timing and ordering

- Diary weather fetch and field report weather fetch each have a bounded wait (illustratively 8 and 10 seconds). Day boundaries for weather record queries are UTC calendar days. _(time-001; observed)_
- Signing happens after the automatic close (if needed) and uses the diary, entries and photos as stored at that moment; the notification announcing the signing is emitted only after the signature is stored. _(time-002; observed)_

## Edge cases

- With a one-day slack, a diary dated exactly one day after the UTC current day is accepted; two days after is refused. _(edge-001; observed)_
- Project address coordinates stored as text numbers are accepted if they convert to numbers in range; a non-numeric or out-of-range value, a missing project, or a missing address all mean no location and silently no weather. _(edge-002; observed)_
- When no wind direction degrees are returned, the compass label is currently derived from zero degrees and so reads as north; this is a decision point (see open questions), not a requirement. _(edge-003; observed)_
- Sunrise and sunset given as full timestamps are compared as instants so a day whose UTC stamps wrap past midnight is not misjudged. Bare times are compared as written, with a tolerance that reads an early-morning sunset (illustratively before 03:00) as after midnight rather than flagging it. _(edge-004; observed)_
- A diary entry whose time lies outside a window around the diary day (illustratively more than one day before or two days after) triggers a non-blocking warning; shift work across midnight is expected to pass. _(edge-005; observed)_
- Crew consistency warning: equipment count above zero with a labour count of zero produces a warning only, because standby plant can be legitimate. _(edge-006; observed)_

## Errors

- Future-dated sealed diary: validation-style refusal (HTTP 422 class) with an explanatory message. Malformed day: validation-style refusal. Duplicate project day: conflict (409 class). Missing diary: not found (404 class). _(err-001; observed)_
- Editing, deleting, or changing entries or photos of a signed or archived diary is refused as a conflict with a structured body carrying a stable machine-readable code, an explanatory message, the diary identifier and its state; the message points to the unlock step available to managers. _(err-002; observed)_
- Observed weather records (manual or sensor source) whose capture time is later than now plus a slack (illustratively one day) fail the validation rule as an error; forecast-style sources may lie ahead. Sunrise not before sunset also fails as an error. _(err-003; observed)_
- A field report whose report date is more than a day after the reference day (today unless overridden by extra data) yields a warning while draft and an error once submitted or approved. A submitted or approved report with no work, delays, notes or crew yields an error; delay hours above zero with no stated cause is a warning on drafts and an error afterwards; more than a per-person daily hours ceiling (illustratively 24), or more than the same ceiling in total per machine (operating plus standby plus breakdown), yields a warning-class finding per row. _(err-004; observed)_
- Signature input that is not an embedded image, uses an unaccepted type or exceeds the size cap is rejected as invalid input. _(err-005; observed)_

## What it must not do

- The weather retrieval must not raise an error to the user for a field report when the service is unavailable or unconfigured, and must not overwrite temperature or humidity the user entered. _(neg-001; observed)_
- Closing a diary must not change its header crew and equipment counts; the authoritative crew roll-up is computed on demand as header plus entries, so repeated closing never inflates counts. _(neg-002; observed)_
- An archived diary can never be reopened. _(neg-003; observed)_

## Security

- Weather fetch for the sealed diary is gated by its own permission tier and by access to the target project; field report operations are gated by read, create, update, delete and approve permission tiers, with project access checked in the layer above the business logic. _(sec-001; observed)_
- Linking documents to a field report is rejected with an unprocessable response if any document does not belong to the report's own project; a missing document and a foreign-project document yield the same response so document existence cannot be probed. _(sec-002; observed)_
- The external weather request is built with a fixed host and structured query values so caller input cannot redirect it; the service credential is never returned to clients. _(sec-003; observed)_

## Invariants

- A sealed diary's fingerprint is reproducible: the same diary fields, entries and photos in any storage order always produce the same fingerprint. _(inv-001; observed)_
- Revision numbers per diary only increase; at most one signature record exists per diary at a time. _(inv-002; observed)_
- No diary is dated beyond the permitted future slack at creation. _(inv-003; derived)_

## Notes

- The destination is an existing application with its own record names; this spec states behavior only. Weather vocabulary words, signer roles, report types, state sequences and every numeric limit, window and threshold in this spec are illustrative semantics; the destination chooses its own values, and should preserve words and sequences only where existing stored records or clients rely on them. _(compat-001; inferred)_
- Weather suppliers are interchangeable provided the stored summary meets the stated shape and failure behavior; no particular supplier is a compatibility requirement. The summary reduction approach (mean, maximum, sum, most frequent condition, rain-hour count) and the forecast-versus-archive cutoff are behavior to keep in spirit, with thresholds chosen by the destination. _(compat-002; inferred)_

## Non-goals

- No implementation code is generated.
- Do not reproduce origin provenance markers.
- PDF layout, translations and branding of the exported diary are outside this unit and are described only where they affect the language request.
- Trade productivity-loss calculation derived from weather is neighbouring behavior and is not specified here.
- Photo archive, drone survey and reality-capture attachments to the diary are covered by other specs.

## Test cases

- **test-001**: Given today is 2026-03-10 UTC and a one-day slack, when a diary is created for 2026-03-11.  
  Expected: Creation succeeds in the open state.
- **test-002**: Given today is 2026-03-10 UTC and a one-day slack, when a diary is created for 2026-03-12.  
  Expected: Refused as unprocessable with a message that a diary cannot be opened ahead of the site date; nothing stored.
- **test-003**: Given a diary already exists for project P on 2026-03-01, when a second diary is created for P on that day.  
  Expected: Refused as a conflict.
- **test-004**: Given an open diary with two entries and one photo, when it is signed by role supervisor with name Ada Quinn.  
  Expected: Diary is closed then signed, a signature record at revision 1 holds a fingerprint, the supervisor reference equals Ada Quinn.
- **test-005**: Given the diary from test-004 is unlocked with a reason and re-signed with no content change.  
  Expected: Revision becomes 2, only one signature record remains, the fingerprint equals the earlier one, the unlock history holds one entry with the reason.
- **test-006**: Given a signed diary, when an entry is edited, then when the diary is archived, then when unlock is attempted.  
  Expected: The edit is refused as a conflict with the stable machine-readable body; archive succeeds; unlock is refused as a conflict because archive is terminal.
- **test-007**: Given an open diary, when archive is requested.  
  Expected: Refused as a conflict because the diary must be signed first.
- **test-008**: Given a weather fetch request for coordinate 48.1, 11.6 on a day 2 days ago with keep set, and the upstream returns 24 hourly points whose precipitation exceeds the rain threshold in 3 of them.  
  Expected: Forecast-style source used; result says fetched, includes a stored record identifier and a rain-hour count of 3; temperature is the mean of the hourly values.
- **test-009**: Given a weather fetch request for a day 9 days ago.  
  Expected: The historical-archive source is used.
- **test-010**: Given the upstream times out, when a diary weather fetch is requested.  
  Expected: Result says nothing fetched with an empty summary and no record id; no error status.
- **test-011**: Given a diary weather fetch request with a malformed day text.  
  Expected: Refused as unprocessable.
- **test-012**: Given a project whose address states a nested coordinates group with numeric text values and a credential is configured, when a field report is created with no coordinates and the user left temperature empty but typed humidity 70.  
  Expected: Weather is fetched for the project location; temperature is filled from it; humidity stays 70.
- **test-013**: Given the project address holds latitude 120 and a credential is configured, when a field report is created without coordinates.  
  Expected: No fetch is attempted, no snapshot stored, creation succeeds.
- **test-014**: Given no weather credential is configured, when a report is created with coordinates.  
  Expected: Creation succeeds without a snapshot and without error.
- **test-015**: Given wind direction 350 degrees and then 11 degrees.  
  Expected: Compass labels are north-northwest and north respectively.
- **test-016**: Given today is 2026-03-10 and a draft field report dated 2026-03-20 is created, then submitted.  
  Expected: Creation succeeds returning a future-date warning; submission is blocked by an error finding for the future date.
- **test-017**: Given a submitted field report, when an edit, a delete, or a document link is attempted.  
  Expected: Each is refused as a bad request stating that only drafts are editable.
- **test-018**: Given a signature value of a PNG data URI under the size cap, then a value starting with plain text, then a data URI of a type outside the accepted set, then a value of 3 MiB, then an empty string.  
  Expected: First and last accepted; the middle three rejected as invalid input.
- **test-019**: Given the signature control with no stored value, when a person draws a stroke and releases, then presses clear.  
  Expected: After release the value becomes a PNG image data URI; after clear the value is empty and the area is blank. A press with no movement and release produces no value.
- **test-020**: Given the signature control opened with an existing stored image and then disabled.  
  Expected: The stored image is shown; no clear action appears and drawing is impossible.
- **test-021**: Given a manual weather record whose capture time is three days ahead, and a forecast-source record with the same time.  
  Expected: The manual record fails the not-in-future rule; the forecast record passes.
- **test-022**: Given sunrise 20:00 and sunset 06:30 as bare times, then sunrise 07:00 and sunset 06:30.  
  Expected: The first passes (early-morning sunset read as after midnight); the second fails the sunrise-before-sunset rule.
- **test-023**: Given a diary PDF download with interface language Turkish and no explicit choice, then with explicit choice German, then with no interface language.  
  Expected: The language parameter is Turkish, then German, then absent; the fallback file name uses the day when known else the diary identifier.
- **test-024**: Given a diary with equipment count 2 and labour count 0.  
  Expected: Saved with a warning only.
- **test-025**: Given an open diary with header labour 5 and two entries stating labour 3 and 2, then it is closed twice via sign and re-sign.  
  Expected: Header count stays 5 after each; the roll-up on demand reports 10.

## Open questions (decisions for QC Manager)

- Decision point: the two record styles overlap. Should the destination offer both a legally sealed diary and a draft/submit/approve structured field report, or one record style that can optionally be sealed?
- Decision point: should diary weather fetch fall back to the project's stored site coordinates when none are supplied, as field report creation does, or keep requiring coordinates from the caller?
- Decision point: field report weather is fetched only at creation and diary weather only on explicit request; is a refresh option wanted when the date or site changes?
- Decision point: whether a drawn signature may be a vector image type. Vector images can carry active content, so decide whether the accepted list should be raster types only, and apply the same choice to every upload surface in the destination.
- Decision point: a missing wind direction currently reads as north; decide whether a missing direction should instead be left empty.
- Decision point: whether future-dated field reports should be refused at creation (current behavior only warns while draft and refuses at submission).
- Decision point: define how error-severity validation findings turn into refusals for diary weather and entry writes (status code and body shape); finding severities are as stated in this spec.
- Decision point: define the exact refusal response when error findings block a field report submission; the transition itself must be refused.
- Decision point: which role threshold counts as manager-level for unlocking, and which roles may sign; the destination defines its own role matrix.
- Decision point: the diary signing request accepts a signer name and drawn-signature text without checking that the text is an image; decide whether to validate it like the field report signature.
- Decision point: the future-date slack is anchored to UTC rather than the site's own time zone; decide whether to anchor to the project time zone when known.
- Scope note: drawn signature capture is specified only for field reports; the diary's own signing screen is not specified here and is a decision for the destination.
