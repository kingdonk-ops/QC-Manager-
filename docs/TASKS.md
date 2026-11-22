# QC Manager — task list

The full backlog, grouped by work stream. Each stream lists its tasks in build order.
The short "do next" list is [`TODO.md`](TODO.md).

Status: `todo` · `in progress` · `done` · `later`

Sources: the OCE / KERP / Project AIP review document, the 22-repository review, and
upload batches 1–12 (Foreman, OCE, MODS Connect, ArchiMesh, OpenInspection / Inspector Hub,
EspoCRM, KERP ADRs, CEOClaw).

---

## 0. Reviews (before new feature work)

| # | Task | Status |
|---|---|---|
| 0.1 | **Claude security review** — run the Claude Code security review over the whole repository (auth, Entra/OAuth, portal magic links, permissions, record visibility, file upload/download, API keys, rate limiting, migrations). Record findings with severity. | todo |
| 0.2 | **Vercel security review** — run the Vercel security review over the repository and deployment config (frontend build, headers/CSP, secrets, environment variables). Tool and access to be confirmed. | todo |
| 0.3 | **Ponytail audit** — whole-repo quality audit (bugs, load hot spots, risky untested code, dead code, what to delete, merge or split). | todo |
| 0.4 | Triage all three reports into one findings list; turn each accepted finding into a task here; fix critical and high findings first. | todo |

## 1. Known issues carried over

| # | Task | Status |
|---|---|---|
| 1.1 | Existing NCRs become `internal` after the KERP migration — decide the default, and migrate or back-fill visibility. | todo |
| 1.2 | Lobby-admitted staff without `projects.read` see the CDE as a client would — fix `is_portal_user` or the lobby grant. | todo |
| 1.3 | The Gantt reschedules activities that have no actual dates — keep planned dates when no actuals exist. | todo |
| 1.4 | Add a database trigger that blocks edits to frozen inspection template revisions (the SHA-256 is stored, the trigger is missing). | todo |

## 2. People on site (item 1)

### Stage A — identity, inductions, attendance

| # | Task | Status |
|---|---|---|
| 2.1 | Crew role: sees only assigned projects; cannot sign, close, approve or delete. | todo |
| 2.2 | Per-project module allow-list for crew, granted and revoked by a supervisor (one-tap revoke). Effective check = permission AND assigned project AND module allowed. | todo |
| 2.3 | Link + PIN sign-in for workers without Entra (personal link, 6-digit PIN, 5 tries → 15-minute lock, revoke both halves). Out-of-scope records return 404. | todo |
| 2.4 | QR gate poster per site (and one company-wide), induction link that can be sent the day before. | todo |
| 2.5 | Induction: worker or visitor, white card number or "not held yet" (flagged), emergency contact, site documents read before signing, signature, site address as signed, minute timestamp. | todo |
| 2.6 | Versioned induction templates; each signed record keeps a snapshot of the text, declaration and document titles shown. | todo |
| 2.7 | Induction register: filters, CSV export, signed PDF per induction, zip of all. | todo |
| 2.8 | Check-in / check-out by the same QR, with a location check (~250 m) at both ends; shift lands in the site diary. | todo |
| 2.9 | On-site-now count and "checked in today" list, including visitors. | todo |
| 2.10 | Muster / evacuation roll from on-site-now. | todo |
| 2.11 | Visitor and delivery sign-in/out; delivery booking board with gate and laydown clash check. | todo |
| 2.12 | Person and subcontractor compliance: certificates and licences with expiry, blocking where required. | todo |
| 2.13 | Calculated flags (never stored): possible duplicate entry, "no check-in" on hand-typed hours. Company setting: hours from diary or from check-in. | todo |

### Stage B — field capture

| # | Task | Status |
|---|---|---|
| 2.14 | `/field` mobile screens: bottom navigation (Today, Capture, Crew, Me), 48 px targets, single-column forms, light high-contrast theme. | todo |
| 2.15 | PWA: app manifest, service worker, install prompt. | todo |
| 2.16 | Offline: download today's project bundle at sign-in; queue writes; replay five at a time; server wins on conflict with a "review" prompt; never drop silently; detect captive portals. | todo |
| 2.17 | Photos: resize to 1600 px before queuing; burst capture; QUEUED badge and count; video online only. | todo |
| 2.18 | Capture details on every field record as real columns: time, latitude, longitude, accuracy, device. | todo |
| 2.19 | Inspection editor by screen width (4 / 2 / 1 panes), speed mode, copy-last, auto-advance, pinned tags. | todo |
| 2.20 | "Finish fieldwork" as a step separate from publishing; publishing and signing need a connection. | todo |

## 3. MCP server and AI (item 2)

| # | Task | Status |
|---|---|---|
| 3.1 | MCP server with Entra / OAuth sign-in, running under each user's own permissions (no company-wide admin key). | todo |
| 3.2 | Read tools across modules; write tools for diary entries, tasks, actions and drafts. | todo |
| 3.3 | Hard limits: never signs hold points, ITRs or approvals; never edits or deletes signed records. | todo |
| 3.4 | Server-side totals (hours, quantities) so the assistant does not add up figures itself. | todo |
| 3.5 | Every assistant write is audited and marked as made through the assistant ("logged by X for Y"); AI-initiated changes need human confirmation. | todo |
| 3.6 | AI record: metadata only (model, prompt version, whose credentials, time), "reviewed by" per reviewer, unreviewed calls highlighted; fails closed when not configured. | todo |
| 3.7 | Build a form from an uploaded PDF (draft only, reviewed before publishing). | todo |

## 4. Completions and quality (item 3)

