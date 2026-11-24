# 18. Field mode and offline

Spec `spec-field-offline-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A phone-first field mode for site workers that keeps working with no signal. A worker opens a personal link received by text message, enters a short numeric PIN, and gets a full-screen mobile shell with five bottom tabs (daily overview, time capture, crew, issue reporting, personal status). Everything the worker records (time, crew punches, issues with photo and location, non-conformance, safety observation, haul ticket) is saved on the device first and queued, then replayed to the server in order when connectivity returns, idempotently so nothing is created twice. The shell always shows whether the device is online, how many captures are waiting, how large the backlog is and its age, warns when device storage is nearly full, and lets the worker retry, dismiss, or review refused captures. Open crew shifts and the crew pick list survive page reloads. A one-tap download stores the open punch items, the day's checklists and the crew for offline reading. A second, office-side flavour of offline editing (diary, punch list, inspections) shows a sync status indicator and, on a version conflict, a side-by-side merge dialog. The application is installable as a standalone app with an automatically updating offline cache. The queue engine, merge engine and field-session backend are outside what this specification fully covers and are described only as far as the screens reveal them.

## Behaviour

- Sign-in: the worker follows a personal link containing a one-time token, types a short numeric PIN (six digits in the origin; the destination chooses; digits only, input trimmed to the required length, numeric keypad and one-time-code autofill hints), and submits by button or Enter. A PIN that is not exactly the required length is refused on the device with a hint, without a request. On success the server returns a session token, the project and the user; these and the PIN are stored for the browser session only, and the worker is taken to the shell, replacing the sign-in screen in history. A refused sign-in shows the server's message (or the HTTP status); a transport failure shows a network error hint; the button shows progress and is disabled while busy or until the required number of digits is present. _(beh-001; observed)_
- The worker session is a token plus PIN plus project and user. Every field request carries the token as a standard bearer credential and the PIN as a second request header. Without a session the shell shows a signed-out header and each tab invites the worker to open the link from their message. The session is read during render and is the same object while the stored values are unchanged, so effects keyed on it do not restart on every sync tick; it changes only when a stored value changes, becomes absent when storage is cleared, and a re-sign-in on the same project yields a stable new object. _(beh-002; observed)_
- Daily overview tab: lists the worker's diary entries for today's date (device-local date) with date, status and notes, a refresh control, and an empty hint pointing to the time-capture tab. Reads go directly to the server. How a failed read is distinguished from an empty result is an open question. _(beh-003; observed)_
- Time-capture tab: the worker picks a task from a fixed short list, a start and end time (illustrative defaults 07:00 and 16:00), and an optional note; hours are computed as the positive difference rounded to two decimals, shown live, and saving is disabled when hours are zero. Saving queues two ordered captures: an idempotent request that makes sure today's diary entry exists, then a work activity on that date carrying description (note or task), hours as text, start and end stamps and the task. A success line says the time is saved and will sync when online. _(beh-004; observed)_
- Crew tab: a foreman maintains today's crew for the project. People are added from the project's people-directory pick list (carrying their directory id) or, if the person is in nobody's directory, by typed name (no id). Each member can be punched in (the start instant is stored on the device only; nothing is queued, because the hours are unknown) and punched out (queues the ensure-entry request and a crew-punch activity with hours between start and end rounded to two decimals, floored at zero, task, name, and the directory id when there is one). After punch-out the member is idle again. _(beh-005; observed)_
- A shift belongs to the calendar day on which it began (device-local), not the day of punch-out, so a night shift from 22:00 is filed against the evening it started. An unparseable start falls back to today. _(beh-006; observed)_
- Open shifts survive page reloads and tab closure: the crew list, including who is punched in and when, is kept on the device per project (not per day, so a shift past midnight is still open). Rows that no longer read as a crew member are dropped individually, rows written by an earlier version that lacked a directory id are kept with an empty id, malformed or non-list data reads as an empty crew, a missing project key reads and writes nothing, and a storage failure on write never throws. Every change to the crew is persisted at the same moment it is applied. _(beh-007; observed)_
- The crew pick list is cached per project on the device and refreshed whenever a fetch succeeds. A fetch that fails returns nothing rather than an empty list so the cache survives; an empty or failed answer never overwrites a working cache; clearing is a separate deliberate act. Cached rows without an id or a name are dropped, thin rows get an empty code and a person type, unreadable data reads as empty, and storage failures never throw. The pick list hides people already on today's crew; typed rows (no id) claim nobody. The picker stays a picker while the project has any list, even when everyone is added, and only offers free typing on request. _(beh-008; observed)_
- Issue-reporting tab offers four report kinds: punch item, non-conformance, safety observation and haul ticket. Punch has its own form: title, priority (low, medium, high, critical, default medium), optional note, optional photo from the device camera, and optional device location with accuracy (requested with a bounded time limit). Non-conformance carries title, description (defaulting to the title), severity minor, major or critical and a fixed type. Safety observation carries a type (good practice, unsafe act, unsafe condition, near miss), description, severity and likelihood on a three-step low, medium, high scale. A haul ticket carries material, net tonnes, plate, and direction inbound or outbound. Each capture is stamped with the device capture time. A saved confirmation says it is saved on the device and will sync when there is signal. _(beh-009; observed)_
- Tonnage typed with a comma or spaces is normalised (for example 1 024,125 becomes 1024.125); only non-negative numbers with up to three decimals are accepted; negatives, text and four decimals are refused. A haul ticket with a non-numeric weight is not queued and the field is shown as wrong; an empty weight is allowed (ticket without weight yet) and is sent without a weight. _(beh-010; observed)_
- A punch item with a photo is saved in two parts because queued captures carry only structured data: the punch itself goes through the queue, idempotent on a client-generated operation key; the photo is parked on the device as a durable record keyed by that same key. Once the punch has synced and its server identifier is known (from the drain result, or after a reload from the session's applied-operation ledger), the photo is uploaded to that punch and the stored bytes are removed. A failed photo upload keeps the record for the next sync. Recently raised issues, including already synced ones, remain visible across reloads, newest first, with a marker while a photo is still pending. _(beh-011; observed)_
- Field captures use purpose-built capture endpoints authorised by the field session, not the office-user endpoints, because a field session lacks the office sign-in and membership that those require. Capture endpoints exist for punch, photo, non-conformance, safety observation and haul ticket. Each capture carries a client operation key so the server answers duplicates once. The server hands each capture to the owning domain service, so rules are not duplicated on the device. _(beh-012; observed)_
- Write-through helpers for the office-side offline registers: online, a create or update goes straight out; offline or when it fails without any server answer, the write is kept on the device and queued and the caller receives the optimistic record flagged as new or edited, so the screen carries on. A create is made idempotent by one operation key shared by the online attempt and the queued retry, so a request that landed but lost its answer is not created twice. A record that exists only on the device cannot be patched on the server, so updates to it are queued. A version-conflict answer to an online update queues the update and triggers an immediate sync so the drain can park it for a merge. _(beh-013; observed)_
- Sync scheduling in the field shell: connectivity is tracked reactively; shortly after the device comes online (a short settling delay of about a second, illustrative) the queue is drained in capture order; a capture made while online triggers an immediate drain, while offline it just waits; a manual sync-now is available only while online; the pending list and count are refreshed from the queue on every change so badge and review list can never disagree. Correctness against double drains rests on idempotency keys and a server-side ledger, not on the scheduler. _(beh-014; observed)_
- Offline and sync badge in the field header: offline shows a warning pill with the waiting count; online with a backlog or an active drain shows a tappable pill with the count (and a spinner while syncing) that triggers a sync; online with nothing waiting shows a calm online pill, optionally hidden. The count combines the field queue and the separate crew-time queue. _(beh-015; observed)_
- Pending-sync review panel on the personal status tab lists every waiting capture with a friendly type label, method, relative capture time (just now under about a minute, then minutes, hours and days; a future time from clock skew reads as just now) and status: waiting if never attempted, failing with a retry count if a transient failure has been recorded. Failing items sort first, then oldest first, ties broken by a stable key. A header shows the total, a connectivity chip, and a counts line (waiting versus need attention). Sync now is disabled when empty, while syncing or while offline, and an offline hint explains that items sync on reconnect. Each item can be dismissed (removing only the local capture, not anything already applied on the server). An empty state says everything is synced. _(beh-016; observed)_
- Captures the server refused after a drain are listed in a refusal panel with the type label and the reason; a capture refused as too old (the server accepts a capture for replay only up to a configured maximum age; the destination chooses the limit) gets a plain sentence telling the worker to enter it again; other reasons show the server's detail or a generic rejected message. Refusals are permanent, not retried. _(beh-017; observed)_
- Captures made by other users on the same device are held, never sent under the current sign-in. The panel shows a held section naming who each group is waiting for (or that the owner is unknown for earlier sessions), explains they will never be sent under this sign-in, and offers export as a downloadable JSON document and discard on the device behind an explicit confirmation stating the count and that it cannot be undone. Held captures of the field queue and the crew-time queue are exported and discarded together. _(beh-018; observed)_
- Crew-time captures need the office identity that the field session lacks, so in the origin they use their own queue. They are listed and counted beside the others in the panel but cannot be dismissed from there; they replay through their own queue. Whether the destination keeps two queues is an open question. _(beh-019; observed)_
- Storage meter: one line shows how many captures wait, their size and the age in days of the oldest; photos are the bulk, so their bytes come from the parked photo records. If device storage is nearly full a warning says to sync soon so photos are not lost, styled more severely when full. The meter is hidden when nothing waits and storage is fine. On mount the app asks the browser to keep the stored data from being evicted; refusal is harmless. A storage error never breaks the panel. _(beh-020; observed)_
- Download for offline: one request, authorised by the field session, returns the open punch items, the day's inspection checklists and the project crew, each with a truncated flag, plus the server time. They are stored on the device for the session's project, stamped with the server time and the local time. The worker is told how many items (punch plus inspections) were saved; if the request does not land (no signal, expired session) nothing is stored and a retry hint is shown. The control is disabled without a session or while busy. This action only reads; nothing is written to the server. _(beh-021; observed)_
- A scoped offline cache for the field shell is registered when the shell opens, so the shell and last-viewed data load without signal; registration failure does not affect queued captures. _(beh-022; observed)_
- Office-side sync status indicator states, in precedence order: conflict (needs merge) above everything, offline above pending work, syncing while a drain runs, error when the server refused changes, pending with a count (singular and plural wording), and synced when nothing waits. Tapping on pending syncs now; tapping on error toggles a list of refused changes, each dismissible with the server's reason; tapping on conflict opens the merge dialog. Hover text shows the last sync time or says it has not synced in this session. Target size is at least about 44 pixels. _(beh-023; observed)_
- Merge dialog: when a record was changed on the server while the user was offline, only the fields that could not be merged automatically are shown, side by side as mine (this device) and theirs (server): long text both sides changed, and checklist items both sides changed differently (an item removed on one side is shown as removed). The user picks a side per text field or per checklist item, or writes a combined text by hand; nothing is pre-selected and Apply stays disabled until every conflict is decided. Choosing a side for text records that side's value; typing records a manual value. Extra actions: discard my changes and keep the server copy, and decide later. Simple fields never reach the dialog because the local edit, being the last writer, already won. The dialog traps focus, closes on Escape, is labelled for assistive technology and reports resolved decisions as one structure of text decisions and checklist decisions. _(beh-024; observed)_
- A per-record marker says the record is saved on this device for records flagged new or edited, with a hint that it is not on the server yet and will upload when back online. A merge history list shows a bounded number of recent past merges for a server-held record (time, base and target versions, and the fields resolved), and is hidden for device-only records and when empty. _(beh-025; observed)_
- Offline cache rules for static content: a cache-first lane serves only same-origin fonts, images and application asset files, only when the response status is success, with a bounded lifetime and a bounded entry count (destination chooses values). It never takes cross-origin requests, never the API, never worker scripts, never page documents. Cross-origin images are left to the browser's own cache, and opaque or failed cross-origin responses are never stored. Caches left by an earlier application version are deleted on every application start (never throwing, even without cache storage or when deletion is blocked, and leaving the current cache alone). _(beh-026; observed)_
- Other cache lanes: localization bundles use stale-while-revalidate for the one language read, with bounded lifetime and entry count; reads of the API use network-first with a bounded timeout and the cache only as an offline fallback; other methods bypass the cache and fail normally; reads of resources authorised by a link token are never cached because the token is the credential; navigation falls back to the application shell so a refresh on any route works offline, except for API, static and prefixed asset paths. Large localization bundles are deliberately not precached. _(beh-027; observed)_
- Personal status tab: shows a short how-it-works card (sign in, log today, capture even with no signal, auto-sync) with links to the office areas the captures feed, a signed-in or open-your-link line, an online or offline line, the download-for-offline control and the pending-sync panel. _(beh-028; observed)_

## Inputs

- Sign-in input is a one-time token from the link and a short numeric PIN. The PIN is also sent with every later field request. _(in-001; observed)_
- Each queued capture carries a unique client-generated operation key, enough request information to replay it, a display kind, and, for replayed items, a capture time and a retry count; punch captures may add latitude, longitude and accuracy in metres only when the device provided them and the accuracy is a finite number. _(in-002; observed)_

## Outputs

- Drain results per capture are applied (optionally with the created record identifier), rejected (permanent, with a reason code) or retryable (kept with an incremented retry count until success or the queue's retry ceiling). A refused capture is answered with a rejected status and a reason code. _(out-001; observed)_
- Held captures export as one JSON document with the field queue's and the crew-time queue's held captures side by side. _(out-002; observed)_

## States and transitions

- Queued capture: waiting (never attempted) -> failing (a transient failure recorded, retried on each drain) -> removed on applied, rejected, dismissed, or past the retry ceiling. A capture owned by another user is held instead of waiting. _(st-001; observed)_
- Crew member: idle -> punched in (stored on device only) -> punched out (queues captures, back to idle). _(st-002; observed)_
- Raised issue photo: pending (blob kept) -> uploaded (blob removed, server identifier stored). Idempotent: marking an unknown record is a no-op. _(st-003; observed)_
- Download for offline: idle -> busy -> done with a count, or failed with a retry hint. _(st-004; observed)_

## Timing and ordering

- Captures replay in the order they were captured (first in, first out); a diary entry creation always precedes the activity that relies on it. _(ord-001; observed)_
- A drain is scheduled shortly (about a second) after connectivity returns and immediately after a capture made online; a manual sync never runs offline. _(ord-002; observed)_
- A photo upload follows its punch's successful sync; it uses the server identifier obtained after the punch is applied. _(ord-003; observed)_
- Review list order: failing first, then oldest first, ties by a stable key; relative time grows from just now through minutes, hours and days. _(ord-004; observed)_

## Edge cases

- A capture made while offline and a capture whose request lands but loses its answer are both safe: the same operation key is reused for the retry so the server answers the second try as already applied. A duplicate diary-entry creation on replay is treated as already applied. _(edge-001; observed)_
- A device-only record has a temporary local identifier and cannot be updated on the server until its create has synced; edits are queued behind it. _(edge-002; observed)_
- Browsers without durable database storage fall back to in-memory storage for raised issues so a capture never crashes; every local store degrades to an empty or no-op result on storage failure. _(edge-003; observed)_
- A project that is not yet known on cold start (the shell sees the link token before the project) reads and writes nothing for crew and directory stores and picks them up when the project arrives. _(edge-004; observed)_
- Capture on a day boundary: the time-capture tab uses the device-local today; time entries queue the entry creation before the activity so replay order is guaranteed by the queue's first-in-first-out order. _(edge-005; observed)_
- An unrecognised capture kind label is shown as human-readable words rather than a raw token; an empty label stays empty. _(edge-006; observed)_

## Errors

- Sign-in errors are shown inline: bad PIN format, server refusal with its message or status, network error. _(err-001; observed)_
- Download for offline failure (no signal, expired session, server refusal) shows a retry hint and stores nothing. _(err-002; observed)_
- Replayed captures can be refused permanently (for example as too old); transient failures keep the capture queued. _(err-003; observed)_

## What it must not do

- A punch-in is never queued; only a punch-out is. _(neg-001; observed)_
- Held captures of another user are never sent under the current sign-in. _(neg-002; observed)_
- Dismissing a capture does not undo anything already applied on the server. _(neg-003; observed)_
- Cross-origin images, API calls, worker scripts and page documents are never served by the cache-first lane; mutations are never cached. _(neg-004; observed)_
- Download for offline never writes to the server. _(neg-005; observed)_

## Security

- The field session is deliberately weak-scope: a one-time link plus PIN, no password, stored for the browser session only, sent as bearer token plus PIN header; it does not grant office rights and field captures use dedicated endpoints that the server authorises by session and project. _(sec-001; observed)_
- Captures on shared devices carry their owner; those of other users are held and can only be exported or discarded, never replayed under another identity. _(sec-002; observed)_
- The offline cache never stores reads authorised by a link token (the token is a credential) and never stores mutations. Cache-first storage is limited to same-origin successful responses, so cross-origin and opaque responses never enter long-lived storage. _(sec-003; observed)_
- The PIN and token live in per-session browser storage on the device; the device location is requested only on the issue form and only when the browser offers it. _(sec-004; observed)_

## Invariants

- A capture is never created twice on the server: the idempotency key is generated once per capture and reused on every attempt, and the server also keeps an applied-operation ledger. _(inv-001; observed)_
- The waiting badge, the waiting count and the review list always agree because they are all derived from one read of the queue. _(inv-002; observed)_
- A cached working list is never replaced by an empty or failed answer. _(inv-003; observed)_
- An open shift is never lost silently: it is persisted at the same moment it is changed. _(inv-004; observed)_
- A person already on today's crew is never offered again for adding. _(inv-005; observed)_
- A failure of any local storage, cache or location facility degrades silently and never blocks a capture. _(inv-006; observed)_

## Notes

- Behavioral compatibility only. The destination keeps its own names, routes and layout and chooses its own numeric values (PIN length, replay age limit, cache lifetimes and sizes, timeouts, delays). The interface needs idempotent create operations keyed by a client-generated key, an applied-operation ledger readable by the session, a replay age limit, a one-request offline pack, and field-session authentication distinct from the office sign-in; these are product behaviors to re-specify for the destination, not names to copy. _(cmp-001; derived)_
- Accessibility expectations: touch targets of at least about 44 pixels, safe-area padding for notched phones in standalone mode, status regions that announce changes politely, dialog with focus trap, Escape and labels, alert role for storage and download failures, and numeric keypad hints for PIN entry. _(cmp-002; observed)_

## Non-goals

- No implementation code, storage key, route, header name, queue structure or identifier is carried across.
- The queue engine, three-way merge engine, storage quota thresholds and field-session backend are not fully specified beyond what the screens reveal.
- Exact visual design (palettes, icons, spacing) is not a requirement.
- Office screens other than their sync indicator and merge dialog are out of scope.
- Do not reproduce origin provenance markers.

## Test cases

- **ts-001**: Given the sign-in screen, the worker enters a PIN one digit too short, then a full-length PIN with a failing server, then a full-length PIN with a succeeding server.  
  Expected: Too short: hint shown, no request, button disabled. Failing server: its message is shown. Success: session stored for the browser session and the shell opens, with the sign-in screen replaced.
- **ts-002**: Given a stored session, read it twice, change the project, clear storage, then sign in again.  
  Expected: Same object while unchanged; new object after a change; absent after clearing; stable new object after re-sign-in.
- **ts-003**: Given the device is offline, the worker saves a time entry of 07:00 to 16:00 with a task from the short list.  
  Expected: Two captures are queued in order (diary entry then activity, with 9 hours), a saved message appears, the offline badge shows the count, and nothing is sent.
- **ts-004**: Given the device comes back online with two waiting captures.  
  Expected: After the short settling delay the captures are sent in capture order, the badge shows syncing then clears, and the review panel shows everything is synced.
- **ts-005**: Given a capture whose request reaches the server but loses its answer, and is replayed.  
  Expected: The same operation key is used and the server answers as already applied; only one record exists.
- **ts-006**: Given a start time equal to or after the end time.  
  Expected: Hours read zero and saving is disabled.
- **ts-007**: Given a foreman adds a person from the pick list, punches them in, closes the page and reopens it, then punches them out the next morning after a night shift that began at 22:00.  
  Expected: The open shift is still open after reopening; the capture is filed against the evening it began; it carries the person's directory id.
- **ts-008**: Given crew data in storage that is not valid text, not a list, or contains rows missing identifiers or names, and a row written by an earlier version that lacks a directory id.  
  Expected: Unreadable data reads as empty; bad rows are dropped individually; the older row survives with an empty directory id; writes under a failing storage never throw.
- **ts-009**: Given a working cached pick list and a refresh that returns nobody or fails.  
  Expected: The cached list remains; two different projects keep separate lists; typed rows with no directory id do not hide anyone; a person already on the crew disappears from the choices.
- **ts-010**: Given an issue form with a title, high priority, a photo and a device location, saved offline; later the punch syncs and the photo uploads; and a second case where the photo upload fails.  
  Expected: The punch is queued and the photo is parked with the same key; after sync the photo is uploaded to the created punch and its stored bytes are removed; on failure the record stays pending for the next sync; the recent-issues list shows both, newest first.
- **ts-011**: Given a haul ticket with weight 24,5, then lots, then empty, and a tonnage of 1 024,125, then -1, then 1.2345.  
  Expected: 24.5 is queued; lots is refused with the field shown wrong and nothing queued; empty is queued without a weight; 1024.125 accepted; negative and four-decimal values refused.
- **ts-012**: Given a non-conformance with an empty description.  
  Expected: The queued capture carries the title as description, severity as chosen, and the capture time.
- **ts-013**: Given a review panel with two waiting and one failing capture (three retries) captured at different times, and a crew-time item from the other queue.  
  Expected: The failing one is listed first with its retry count; the others follow oldest first; the crew-time item is listed and counted but has no dismiss control; the counts line reads two waiting and one needs attention; dismissing an ordinary item removes only that capture.
- **ts-014**: Given the device is offline with waiting captures, and later empty.  
  Expected: Sync now is disabled with an offline hint; when empty an everything-synced state shows and sync now is disabled.
- **ts-015**: Given a capture refused as older than the configured replay limit.  
  Expected: It is listed in the refusal panel with a sentence that it is too old and should be entered again.
- **ts-016**: Given captures owned by two other users and one with unknown owner on the same device.  
  Expected: A held section lists each owner with counts and an unknown-owner line; export produces one document; discard first asks for confirmation naming the count and only then discards.
- **ts-017**: Given a backlog with parked photos and a device whose storage is nearly full, then full, then healthy with nothing waiting.  
  Expected: A summary line shows count, size and oldest age; a warning appears and is stronger when full; nothing is shown when nothing waits and storage is fine.
- **ts-018**: Given the download-for-offline control pressed with a working server, then with no signal, then with an expired session.  
  Expected: On success a count of saved items (punch plus inspections) is shown and the punch items, checklists and crew are stored for the project; on failure nothing is stored and a retry hint is shown.
- **ts-019**: Given an office register where the indicator state moves through synced, offline with items, waiting with one then several items, syncing, refused changes, and a conflict.  
  Expected: Labels and states follow the precedence conflict, offline, syncing, error, pending, synced; tapping pending syncs now; tapping error shows refused changes that can be dismissed; the conflict state beats all others; the control stays at least about 44 pixels.
- **ts-020**: Given a conflict with one long-text field changed on both sides and one checklist item changed differently on both sides.  
  Expected: Apply is disabled until both are decided; choosing the server side for the text and this device's side for the item reports exactly those decisions; typing a combined text reports a manual value; discard-my-changes and decide-later are offered; the dialog is not shown when closed.
- **ts-021**: Given a create made offline, then an edit of the same unsynced record, then an online edit hitting a version conflict.  
  Expected: The create is queued with the shared key and shown flagged as new; the edit of the device-only record is queued; the conflicting edit is queued and a sync is triggered so it is parked for merge; flagged records show a saved-on-this-device marker.
- **ts-022**: Given requests for a same-origin application asset, a same-origin image, a cross-origin image, an API call, a worker script and a page document.  
  Expected: Only the first two are served by the long-lived cache lane; the other four are not.
- **ts-023**: Given a browser that still holds a cache from an earlier application version, one without cache storage, and one that refuses deletion, on application start.  
  Expected: The earlier cache is deleted and reported; without storage nothing happens; on refusal nothing throws and nothing is reported; the current cache is never deleted.
- **ts-024**: Given an installed app opened offline on a deep page.  
  Expected: The application shell loads from the cache for any route except API and static paths; last-viewed reads come from the offline fallback of the network-first lane; mutations fail normally and are captured by the queue where the screen supports it.
- **ts-025**: Given an unrecognised capture label and an empty one.  
  Expected: The unrecognised label is shown as readable words; the empty one stays empty.

## Open questions (decisions for QC Manager)

- The capture queue engine (ordering, retry ceiling, owner tagging, idempotency handling), the three-way merge engine, the sync status store (including precedence between error, offline and syncing), the storage quota thresholds, the connectivity detection and the scoped service worker registration were not fully available. Their exact behavior (retry ceiling count, quota percentages, which fields count as simple versus long text) needs its own unit or a clarifying pass before the destination relies on it.
- The server side of the field mode (one-time link issuance and text-message delivery, PIN verification and lockout rules, session lifetime, capture endpoints, applied-operation ledger, offline pack assembly with its truncation limits, replay age limit) is outside this specification; only its use by the screens is described. A separate unit is needed for these.
- The PIN is stored in session storage and re-sent on every request. Decide whether the destination should keep this model or use a short-lived token only.
- The time-capture defaults and the fixed task list are a starter set; decide whether the destination wants project-configurable tasks and defaults.
- A typed crew name carries no directory id and can double-count a person against the office timesheet, which reconciles on that id; the origin accepts this deliberately for subcontractor workers. Decide whether the destination should require a link or allow later reconciliation.
- Crew-time captures run on a separate queue with the office sign-in and cannot be dismissed from the panel; decide whether the destination wants one queue and one identity model.
- A failed read on the daily overview tab is indistinguishable from an empty result. Decide whether the destination should show an error state instead.
- How the replay client should treat an unexpected response shape (for example a list instead of a single capture answer) is unclear in the origin, which counts it as applied. Decide the destination's handling.
- The cache-first lane must never persist opaque or failed cross-origin responses, and caches from earlier versions must be purged; confirm how the destination guarantees this across upgrades and whether any cross-origin content should ever be cached.
- Installability and the cache lanes were captured from the frontend build configuration for the installable app only as far as read; the remaining options of the API read lane and any update prompt (the origin explicitly defers one) were not captured.
- The daily overview tab shows read-only diary entries and the guide content was not read; wording and onboarding content are not requirements.
