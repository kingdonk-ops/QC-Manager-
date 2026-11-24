# 23. Portal access management

Spec `spec-portal-access-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Administrators manage accounts for external parties (several kinds of outside collaborators). They invite people by email, re-send invitations, suspend and reinstate accounts, grant and revoke per-record access, and read an audit trail of which external user viewed, downloaded or signed which document, when, and from which network address. External users sign in with a one-time link (no password), receive a time-limited session, and can only reach records they were explicitly granted. Invitation links are valid for a limited window; a person whose link lapsed can ask for a new one without learning whether the address is registered. External accounts are fully separate from internal accounts and never gain internal access.

## Behaviour

- Inviting an unknown email address creates an external account in the invited state with the chosen external role, optional full name, language (default English) and timezone (default UTC), and records the invitation time. The address is trimmed and lower-cased before lookup and storage, so addresses are unique case-insensitively. _(prt-b-01; observed)_
- Inviting an address that already has an account is idempotent: no second account is created, the existing record is reused (role and name are not overwritten by the invitation), and a fresh sign-in link is issued. An account in the lapsed (expired) status is moved back to invited. An account that is already active keeps its status; an account that is suspended keeps its suspended status (so a link issued to it cannot be redeemed until it is reinstated). _(prt-b-02; observed)_
- Every invitation issues a single-use login link valid for 24 hours from issue. The administrator response carries the plaintext link credential and its expiry exactly once; the server persists only an irreversible digest of the credential, so later reads of the user never reveal it. _(prt-b-03; observed)_
- An invitation may carry an administrator-chosen in-app destination (up to 512 characters). It is stored with the link and returned when the link is redeemed so the external user lands on that page after sign-in. The destination is not embedded in the link address. _(prt-b-04; observed)_
- An invitation request has a flag, on by default, asking the server to email the link when outbound mail is configured. When set, the invitation is durably saved before the email is attempted. The response reports one of four outcomes: sent, failed, mail not configured, or not requested. A mail failure never fails the invitation; the administrator can always copy the link from the response. _(prt-b-05; observed)_
- Re-sending an invitation to an existing account issues a fresh 24-hour link using the account's stored role, name, language and timezone (no destination is carried), saves it before emailing, always attempts the email, and returns the link once plus the email outcome. It is refused with a conflict when the account is suspended, with a message telling the administrator to reinstate the person first. An unknown account yields not-found. _(prt-b-06; observed)_
- Suspending an external user (setting status to suspended through a partial update) also revokes every live session of that user immediately. Reinstating sets the status to active. The partial update accepts only four status values (invited, active, suspended, expired) and may also change full name, language, timezone and the email-notification opt-in; fields left out are untouched and null values are ignored. Status can be set to any of the four values directly, with no transition restrictions beyond that. _(prt-b-07; observed)_
- Listing external users supports filtering by role and by status, paging (offset at least 0, limit 1 to 200, default 50), newest account first, and returns the total match count alongside the page. Each returned user shows identity, role, language, timezone, status, invitation time, last sign-in time, email opt-in, and created and updated times, plus any lockout-related status the destination chooses to support. _(prt-b-08; observed)_
- Invitation expiry is link-level: a link not redeemed within 24 hours is rejected at redemption as expired. Lapsing of a link does not itself change the account status. A separate account-level lapsed status exists and can be set by an administrator; no automatic transition into it was determined. _(prt-b-09; observed)_
- Accounts that are suspended or lapsed cannot redeem a link, cannot obtain a new self-service link, and any existing session of theirs stops validating, even if the session itself has not expired. _(prt-b-10; observed)_
- Self-service sign-in link request: any caller can submit an address. The server always answers accepted with an identical body whatever the address, and does the lookup, link creation and email after responding so response timing does not depend on registration. A link is created only if the address belongs to an account that is not suspended or lapsed, the last link for that account was issued at least 60 seconds ago, and outbound email is configured. Creating a new link ends every unused login link the account still holds, so one live login link exists at a time. Internal failures after the response are swallowed and recorded for operators. _(prt-b-11; observed)_
- Redeeming a link validates purpose, single use and expiry, requires the owning account to be neither suspended nor lapsed, marks the link used atomically (so exactly one session results even under concurrent redemption), moves an invited account to active on first success, stamps last sign-in, opens a 7-day session recording network address and client descriptor, and returns the plaintext session credential once together with the profile, session expiry and stored destination. _(prt-b-12; observed)_
- External session validation requires a bearer credential, looks it up by digest, rejects revoked or expired sessions and inactive owners, and on success updates the session's last-seen time. Sign-out revokes the presented session only. _(prt-b-13; observed)_
- Document access logging by the external user: the client reports a view, download or sign event for a record kind and identifier. The server first checks the caller holds a live grant on that exact record at a sufficient level (sign events need the signing level; view and download events need the viewing level). With no sufficient grant the request is refused as forbidden and nothing is logged. Otherwise one entry is appended with user, record kind, record identifier, action, server timestamp and caller network address, and the entry is returned with a created status. _(prt-b-14; observed)_
- Downloading a shared document: the grant check happens before the document is looked up, and an ungranted caller receives the same forbidden answer whether or not the identifier exists. After the grant check, a missing record gives not-found and a record whose file is gone gives a gone answer. Only when the file is confirmed present is a view event logged (always recorded as a view, even when the file is delivered as an attachment). Media (video, audio, image) is delivered inline and everything else as an attachment, with range support. _(prt-b-15; observed)_
- The administrator reads the access log with optional filters for external user and record kind, paging (offset at least 0, limit 1 to 500, default 100), newest first. Entries are append-only; no capability edits or deletes them. Entries show user, record kind, record identifier, action, event time, network address and creation time. _(prt-b-16; observed)_
- Access rules link one external user to one record (kind plus identifier) at one of four ordered levels (view, comment, submit, sign); a higher level satisfies every lower requirement. Granting is an upsert per user, kind and record: repeating it replaces level, grant time, granter and expiry. A rule may carry an expiry; once passed it denies access exactly as if absent. Revocation deletes the rule by its own identifier (silently succeeding if absent). The administrator lists rules with filters for user and record kind, paging (limit 1 to 500, default 200), newest grant first. _(prt-b-17; observed)_
- Per-kind accessible-record listings for an external user return only identifiers of records covered by live (unexpired) rules; resolved listings of projects and documents also skip targets that no longer exist, and projects that were archived. _(prt-b-18; observed)_
- External users may edit only their own name, language, timezone and email opt-in. They cannot change status or email address; address changes must go through a new invitation so the new address is verified. _(prt-b-19; observed)_
- Link emails are written in the recipient's language with regional fallback to the base language and then English, come in an invitation variant and a sign-in variant, greet by name when known, state the validity in whole hours rounded up (at least 1), name the workspace company as sender only when the workspace uses its own branding, and escape any name or sender text so it cannot inject markup. Sending never raises; outcomes are sent, failed or mail not configured. _(prt-b-20; observed)_
- Link destination: the address in the link always targets a landing that can redeem it. The landing depends on role: roles of parties who receive payments (for example contractor-type and supplier-type roles) open on a payments area, all other roles (and unknown or missing roles) on the general home. The administrator-chosen destination, when non-blank after trimming, overrides the role default for where the person goes after sign-in, and a padded destination is trimmed. The token is URL-encoded in the link. _(prt-b-21; observed)_
- Administrator screen behavior: statuses are shown with distinct semantic emphasis (invited informational, active positive, suspended negative, lapsed neutral); a suspended user shows a reinstate action while every other user shows a suspend action; resend is always offered; after resend or invite a banner shows the one-time link with a copy action, the expiry and the post-sign-in destination; notifications distinguish emailed, mail not configured (copy instead) and mail failed (copy instead); a failed data load shows an error state with retry instead of the empty state; audit rows resolve user addresses where known and link document identifiers to their records where a destination exists; after suspend or reinstate the panel closes and the list refreshes; the Escape key closes the detail panel. _(prt-b-22; observed)_
- External-user sign-in link request form: submit is disabled until the entry looks like an address; the address is trimmed before sending; on acceptance the form shows a non-committal confirmation that does not say whether the address has access; on a refusal or failure it shows a retry-later message. _(prt-b-23; observed)_

## Inputs

- Invitation input: valid email address (whitespace stripped), external role (one of a small fixed set of external-party kinds), optional full name up to 255 characters, language 2 to 10 characters default English, timezone up to 64 characters default UTC, optional destination up to 512 characters, send-email flag default true. _(prt-i-01; observed)_
- Partial user update input: optional status (invited, active, suspended, expired), optional name up to 255, language 2 to 10, timezone up to 64, optional email opt-in. _(prt-i-02; observed)_
- Link redemption input: a credential string of 16 to 256 characters. Self-service request input: a valid email address. _(prt-i-03; observed)_
- Document access event input: record kind (1 to 64 characters), record identifier (unique identifier), action (view, download or sign; default view). Access rule input: external user identifier, record kind (1 to 64 characters), record identifier, level (view, comment, submit, sign; default view), optional expiry timestamp. _(prt-i-04; observed)_

## Outputs

- Invitation and re-send responses return the user record, the one-time plaintext link credential, the link expiry, and the email outcome (sent, failed, not configured, not requested). Invitation answers with a created status; re-send answers with a success status. _(prt-o-01; observed)_
- Self-service link request always returns an accepted status with a fixed body (an acceptance indicator plus a generic message that says a link is sent only if the address is registered). The credential never appears in the body. _(prt-o-02; observed)_
- Redemption response: session credential, session expiry, the user profile and the optional stored destination. _(prt-o-03; observed)_
- Administrator lists of users and rules return a page of items plus a total count; the access log returns a plain sequence of entries. Revoking a rule and signing out return no content. _(prt-o-04; observed)_

## States and transitions

- Account status: new invitation creates invited; first successful link redemption moves invited to active; administrator suspension moves any status to suspended and revokes live sessions; administrator reinstatement moves to active; a repeat invitation moves lapsed back to invited and leaves invited, active and suspended unchanged; the administrator may also set lapsed or invited directly. _(prt-t-01; observed)_
- Login link lifecycle: issued, then either redeemed once (terminal), expired by clock after 24 hours (terminal), or ended early when a newer self-service link is issued to the same account. An invitation or re-send issues a new link without ending the older unused ones. _(prt-t-02; observed)_
- Session lifecycle: opened at redemption with a 7-day lifetime; ends by expiry, sign-out of that session, or bulk revocation on suspension. _(prt-t-03; observed)_

## Timing and ordering

- Link validity is 24 hours; session lifetime is 7 days; minimum gap between two self-service links for one account is 60 seconds. _(prt-d-01; observed)_
- On suspension the status change is applied before sessions are revoked, within the same request; on invitation with email the save completes before the email is attempted; self-service link work occurs after the response is sent. _(prt-d-02; observed)_
- Access log, user list and rule list are ordered newest first; resolved project and document listings are ordered by name. _(prt-d-03; observed)_

## Edge cases

- Inviting the same address twice, or with different letter case or surrounding spaces, never yields two accounts. _(prt-e-01; observed)_
- A grant whose expiry has passed is treated as absent by every check and listing; a grant with no expiry never lapses. A repeated grant can extend, shorten, remove or lower the expiry and level. _(prt-e-02; observed)_
- Rules pointing at records that no longer exist stay in storage but are silently skipped in resolved listings. _(prt-e-03; observed)_
- If no outbound mail is configured, self-service link requests mint nothing (a new link would retire the old one the administrator copied by hand and lock the person out), while administrator-driven invitations still work and report mail not configured. _(prt-e-04; observed)_
- Timestamps without a zone coming back from storage are interpreted as UTC when compared with the current time. _(prt-e-05; observed)_
- The administrator log screen falls back to the creation time when an entry has no event time; the detail panel shows at most the eight most recent entries for the user. _(prt-e-06; observed)_
- The audit view per user in the detail panel is derived from the same bounded log fetch (most recent 200 entries), so very old entries for a user may not appear there. _(prt-e-07; derived)_

## Errors

- Redemption errors: unknown credential gives unauthorized; a link of the wrong purpose, already used, or past expiry gives bad request (distinct messages); an owner that is missing, suspended or lapsed gives unauthorized. _(prt-r-01; observed)_
- Missing, malformed, revoked, expired or inactive-owner session credentials give unauthorized with a bearer challenge. _(prt-r-02; observed)_
- Self-service link requests from a client exceeding a shared per-client request limit receive a too-many-requests answer; this is the only way the request capability ever differs from the standard accepted answer. _(prt-r-03; observed)_
- Re-send for a suspended account gives conflict; unknown user gives not-found; document access event without sufficient grant gives forbidden; document download with no grant gives forbidden, missing record not-found, missing file gone. _(prt-r-04; observed)_
- Invalid role, status, action or level values, non-address emails, over-long fields and out-of-range paging values are rejected as validation errors before any state change. _(prt-r-05; observed)_

## What it must not do

- A suspended account is never sent a re-sent invitation; the administrator must reinstate first. _(prt-n-01; observed)_
- A refused or failed access event writes no log entry; viewing a missing or gone file writes no log entry; the self-service request never reveals registration status in status code, body or (by design) timing. _(prt-n-02; observed)_
- External users cannot suspend or reinstate themselves, change their own address, grant themselves access, or read the audit log or other users' data. Nothing on this surface gives an external account any internal access. _(prt-n-03; observed)_
- Download events are only recorded when the client reports them; the server-side file delivery records a view event regardless of disposition. No log entry is written for list or metadata views. _(prt-n-04; observed)_

## Security

- Link and session credentials are high-entropy random values (at least 256 bits); only a cryptographic digest is stored; comparisons are constant-time; plaintext is revealed once to the party who needs it. _(prt-x-01; observed)_
- Administrator capabilities require internal sign-in plus one of five internal permissions, each held at manager level by default: read users, invite (also covers re-send), suspend (also covers rename and reinstate), manage access rules, read audit log. External-user capabilities use a separate credential system that is independent of internal authorization. _(prt-x-02; observed)_
- Access is deny-by-default and per record: nothing is visible until a rule exists. Resource-existence oracles are avoided by returning identical answers (forbidden or not-found as noted) for ungranted existing records and nonexistent ones; project-scoped capabilities answer not-found when no grant exists. _(prt-x-03; observed)_
- Self-service link abuse protections: per-client rate limit, per-account 60 second gap, identical responses, deferred processing, no minting without mail transport, retirement of older unused links. _(prt-x-04; observed)_
- The access log stores the caller's network address and is exposed only to administrators; link redemption stores address and client descriptor on the session. These are personal data for the retention and privacy policy of the destination. _(prt-x-05; inferred)_

## Invariants

- At most one external account exists per normalized email address. _(prt-v-01; observed)_
- A login link yields at most one session, regardless of concurrency. _(prt-v-02; observed)_
- An external user can act on a record only if a live rule on that exact record, at a level at least as high as the action needs, exists; a higher level never fails a lower requirement. _(prt-v-03; observed)_
- Every logged access event corresponds to an access check that passed at logging time. _(prt-v-04; derived)_
- A suspended or lapsed account has zero usable sessions and zero redeemable links in effect. _(prt-v-05; derived)_

## Notes

- Behavior-only port into an existing application: wire shapes, paths, field names, role names and status labels are not required to match the origin. The destination keeps its own conventions and role set, but must preserve the observable semantics above, including deny-by-default, identical anti-enumeration answers and one-time reveal. Numeric parameters (link validity, session lifetime, resend gap, field length limits, paging bounds, credential size) are ordinary behavioral parameters; the destination may re-tune them through a documented decision. _(prt-m-01; derived)_
- Do not reproduce origin provenance markers. _(prt-m-02; observed)_

## Non-goals

- No implementation code is generated.
- Read-only views of business records for external users are outside this unit beyond their shared access-check semantics.
- Exact visual styling, colors, icons, layout and copy of the administrator or sign-in screens are not specified.
- Notification feed behavior and internal notification events are not specified here.
- Origin table names, field names, event names, endpoint paths and permission identifiers are intentionally not carried over.

## Test cases

- **prt-t-s01**: Given no account for an address, when an administrator invites it with mixed-case letters and surrounding spaces and a role, then an invited account exists with the address trimmed and lower-cased, language English and timezone UTC by default, and the response contains a one-time link credential expiring 24 hours later.  
  Expected: Account created in invited state; link valid 24 hours; credential only in this response; later user reads do not include it.
- **prt-t-s02**: Given an existing active account, when the same address is invited again, then no new account exists, the status stays active, and a new link is issued.  
  Expected: One account; status unchanged; fresh link returned.
- **prt-t-s03**: Given an account in the lapsed status, when it is invited again, then its status becomes invited.  
  Expected: Status invited; fresh link returned.
- **prt-t-s04**: Given an invitation with a post-sign-in destination, when the link is redeemed, then the redemption response contains that destination; when no destination was set it contains none.  
  Expected: Destination round-trips through redemption.
- **prt-t-s05**: Given an invitation requested with email sending on and no mail transport configured, then the invitation still succeeds and the email outcome says mail is not configured; with sending off the outcome says not requested.  
  Expected: Invitation never fails because of mail; outcome reported.
- **prt-t-s06**: Given an invited account, when its link is redeemed, then the account becomes active, last sign-in is set, a session valid 7 days is returned; redeeming the same link again is rejected as already used.  
  Expected: Single session; second attempt bad request.
- **prt-t-s07**: Given a link whose expiry is one minute in the past, when it is redeemed, then it is rejected as expired and the account status is unchanged.  
  Expected: Bad request; no session; no status change.
- **prt-t-s08**: Given a link of a different purpose, or an unknown credential, when redeemed as a sign-in link, then the former is a bad request and the latter unauthorized.  
  Expected: Distinct failure classes; no session.
- **prt-t-s09**: Given two simultaneous redemptions of one unused link, then exactly one succeeds and exactly one session is created.  
  Expected: One success, one already-used rejection.
- **prt-t-s10**: Given an active user with two live sessions, when an administrator suspends the user, then both sessions stop validating immediately and the user can no longer redeem links or request a new one.  
  Expected: Status suspended; all sessions revoked; sign-in blocked.
- **prt-t-s11**: Given a suspended user, when an administrator re-sends the invitation, then the request is refused with a conflict and no link is created; after reinstating (status active), re-send succeeds and returns a fresh link built from the stored role, language and name.  
  Expected: Conflict first; success after reinstatement.
- **prt-t-s12**: Given a registered and an unregistered address, when each requests a sign-in link, then both receive the same accepted answer with the same body, and the credential is in neither body.  
  Expected: Indistinguishable responses.
- **prt-t-s13**: Given a registered active account and configured mail, when two sign-in link requests arrive within 60 seconds, then only the first creates and sends a link; once 60 seconds have passed a second link is created and every earlier unused login link of that account is ended.  
  Expected: One live login link at a time; throttled second request silently does nothing.
- **prt-t-s14**: Given no mail transport, when a sign-in link is requested for a registered account, then the answer is still accepted but no link is created and the account's existing link remains redeemable.  
  Expected: No minting; existing link untouched.
- **prt-t-s15**: Given a client that exceeds the per-client request limit, when it requests another link, then it receives a too-many-requests answer; the form shows a try-again-later message.  
  Expected: Rate-limited answer and retry message.
- **prt-t-s16**: Given an external user with a live view-level rule on a document, when they report a view event, then one log entry is created with the user, document kind, document identifier, action, a server timestamp and the caller address; reporting a signing event on the same document is forbidden and logs nothing.  
  Expected: View logged; sign refused; no entry for the refusal.
- **prt-t-s17**: Given a user with no rule on a document identifier, when they request its content, then the answer is forbidden whether or not the identifier exists; given a rule but a missing record the answer is not-found; given a rule and a missing file the answer is gone and no log entry exists.  
  Expected: No existence oracle; no log entry unless the file is delivered.
- **prt-t-s18**: Given a delivered image document and a delivered archive document, then the image is served inline and the archive as an attachment, each producing a view log entry.  
  Expected: Disposition by media class; log action is view in both cases.
- **prt-t-s19**: Given log entries for several users and record kinds, when an administrator filters by user, then only that user's entries are returned newest first; with a limit of 2 and offset 2 the third and fourth newest are returned; a limit above 500 is rejected.  
  Expected: Filtered, ordered, paged output; invalid limit is a validation error.
- **prt-t-s20**: Given a rule with an expiry in the past, when access is checked or accessible records are listed, then the rule counts as absent; a rule with no expiry is always live; granting again with a future expiry restores access.  
  Expected: Expired rule denies; re-grant restores.
- **prt-t-s21**: Given a rule at comment level, then view and comment requirements pass and submit and sign requirements fail; a rule at sign level passes all four.  
  Expected: Ordered level satisfaction.
- **prt-t-s22**: Given an administrator below manager level, when any administrator capability is used, then it is refused; a manager passes every one of the five permission checks by default.  
  Expected: Forbidden below manager level.
- **prt-t-s23**: Given an external user, when they try to change their own status or address through the self-edit, then those fields are not accepted and unchanged; name, language, timezone and opt-in are updated.  
  Expected: Only four fields editable.
- **prt-t-s24**: Given a payment-receiving external role, other external roles, an unknown role, a blank role and a missing role, then the landing is the payments area for the first and the general home for all others; an explicit destination of two spaces is ignored while a padded real destination is trimmed and wins; a token with spaces and symbols is URL-encoded in the link.  
  Expected: Role defaults and override rules hold; link always targets a redemption-capable landing.
- **prt-t-s25**: Given the administrator screen with a user whose status is suspended and one whose status is active, then the suspended user's panel offers reinstate and the active user's panel offers suspend, both offer re-send; a failed user-list load shows an error with retry rather than an empty state.  
  Expected: Action set depends on status; errors distinct from empty.
- **prt-t-s26**: Given a link email for a recipient with a regional language not available, then the base language is used, falling back to English; with an unnamed recipient a generic greeting is used; with default branding no company name is used as sender; the validity shown is the hours until expiry rounded up and never below one.  
  Expected: Localization and fallback rules hold; markup in names is escaped.

## Open questions (decisions for QC Manager)

- What, if anything, should move an account to the lapsed status automatically (for example a scheduled job)? No automatic trigger was determined.
- Should the destination track failed sign-in attempts for external accounts and apply a temporary lockout? The origin's user record suggested such a concept but no enforcement behavior was determined; treat as an open design decision, not a requirement.
- Invitation of a suspended account issues a link that cannot be redeemed; is that the intended outcome, since only re-send is blocked?
- Should invitations also retire earlier unused links, as the self-service request does? Only the self-service path was observed doing so.
- Should the destination record download events server-side? In the origin, file delivery always logs a view and downloads are logged only if the client reports them.
- Retention and privacy treatment of stored network addresses in the access log and sessions is not specified by the source.
- Should the destination allow a session credential on a secondary channel (such as a query parameter) for one media-delivery path whose client cannot set headers? The origin did so; the exposure trade-off is a destination decision.