| # | Task | Status |
|---|---|---|
| 4.1 | Weighted progress stages per item type (e.g. scaffold 5 %, strip 15 %, prep 10 %, install 40 %, clad 20 %, inspect 10 %); a stage counts only when its linked form / ITR is signed; feeds verified progress and EVM. | todo |
| 4.2 | Colour-by-status on lists and drawings. | todo |
| 4.3 | Quality gates in sequence on top of the MDR gate and hold points. | todo |
| 4.4 | Validation report before handover (red / amber / green): missing signatures, uncalibrated equipment, open hold points, orphan tags. | todo |
| 4.5 | Prefab / shop-fabricated dispatch gate: cannot ship until its quality check passes. | todo |
| 4.6 | Constraints and queries on activities and work packs, with owner and close-out; "ready to start" when all are cleared. | todo |
| 4.7 | QR on asset tags: scan to open ITRs, open hold points and forms for that tag. | todo |
| 4.8 | Cost of quality: rework cost per NCR, per subcontractor. | todo |
| 4.9 | "Results received" status and trigger for NDT, lab and coating results that arrive later. | todo |
| 4.10 | Commissioning stages and acceptance; completion proofs. | todo |

## 5. Signatures anyone can check (item 4)

| # | Task | Status |
|---|---|---|
| 5.1 | Seal signatures with a company Ed25519 key; keep retired keys; each record notes the key that sealed it. | todo |
| 5.2 | QR on every signed PDF linking to a public check page (no login). | todo |
| 5.3 | Exportable audit trail with the public key, checkable offline in a browser. | todo |
| 5.4 | Freeze and hash a copy of any document sent for signature; record company and signer names as on the day. | todo |
| 5.5 | Signing evidence: time, IP, browser, in person or remote, "on behalf of" with the wording shown. | todo |
| 5.6 | Several signers with a completion rule (all or any), locked once anyone signs. | todo |

## 6. Access, sharing and portal (item 5)

| # | Task | Status |
|---|---|---|
| 6.1 | Record scope levels and field-level security. | todo |
| 6.2 | Effective-access viewer ("what can this person see and do, and why"). | todo |
| 6.3 | Per-project Site Manager flag. | todo |
| 6.4 | A manager can grant only permissions they hold; owner cannot be reduced and external parties cannot be elevated (enforced in code). | todo |
| 6.5 | Split template permissions (create / edit / delete / import); delete off by default and refused while in use. | todo |
| 6.6 | Permission presets chosen at invite; invite link shown in full for copying. | todo |
| 6.7 | Share links per person, expiry as a duration, optional password, revoke now, bulk expire with a count, revoke when a contact is archived. | todo |
| 6.8 | Portal sign-in by e-mailed link that never reveals whether an address is known; "expired" vs "withdrawn" messages. | todo |
| 6.9 | External access = the stricter of company setting and the person's role on the record. | todo |

## 7. Alerts and messages (item 6)

| # | Task | Status |
|---|---|---|
| 7.1 | Alert rules: trigger, recipients by role, delay, channels (e-mail, Teams, in-app), wording template, conditions. | todo |
| 7.2 | Delivery log: pending, sent, failed (with error), skipped (with reason). | todo |
| 7.3 | Wording templates with field list and preview; required templates cannot be emptied. | todo |
| 7.4 | Separate "published" and "amended" events (what changed and why). | todo |
| 7.5 | Built-in safety and quality alerts: hold point awaiting release, overdue NCR, expiring certificate, incident reported. | todo |
| 7.6 | Follow a record; grouped notifications; daily summary through Teams. | todo |

## 8. Forms and templates (item 7)

| # | Task | Status |
|---|---|---|
| 8.1 | Form designer with conditional logic. | todo |
| 8.2 | Record locking and edit-lock warnings. | todo |
| 8.3 | Items nested up to three levels (A / A.1 / A.1.a). | todo |
| 8.4 | Fact item types (number, date, yes/no, photo only) beside rated items. | todo |
| 8.5 | Findings split into information, limitations and defects; per-project required defect fields (block or warn). | todo |
| 8.6 | Content library: standard comments, rating scales, defect categories. | todo |
| 8.7 | Date locked to submission day; forms restricted to supervisors. | todo |

## 9. Commercial

| # | Task | Status |
|---|---|---|
| 9.1 | Correspondence notice fields: event date, contract clause, estimated cost, delay days, links to change of scope and claims, response-due date from notice period. | todo |
| 9.2 | Back-charges raised from NCRs, with a ledger per party. | todo |
| 9.3 | "Waiting on whom" report across RFIs, submittals, changes and correspondence. | todo |
| 9.4 | Inbound e-mail capture into Correspondence through Microsoft 365. | todo |
| 9.5 | Read-only XER Gantt preview in the file viewer. | todo |

## 10. Platform

| # | Task | Status |
|---|---|---|
| 10.1 | Terminology labels per language (en, de). | todo |
| 10.2 | Pack and library updates offered with a diff ("keep mine / take theirs"), never forced. | todo |
| 10.3 | File storage region per project. | todo |
| 10.4 | Retention periods (signed records, rendered PDFs) and an erasure log. | todo |
| 10.5 | Cross-module project timeline view over the audit chain. | todo |
| 10.6 | Link records about one real event (incident, NCR, diary entry, claim). | todo |

## Later

| # | Task | Status |
|---|---|---|
| L.1 | SIMOPS clash check (same area, same time) from permits, areas and schedule. | later |
| L.2 | SAP PM / Maximo connector for tag-linked work orders. | later |
| L.3 | Activity start/stop timers. | later |
