# 15. Photo archive

Spec `spec-photo-archive-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

The photo archive is one project-scoped collection over every photo the application holds: direct uploads and photos that other registers (diary, punch list, field reports, progress) already own. Each photo carries a capture time and position with a recorded source, and a tamper-evident evidence record that includes the camera's compass heading and tilt when known. Photos can be browsed as a grid, a day timeline, a map or albums, narrowed by text, tag, album, date range, source register, category, linked record and presence of a position. Two photos of the same spot can be compared as a saved before/after pair with a draggable reveal slider, and the daily diary can pair located photos across two dates automatically. All numeric constants (accuracy cutoffs, distances, radii, windows, page sizes and similar) are illustrative; the destination chooses its own values.

## Behaviour

- A position is usable only when both coordinates are finite numbers, latitude is within -90..90, longitude within -180..180, and the pair is not exactly (0, 0), which is treated as a missing fix rather than a site. _(beh-001; observed)_
- The effective position of a photo follows precedence: a position typed by a person, else the position measured by the device at capture (which carries an accuracy radius, kept when it is a non-negative number), else the position in the camera's metadata. The chosen source (manual, device, camera) is recorded. If none is usable the photo has no position. _(beh-002; observed)_
- The effective capture time follows the same precedence: typed, else device capture time, else the camera's shutter time; the source is recorded. A photo with none keeps no capture time; the upload time is never substituted as a capture time. _(beh-003; observed)_
- On upload the device-measured position and time (when the device supplied a valid one) overwrite the position and time read from the file, and the position accuracy is stored; otherwise the values read from the file are kept. Naive timestamps are read as UTC. The stored copy of the file has its location metadata removed by default as a privacy measure while the coordinates read from the original remain on the photo record; the file's hash, pixel size and thumbnail state are stored on the record. _(beh-004; observed)_
- Compass bearing and orientation: the device capture block may carry a heading in degrees (0..360), pitch (-180..180) and roll (-90..90), plus altitude; out-of-range or non-numeric values are dropped and kept values rounded to 2 decimals. If the device gave no heading, the camera's image-direction tag (0..360) is used as heading. The camera's standard orientation code (1..8) is also kept. These are stored in an orientation block of the photo's evidence record; they are not separate searchable photo fields, are not shown in the photo detail panel, and are not used by any filter. _(beh-005; observed)_
- Each stored photo has an evidence record holding: file hash, byte size, server receive time, uploader, camera tags, the device block, the effective location with its source (device or camera), the effective capture time with its source (device, camera, or server receive time when neither exists), and the orientation block. A three-level evidence grade is derived: the highest level when the hash exists, the position is from the device with accuracy at or better than a cutoff (illustratively 50 m) or from the camera, and the time is from the device or camera; an intermediate level when hashed but missing a usable position or time source; the lowest level (none) when there is no hash or no record. The names of the levels are a decision point (see open questions). _(beh-006; observed)_
- Editing a photo may change caption, category, tags, capture time, position, zone and location link, each with a bounded length (illustratively caption 2000, category 100, zone 128). Latitude and longitude must be given together or neither (unprocessable otherwise); changing the position clears the stored accuracy; setting a capture time marks its source as manual; tags are trimmed, de-duplicated in order, blanks dropped, and a maximum count kept (illustratively 50). _(beh-007; observed)_
- Archive filters, combined with AND: free text (case-insensitive contains over file name, caption and zone), tag (exact, case-insensitive match against the photo's tags), album membership, date range, source register (documents, daily diary, punch list, field reports, progress; any other value is refused as unprocessable), category, linked record (kind and identifier both required to apply), has-position (true: both coordinates present; false: either absent), include archived (default off), and an explicit list of photo identifiers for exports. _(beh-008; observed)_
- Date range filtering compares against the capture time, falling back to the upload time when a photo has no capture time; bounds are inclusive. The page turns a chosen start day into the start of that UTC day and an end day into the last second of that UTC day so photos taken late on the end day stay inside. _(beh-009; observed)_
- Listing order is newest capture first (upload time when no capture time), ties broken by identifier descending. Paging is by an opaque cursor derived from the last item's sort time and identifier; the page size is bounded (illustratively 1..200, default 60); the response has the items, the next cursor when more remain, and the total count matching the filters. A tampered or unreadable cursor is treated as start from the beginning. The total reflects the tag filter. _(beh-010; observed)_
- Timeline: photos are grouped by calendar day (UTC) of capture, newest day first, newest photo first within a day. A photo with no capture time is grouped by its upload time and counted in the day's undated count; a photo with neither goes into a final unknown bucket. The response pages over day groups (illustratively page size 1..1000, default 500) and reports the number of days matched. _(beh-011; observed)_
- Map output is a standard geographic feature collection (GeoJSON) containing only photos with a usable position, coordinates in longitude-then-latitude order rounded to a fixed precision (illustratively 7 decimals), each feature carrying identifier, caption, file name, capture time, source register, accuracy and category (defaulting to site). The map call forces the has-position filter on, and includes the project's site anchor position when one exists. _(beh-012; observed)_
- Photos of one record (by record kind and identifier) can be listed with offset paging (illustratively default 200, maximum 500). Eight record kinds can be linked: bill-of-quantities position, schedule activity, location, punch item, inspection, diary, field report, safety observation. _(beh-013; observed)_
- Saved before/after comparison: a comparison names a before photo, an after photo and an optional title (bounded, illustratively 200 characters). The two must be different photos (unprocessable otherwise) and both must exist in the same project (not found otherwise). Comparisons can be listed (illustratively page default 100, maximum 500) and read; each returns the full before and after photo records. Creation needs the edit tier, reading the read tier. _(beh-014; observed)_
- Before/after slider: the after photo fills the frame and the before photo is clipped on top from the left up to the handle position, expressed as a percentage that starts at 50 by default (or a supplied initial value). Dragging with a pointer anywhere in the frame moves the handle to that position, clamped to 0..100 and rounded to one decimal; a frame of zero width reads as 50. The handle is a keyboard-focusable slider with an accessible name and minimum, maximum and current value: arrow keys move a small step (illustratively 2 points), page keys a larger step (illustratively 10), Home goes to 0 and End to 100, other keys are ignored, and values stay within 0..100. Corner labels mark before and after, and under the frame each photo's capture date is shown, or an undated label when unknown. Each photo has alternative text from its caption or file name. _(beh-015; observed)_
- Automatic before/after pairing in the daily diary: given all candidate photos, an earlier day and a later day (compared by calendar date of capture; an unreadable date gives no pairs), only photos that have a position are considered. For each earlier-day photo in input order, the nearest not-yet-used later-day photo within a pairing radius (illustratively 15 metres, great-circle distance) is chosen; each later photo is used at most once; unmatched photos are left out. Each pair reports both photo identifiers, the distance rounded to a fixed precision (illustratively 4 decimals) and both capture times. _(beh-016; observed)_
- Page views are grid, timeline, map, albums and compare; an unknown view value falls back to grid. Filter state lives in the page address so views can be shared: text, tag, album, from and to days (year-month-day only), source register and category (only from the known lists), a position-only toggle, and a record-kind plus identifier pair; malformed values are dropped, unrelated address parts such as the view are kept, and the number of active narrowing filters (text, category, tag, album, from, to, source, position-only) is shown. A record target is sent only when both kind and identifier are known. _(beh-017; observed)_
- Photo categories offered: site, progress, defect, delivery, safety, aerial, other. Bulk actions apply per selected photo only when it would change: set category (skipped if already equal), add tags (case-insensitive, only the missing ones are added), or toggle a special field tag on or off. A category suggestion stored on a photo is offered only when it names a known category different from the current one, with optional confidence and suggested tags. _(beh-018; observed)_
- A record-embedded photo strip lists the photos linked to one record, hides photos whose source register is the hosting register itself, and renders nothing (and sends no request) until the host record exists. _(beh-019; observed)_
- Upload: a bounded number of files per request (illustratively 1 to 50; none or more is a bad request); a failing file is reported with its file name and reason without failing the others; an optional record target (kind and identifier both or neither, unprocessable otherwise) is verified to exist in the same project before any file is stored; a malformed device capture block is unprocessable; uploads are rate limited per user (too many requests when exceeded). Each stored photo announces its creation. Phone users are offered the camera; the page reads the device position, time and heading at capture. _(beh-020; observed)_
- Photos held by other registers are indexed without copying files: a drafted index row needs a file path and a source identifier; indexing is idempotent per project, register, source record and path; a diary photo that is itself an archive photo is linked rather than indexed twice; paths escaping the permitted upload locations are refused; remote addresses are indexed without thumbnails. Indexed photos are archived (not deleted) when their source record is deleted or drops the file, and deleting an indexed photo archives it while deleting an uploaded one removes it. A backfill job can index every existing photo of a project and is safe to rerun. _(beh-021; observed)_
- Albums: a project album has a unique name (trimmed; blank is unprocessable, duplicate is a conflict), description, sort order and optional cover photo (which must be in the same project). Adding photos (illustratively 1..500, all in the album's project) sets the first as cover when none exists; removing the cover picks another remaining photo or none. Albums list with photo counts. Export of an album or an explicit photo list produces a ZIP of originals with one descriptive record per photo and a manifest listing missing files; export is an asynchronous job with status and a download once ready. _(beh-022; observed)_
- AI suggestions (caption, tags, progress reading, hazard) are stored as pending and change nothing until a person accepts them; acceptance writes caption or tags, links the photo for a progress reading (and emits a notification without moving progress), and may use an edited payload that is re-validated; reviewing a non-pending suggestion is a conflict; rejecting records the reviewer. A model's confidence is clamped to 0..1 (values 1..100 read as percentages); progress rows may only name records the photo is already linked to; tags are lower-cased, de-duplicated, with bounded count and length (illustratively at most 8 of at most 40 characters); hazard boxes must be fractions within the image. Analysis requests are rate limited. _(beh-023; observed)_
- Quality rules reported for the archive (all thresholds illustrative): capture time present (warning); capture time not far in the future (illustratively 24 hours) and not long before the project start (illustratively a year) (error); position within a distance of the project's site anchor (illustratively 2 km) and fix accuracy at or better than a cutoff (illustratively 50 m) (warnings; photos without a position skipped); linked records exist in the same project (error); the same file hash not archived twice (information); evidence grade at the highest level (information, raised to a warning for photos linked to punch items or inspections with no evidence); pending AI proposals reviewed within a window (illustratively 7 days) (information); accepted hazards linked to a safety observation (warning); the file still readable in storage (error). _(beh-024; observed)_

## Inputs

- The device capture block (supplied as text with an upload) may contain latitude, longitude, accuracy radius, altitude, capture time, heading, pitch and roll; all optional. If nothing usable remains the upload records no device block. _(in-001; observed)_
- Upload form also takes category (default site), caption, a comma-separated tag list and an optional record target. _(in-002; observed)_

## Outputs

- A photo record exposes identifier, project, file name, caption, category, tags, capture time and its source, upload time, uploader, position, accuracy, pixel size, hash, source register and source record, category suggestion, thumbnail state, location link, zone, archived flag, evidence grade, authenticated file and thumbnail addresses, and links; it never exposes server storage paths. _(out-001; observed)_
- A per-photo export record contains identifier, project, file name, caption, category, capture and upload times, position block (or none), hash, size in pixels, source, zone, sorted unique tags, links and the evidence record. Entry names inside the ZIP are unique, never contain a path, strip characters that are unsafe in file names and are limited in length. _(out-002; observed)_

## States and transitions

- Photo: active to archived (indexed photos on user delete or source removal) and back to active when the source record references the file again; uploaded photos are deleted outright. _(st-001; observed)_
- AI suggestion: pending to accepted, edited or rejected; no other moves. _(st-002; observed)_

## Timing and ordering

- Grid is newest-first by capture; timeline newest day first with unknown last; ZIP export streams originals file by file rather than loading them whole. _(time-001; observed)_

## Edge cases

- A device position of exactly (0, 0) is ignored and the camera position, if any, is used. _(edge-001; observed)_
- A heading of exactly 0 or exactly 360 is accepted; 361 or a negative value is discarded. _(edge-002; observed)_
- A photo with no position never appears on the map or in the map output but still appears in the grid and timeline. _(edge-003; observed)_
- A photo with no capture time sorts and groups by its upload time but is counted as undated in the timeline and shown with an undated label in comparisons. _(edge-004; observed)_
- In diary pairing where two earlier photos are both nearest to the same later photo, the later photo goes to the first earlier photo in input order; the second may take another within the radius or stays unpaired. _(edge-005; observed)_

## Errors

- Not found: unknown photo, album, comparison, suggestion or link; record target or document missing or in another project (identical answer for both, so identifiers elsewhere are not revealed); file or thumbnail missing in storage. _(err-001; observed)_
- Unprocessable: unknown source register filter, malformed device block, incomplete record target, lone latitude or longitude on edit, same photo as before and after, blank album name. Conflict: duplicate album name, reviewed suggestion. Bad request: no files, too many files. Too many requests: upload or analysis rate limit. _(err-002; observed)_

## What it must not do

- Upload time is never presented as capture time; a missing capture time stays missing. _(neg-001; observed)_
- Accepting an AI progress reading never changes bill-of-quantities or schedule progress. _(neg-002; observed)_
- The diary's automatic pairing never pairs photos without a position and never pairs beyond the pairing radius. _(neg-003; observed)_

## Security

- Photo files and thumbnails are served only through authenticated, project-checked calls; file paths of indexed photos are resolved only inside the permitted upload locations and remote addresses are never fetched by the server; location metadata is stripped from the stored copy by default. _(sec-001; observed)_
- Record targets and album members are checked to be in the same project as the photo; mismatches return the same answer as missing. _(sec-002; observed)_

## Invariants

- Every read is scoped by project; an archived photo is hidden from listings unless explicitly included. _(inv-001; observed)_
- A saved comparison always references two distinct photos of its own project. _(inv-002; observed)_
- Slider position is always within 0..100. _(inv-003; observed)_

## Notes

- The evidence grade has three levels (highest, intermediate, none). Backend and client must share one vocabulary for the intermediate level so that every grade renders with a proper label; the chosen names are a neutral decision for the destination (see open questions). _(compat-001; observed)_
- Numeric constants (accuracy cutoff, site distance, future slack, pairing radius, AI review window, page sizes) are illustrative and the destination chooses its own. The five-register and eight-link-kind vocabularies are data semantics to preserve only where existing records rely on them. Any standard spherical-earth distance model is adequate at these distances; the exact earth radius constant is immaterial. _(compat-002; observed)_

## Non-goals

- No implementation code is generated.
- Do not reproduce origin provenance markers.
- Thumbnail generation, image decoding limits and the vision model provider call are not specified.
- Drawing pin placement behavior is summarized only.
- Compass-bearing display or search is not specified; whether to offer it is a decision point.

## Test cases

- **test-001**: Given an upload with typed position (48.1, 11.6), a device fix (48.2, 11.7, accuracy 8 m) and camera position (48.3, 11.8).  
  Expected: Position (48.1, 11.6) with source manual; without the typed one, device with accuracy 8; without both, camera with no accuracy.
- **test-002**: Given a device fix of (0, 0) and a camera position (51.0, 7.0).  
  Expected: Camera position used, source camera.
- **test-003**: Given no typed time, device time 2026-05-04T08:00:00Z and camera time 2026-05-04T07:55:00 (naive).  
  Expected: Capture time is the device time with source device; with no device time, the camera time read as UTC with source camera; with neither, no capture time and the upload time is not used.
- **test-004**: Given a device block with heading 271.456, pitch -200, roll 12.  
  Expected: Orientation keeps heading 271.46 and roll 12; pitch is dropped.
- **test-005**: Given no device heading and a camera image-direction of 90, then a camera direction of 400.  
  Expected: Heading 90 recorded from the camera; 400 is ignored and no heading recorded.
- **test-006**: Given photos with: device location accuracy 30 m plus device time; camera location plus camera time; location but only server receive time; no hash.  
  Expected: Grades are highest, highest, intermediate, none.
- **test-007**: Given an edit that sets only latitude.  
  Expected: Refused as unprocessable; setting both clears the accuracy.
- **test-008**: Given 130 photos of one project over several days and a filter of source punch list, text slab, has position, between 2026-10-01 and 2026-10-31.  
  Expected: Only photos matching all conditions return, newest capture first; a photo taken at 23:00 UTC on 2026-10-31 is included.
- **test-009**: Given 130 matching photos, page size 60, then following the returned cursor twice, then a cursor edited by hand.  
  Expected: Pages of 60, 60, 10 with total 130 and no cursor on the last; the edited cursor restarts from the first page.
- **test-010**: Given a source filter value that is not a known register.  
  Expected: Refused as unprocessable.
- **test-011**: Given photos taken on 2026-10-02 (two, one with no capture time but uploaded that day) and 2026-10-01 and one with no times at all.  
  Expected: Groups: 10-02 (count 2, undated 1), 10-01, then unknown; newest photo first within a day.
- **test-012**: Given three photos, one without position, when the map is requested for a project with a site anchor.  
  Expected: Two features with longitude first, coordinates rounded to the fixed precision; the anchor included; the unlocated photo absent.
- **test-013**: Given a comparison request with the same photo twice, then with a photo of another project, then with two valid photos and a title.  
  Expected: Unprocessable; not found; created with both photo records returned.
- **test-014**: Given the slider at 50, when Right arrow then Page Up are pressed, then Home, then a letter key.  
  Expected: Values 52, 62, 0; the letter is ignored; the before layer clip tracks the value (62 shows 62 percent of the before photo).
- **test-015**: Given the slider frame 200 wide starting at x 100, when a pointer is at x 150, at 0, at 999, and when the frame width is 0.  
  Expected: 25, 0, 100 and 50.
- **test-016**: Given morning photos A1 (0 m, 0 m offset), A2 and afternoon photos B1 (8 m from A1), B2 (12 m from A1, 5 m from A2), B3 with no position, and a pairing radius of 15 m.  
  Expected: A1 pairs with B1 (distance about 8); A2 pairs with B2; B3 never pairs; a photo 20 m away is not paired.
- **test-017**: Given a diary pairing with an invalid date text.  
  Expected: No pairs.
- **test-018**: Given address parameters view=map, from=yesterday, source=nowhere.  
  Expected: View map; from and source are dropped; the active filter count is 0. Given view=carousel, the view is grid.
- **test-019**: Given filters with tag rebar, from 2026-10-01 and position-only, written to the address and read back with the view kept.  
  Expected: Identical filters returned, count 3, view preserved; target kind alone produces no target filter.
- **test-020**: Given selected photos: one in category site with tag Rebar, one in defect with tag field, one in site; actions set category defect, add tags rebar and slab, toggle field on.  
  Expected: Only photos that would change are patched; Rebar is not duplicated by adding rebar; the second photo is skipped for the category and for the field toggle.
- **test-021**: Given a photo strip for a punch item whose list includes a photo from the punch list register and one linked photo.  
  Expected: Only the linked photo shows; with no record yet nothing renders and no request is made.
- **test-022**: Given an upload of 51 files; and an upload of 3 files where the second is not an image.  
  Expected: Bad request; then two photos stored plus one error naming the second file.
- **test-023**: Given an index request for a photo path escaping the upload locations, then the same valid path indexed twice, then its source record deleted.  
  Expected: Refused; one index row; the row becomes archived and disappears from default listings.
- **test-024**: Given an album named Pack, a second album Pack, and adding two photos.  
  Expected: Conflict on the duplicate; first added photo becomes cover.
- **test-025**: Given a photo taken 3 days in the future, a photo at 3 km from the anchor with accuracy 10 m, a photo with accuracy 80 m, and two photos with the same hash, using illustrative thresholds of 24 hours, 2 km and 50 m.  
  Expected: Error for the future photo, warning for the distant photo, warning for inaccurate fix, informational duplicate notes for both twins.
- **test-026**: Given a pending caption suggestion accepted with an edited text, then accepted again.  
  Expected: Caption written, status edited; the second acceptance is a conflict.

## Open questions (decisions for QC Manager)

- Decision point: compass heading, pitch and roll are captured and kept in the evidence record but are not exposed on the photo record, in the detail panel, in map output or in any filter; decide whether the destination should show or search bearing (and whether the map should draw a viewing direction).
- Decision point: automatic before/after pairing exists only in the daily diary and uses position alone; decide whether the archive should offer it, and whether heading similarity should be a pairing criterion.
- Decision point: before/after pairing is greedy in input order, so the result depends on the order of photos; decide whether a globally nearest assignment is preferable.
- Decision point: grade naming. The evidence grade has three levels, and the backend and client currently use different names for the intermediate level so that level can render without a proper label. Choose one shared vocabulary for all three levels (names, display labels and any filter values) used identically by backend, client and exports.
- Decision point: map and exports include photos at poor accuracy without a marker; decide whether poor-accuracy positions should be flagged visually.
- Decision point: stored copies have location metadata removed by default while the record keeps the coordinates; decide whether to keep the default and who may read the coordinates.
- Decision point: tag filtering is applied after the main query, which loads every matching row; decide whether tags should be indexed or queried so that totals and paging scale.
- Unknown: the photo detail panel, upload camera flow and the shared device-capture helper are not fully specified; heading acquisition on the device (sensor permission handling) is unspecified.
- Unknown: permission tiers by role are not specified; the destination defines its own role matrix.
