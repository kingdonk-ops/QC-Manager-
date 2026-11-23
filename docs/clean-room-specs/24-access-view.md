# 24. Effective access ("who sees what")

Spec `spec-access-view-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

A person's effective authority is resolved from a single role held on the account: roles form an ordered ladder, every action has a minimum role, the top role passes every check, and any action not known to the registry is denied to everyone below the top role. The current-user profile returns the flat list of actions the role allows. Administrators manage accounts (list, read, create, change role or active state, erase) with guards that protect administrator accounts and the last active administrator, may set per-user feature-area visibility and access levels, and can edit each action's minimum role through a permissions matrix and role presets. Programmatic keys can only narrow, never widen, their owner's authority. A governance page hosts the permissions matrix beside other governance sections and shows summary counts. A single per-record effective-access report for internal users was not determined to exist; the closest observed views are the permissions matrix, the per-user feature-area access view and the external-user access rule listing.

## Behaviour

- Role ladder (lowest to highest): viewer, editor, manager, administrator. One or more additional low-trust roles are ranked below the viewer rung and, by explicit design, hold no permissions yet: every check for them returns denied. A viewer-equivalent role may share the viewer rank. _(acv-b-01; observed)_
- Industry-specific or legacy role titles may resolve to a canonical ladder role through an alias table (some resolve to editor, some to administrator, some to viewer). Matching ignores letter case and surrounding spaces. A role string that is blank, missing or unrecognized resolves to nothing and is denied every action and receives an empty permission list. _(acv-b-02; observed)_
- Each registered action has exactly one minimum role. A role may perform an action when its rank is at least the rank of the action's minimum role (roles inherit everything below them). The administrator role always passes, even for actions not registered. _(acv-b-03; observed)_
- An action that is not in the registry is denied to every non-administrator (deny by default) and the denial is recorded as a warning for operators. _(acv-b-04; observed)_
- The per-role effective permission list is every registered action whose minimum rank is at or below the role's rank; for administrator it is every registered action; for an unresolvable role it is empty. The current-user profile returns this list computed from the account's stored role at request time, so a role change shows on the next profile read. _(acv-b-05; observed)_
- Feature areas contribute their actions, each with a minimum role, in groups. Contributing a group again replaces that area's list. Withdrawing a feature area while the system runs forgets its actions, except that an action also contributed by another area is kept, so the other area's checks do not fall into deny-by-default. Applies only if the destination supports dynamic contribution and withdrawal of feature areas. _(acv-b-06; observed)_
- Minimum roles can be edited only for actions already in the registry; editing returns the previous minimum so the change can be audited, and an attempt on an unknown action fails rather than creating it. A copy (snapshot) of the whole action-to-minimum map can be taken for comparison with a preset or baseline without changing live data. _(acv-b-07; observed)_
- Three role presets compute a minimum role for every registered action from the kind of operation the action represents, so new feature areas are covered automatically. The viewer-oriented preset gives viewer to read, list, view and export operations, manager to delete operations, administrator to system operations, editor to the rest. The editor-oriented preset gives viewer to read-like operations, manager to delete, approve and reject operations, administrator to system operations, editor to the rest. The manager-oriented preset gives viewer to read-like operations, editor to create, update and import operations, administrator to system operations, manager to the rest. _(acv-b-08; observed)_
- Core defaults: reading system settings and viewing audit records is manager level; changing settings, managing installed extensions and deleting or redacting audit records is administrator level; read-only catalog listings (installed extensions, validation catalogs) are viewer level. _(acv-b-09; observed)_
- User management minimums by default: listing and reading accounts is manager level; creating, updating and deleting accounts is administrator level; managing one's own programmatic keys is editor level. _(acv-b-10; observed)_
- Administrator account guard: only an administrator may create, edit, promote, erase or change feature-area access of an administrator account, even if lower roles were granted the account-management actions in the matrix. This stops a manager promoting themselves. _(acv-b-11; observed)_
- Administrators can create accounts with a role from a fixed whitelist of assignable roles (the four ladder roles plus one domain-specific editor-equivalent role), an active flag (default active) and a strong password of at least 12 characters; other role values are rejected before reaching storage. A role update accepts the same whitelist. Account list supports offset at least 0, limit 1 to 500 default 50, and an optional active filter. _(acv-b-12; observed)_
- The last active administrator cannot be demoted, deactivated or erased (conflict, with a message indicating another person must be promoted first). An administrator cannot erase themselves through the admin path (bad request; own deletion goes through a self-service path with password confirmation); erasing an already-erased or unknown account is not-found. _(acv-b-13; observed)_
- Changing an account's role records an audit entry with the old and new role and the affected account; recording is best-effort and its failure does not fail the change. Administrator erasure records an entry naming the actor and target without personal data, and notifies other parts of the system that an erasure occurred. Erasure anonymizes the account in place so history still resolves, strips personal fields, invalidates the password, revokes keys and blocks sign-in. _(acv-b-14; observed)_
- In demonstration mode, account reads and the echo of updates are redacted: names blanked and the address local part replaced with a hash, leaving the domain, except the caller's own row, so single reads do not bypass the list's privacy. _(acv-b-15; observed)_
- Per-user feature-area access: for each feature area an administrator stores a visible flag and an access level (none, view, edit, full; default edit), plus an optional custom role label. Writing replaces the whole feature-area map, mirrors each visible flag into the user's own navigation visibility preference, enables in any feature-gating mechanism the destination has every area that is visible and not none, and updates the custom label only when one is supplied. Reading is manager level; writing is administrator level with the administrator-account guard. _(acv-b-16; observed)_
- Programmatic keys carry scopes that are action names. Scopes only narrow what the owner's role already allows; an empty scope list keeps the owner's full authority. A catalogue of selectable scopes is generated from the registry, with each scope's minimum role. Creation validates scopes, expiry, name uniqueness among the owner's live keys and a cap on live keys, and returns the full key once. Rotation issues a replacement with the same name, scopes and limits, leaves the old key valid for 24 hours (or until its earlier expiry), is not-found when the key is not the caller's, and conflicts when the key is inactive or already rotated. _(acv-b-17; observed)_
- Governance page: three sections, the permissions section first by default. The active section is carried in the address query so sections are deep-linkable and each switch is a history entry; an unknown or missing value shows the permissions section; sections support keyboard navigation in the standard tab pattern. A persistent band links to related administration areas. _(acv-b-18; observed)_
- Governance summary tiles (roles, active approval routes, validation rule sets with a total rule count) are clickable shortcuts into their sections, share cached data with the section pages, and show distinct loading, failed and not-available states (failed is announced as an alert and is never shown as a dash that reads as zero). The role-count tile only requests data when the viewer holds the audit-viewing level permission (manager and above); below that it shows not-available. _(acv-b-19; observed)_
- The administrator-facing view of which external user can see or act on which record is the external-access rule listing (user, record kind, record identifier, level, grant time, granter, expiry), filterable by user and record kind and visible at manager level; it is specified in the companion external-access unit. _(acv-b-20; derived)_

## Inputs

- Resolution inputs are a role string (possibly an alias or in any letter case), an action name, and the registry's current minimum-role map. Matrix edit input is an existing action name and a target minimum role. _(acv-i-01; observed)_
- Per-user feature-area access input: map of feature-area identifier to visible flag and access level (none, view, edit, full), optional custom role label. _(acv-i-02; observed)_
- Admin account inputs: create (address, strong password of at least 12 characters, role from the whitelist, active flag); update (optional role from the same whitelist, optional active flag and profile fields). _(acv-i-03; observed)_

## Outputs

- Current-user profile output includes the ordinary profile plus a flat list of permitted actions for the account's role. _(acv-o-01; observed)_
- Registry outputs: all actions with minimum role sorted by name, actions grouped by feature area, a role's permitted action list, the minimum role of one action or nothing, and a defensive copy snapshot. _(acv-o-02; observed)_
- Feature-area access output: map with visible flag and access level for each feature area, and the custom role label or none. _(acv-o-03; observed)_

## States and transitions

- An account's role changes only through the admin update (or create); after the change, the effective permission list changes at the next evaluation with no extra step. Registry minimums change through matrix edits or preset application and take effect immediately for every account of the affected roles. _(acv-t-01; derived)_
- Account lifecycle through admin operations: active to deactivated by update; any account to anonymized-and-blocked by erase (terminal). Deactivation and demotion of the sole active administrator are blocked. _(acv-t-02; observed)_

## Timing and ordering

- Permission checks read the role stored on the account and the registry at evaluation time; neither is cached in the issued session in this behavior area, so role and matrix changes take effect on the next evaluation. Whether the request-authentication layer caches roles in credentials was not determined. _(acv-d-01; inferred)_
- Registry list outputs are sorted by action name. Ordering of a role's permitted list is not required to match any particular sequence. _(acv-d-02; observed)_
- Summary tile data caches: the roles tile is considered fresh for about a minute, approval routes for about thirty seconds, rule sets for about five minutes; the roles request is not retried after failure. These are ordinary tuning parameters the destination may re-tune. _(acv-d-03; observed)_

## Edge cases

- A role not in the ladder yet carrying a known alias is resolved through the alias first; a role string with unusual casing or padding resolves identically. _(acv-e-01; observed)_
- An action whose configured minimum role is not recognized as part of the ladder is unsatisfiable for non-administrators. _(acv-e-02; derived)_
- Low-trust roles ranked below viewer never pass any action, including read actions, until their surface actually registers actions for them. _(acv-e-03; observed)_
- Preset results are recomputed from the current registry each time, so newly registered actions appear in the comparison against a baseline. _(acv-e-04; derived)_
- Feature-area access with an area set invisible but non-none, or visible with none, behaves per the stated rule: only entries both visible and not none are switched on in gating. _(acv-e-05; derived)_

## Errors

- Account management by a caller below the required level is refused as forbidden; an administrator-target operation by a non-administrator is forbidden with a message that only administrators manage administrator accounts. _(acv-r-01; observed)_
- Role names outside the whitelist, weak or short passwords and bad addresses on admin create produce a validation error (unprocessable) before any storage work. _(acv-r-02; observed)_
- Matrix edit of an unregistered action fails with a not-found style error and creates nothing. _(acv-r-03; observed)_
- Unknown or already-erased account on update or erase gives not-found; sole active administrator gives conflict; self-erase through admin path gives bad request; key operations give not-found for another owner's key and conflict for inactive or already-rotated keys. _(acv-r-04; observed)_
- A failure to load a governance summary tile shows a visible failed state with an alert announcement for that tile only, without affecting the other tiles or the sections. _(acv-r-05; observed)_

## What it must not do

- Lower roles never inherit anything from higher roles; the administrator bypass is the only exception to the minimum-role comparison. _(acv-n-01; observed)_
- A programmatic key can never exceed its owner's role; scopes cannot grant anything the role lacks. _(acv-n-02; observed)_
- The matrix cannot invent actions; the admin UI path never silently creates a permission. _(acv-n-03; observed)_

## Security

- Deny-by-default for unknown actions and unresolvable roles; low-trust roles are held below viewer so a missing-rank fallback can never promote them. _(acv-x-01; observed)_
- Privilege-escalation guard: administrator accounts can be touched only by administrators; role changes are audited with before and after; the last active administrator is protected; keys only narrow. _(acv-x-02; observed)_
- Reading the permissions matrix data and viewing role counts is gated at the audit-viewing (manager) level; the interface avoids sending a request it knows will be refused. _(acv-x-03; observed)_
- Demonstration-mode redaction of personal data applies to list, single read and update echo, except for the caller's own record. _(acv-x-04; observed)_
- Administrator erase and own-erase do not leave identifiers recoverable from the account row, while preserving referential history; keys are revoked. _(acv-x-05; observed)_

## Invariants

- Authority is monotonic in the role ladder: any action permitted to a role is permitted to every higher role. _(acv-v-01; derived)_
- The per-role permitted list always agrees with the single-action check for the same role and registry state. _(acv-v-02; derived)_
- At least one active administrator exists after any admin operation. _(acv-v-03; observed)_
- Every alias resolves to a canonical role, never to another alias. _(acv-v-04; observed)_
- Withdrawing a feature area never removes an action still contributed by another area. _(acv-v-05; observed)_

## Notes

- Behavior-only port into an existing application that already has its own role model: the destination should map these observable rules onto its own roles and permission checks rather than adopt the origin's names. The assignable-role whitelist, the alias table, rank values, action names and preset tables are origin specifics, kept only if the destination has no equivalent. Numeric parameters (minimum password length, paging bounds, key overlap window, cache freshness) are ordinary behavioral parameters the destination may re-tune. _(acv-m-01; derived)_
- Do not reproduce origin provenance markers. _(acv-m-02; observed)_

## Non-goals

- No implementation code is generated.
- Authentication, sign-in, session, password reset, registration and profile preference flows are outside this unit.
- Approval routes and validation rule sets hosted in the governance page are separate units and are not specified here.
- The permissions matrix grid component, the request-authentication layer and key rule validators were not analyzed and are not specified here.
- Visual styling, colors, icons and layout are not specified.
- Origin action names, role names, feature-area identifiers, endpoint paths and storage field names are not carried over.

## Test cases

- **acv-t-s01**: Given an action whose minimum role is manager, when checked for viewer, editor, manager and administrator, then only manager and administrator pass.  
  Expected: Rank comparison with inheritance upward.
- **acv-t-s02**: Given an action absent from the registry, when checked for administrator and for manager, then administrator passes and manager is denied.  
  Expected: Administrator bypass; deny by default for others.
- **acv-t-s03**: Given role strings that are aliases of editor, of viewer and of administrator, written with mixed case and padding, then they resolve to editor, viewer and administrator respectively, and an alias never resolves to another alias.  
  Expected: Alias resolution case-insensitive and trimmed.
- **acv-t-s04**: Given a blank role, a missing role and an unrecognized role, when any action is checked, then all are denied and each permitted list is empty.  
  Expected: No resolution means no authority.
- **acv-t-s05**: Given each low-trust role ranked below viewer and a registry with read actions, then none of them passes even a read action.  
  Expected: Denied for all low-trust roles.
- **acv-t-s06**: Given an account whose role is editor, when the current-user profile is read, then the permission list equals exactly the registered actions with minimum viewer or editor; after an administrator changes the role to manager the next profile read shows the larger list.  
  Expected: List computed from current role and registry.
- **acv-t-s07**: Given two feature areas that both contribute one shared action, when one area is withdrawn, then the shared action remains with its minimum role; an action only the withdrawn area contributed disappears from the matrix and is thereafter denied to non-administrators.  
  Expected: Shared actions survive withdrawal.
- **acv-t-s08**: Given the matrix is edited for an existing action, then the previous minimum is returned and checks reflect the new minimum immediately; editing an unknown action fails and the registry is unchanged.  
  Expected: Edit-only semantics with audit delta.
- **acv-t-s09**: Given actions of the kinds system, delete, approve, read, list, view, export, create, update, import and other, when each preset is applied to compute minimums, then the results follow the three preset tables with administrator for system actions in all three.  
  Expected: Preset outputs match the stated per-kind rules.
- **acv-t-s10**: Given a manager holding account-update rights because the matrix was lowered, when they try to promote themselves or edit, create, erase or change feature-area access of an administrator, then each attempt is forbidden.  
  Expected: Only administrators manage administrators.
- **acv-t-s11**: Given exactly one active administrator, when that account is demoted, deactivated or erased by another administrator path, then the operation is refused with a conflict; after a second active administrator exists the same operation succeeds.  
  Expected: Last-admin protection.
- **acv-t-s12**: Given an administrator erasing their own account through the admin path, then the request is a bad request; erasing an unknown account is not-found; erasing another account anonymizes it, blocks sign-in and revokes its keys while records that referenced it still resolve.  
  Expected: Self-erase refused; erase is anonymizing and terminal.
- **acv-t-s13**: Given a role change from editor to manager, then an audit entry exists with before and after roles; if audit storage fails the change still succeeds.  
  Expected: Audited, best-effort recording.
- **acv-t-s14**: Given admin create with a role outside the whitelist, with a password shorter than 12 characters, or with a malformed address, then each is rejected as invalid before any account exists.  
  Expected: Validation error, no side effects.
- **acv-t-s15**: Given the account list with limit 500 versus 501 and an active filter, then 500 is accepted and 501 rejected; the filter returns only matching accounts.  
  Expected: Paging bounds and filter hold.
- **acv-t-s16**: Given demonstration mode on, when an administrator reads the list, a single account and an update echo, then names are blank and address local parts hashed for other people's accounts, while the caller's own row is unredacted.  
  Expected: Redaction on all three read paths except own row.
- **acv-t-s17**: Given feature-area access written with one area visible at edit, one visible at none, one hidden at view, then the user's navigation visibility mirrors the visible flags, only the first is switched on in gating, and the whole prior map is replaced; omitting the custom label leaves the old label; reading returns the stored map and label.  
  Expected: Replace semantics with mirrored visibility and gating.
- **acv-t-s18**: Given a key created with an empty scope list and one created with a single scope, then the first keeps the owner's full authority and the second is limited to that scope; no scope can allow an action the owner role lacks; creation fails on an unknown scope, a past expiry, a duplicate live name, or exceeding the live-key cap.  
  Expected: Keys only narrow; creation rules enforced.
- **acv-t-s19**: Given a live key rotated once, then a replacement with the same name, scopes and limits exists and the old key stops working within 24 hours or at its earlier expiry; rotating again is a conflict, rotating someone else's key is not-found, rotating a revoked key is a conflict.  
  Expected: Rotation rules and overlap window.
- **acv-t-s20**: Given the governance page opened with an unknown section value, a missing value, and each valid value, then permissions shows for the first two and the requested section for the others; switching sections adds history entries so Back returns to the earlier section; arrow keys move between sections.  
  Expected: Deep-link and keyboard behavior.
- **acv-t-s21**: Given a viewer-level or editor-level user opening the governance page, then the role-count tile makes no request and shows not-available; for a manager the tile requests data; if that request fails the tile shows a failed state with an alert while the other two tiles still show counts.  
  Expected: Gated request and per-tile failure isolation.
- **acv-t-s22**: Given an administrator who wants to know what an external user can reach, when they list access rules filtered by that user, then every rule with record kind, record, level, grant time, granter and expiry is shown, including expired ones with their expiry.  
  Expected: Administrator can answer who can see what for external users from the rule list.

## Open questions (decisions for QC Manager)

- Is there a need for a per-record or per-project effective-access report for internal users (who can see or act on which records)? None was determined to exist in this behavior area; project membership checks are handled elsewhere in the system.
- How are key scopes combined with the owner's role at request time? Only the contract (narrow only, empty means full) was observed.
- Does request authentication re-read the role from storage on every request or trust a role claim in the credential? Inferred as re-read; not confirmed.
- Where exactly is the audit-viewing level permission enforced for the matrix data, and should the matrix UI support applying presets and previewing differences? Not determined.
- How does per-user feature-area access interact with role minimums for the same area (does access none block an action the role would allow)? Not determined.
- Should a domain-specific editor-equivalent role carry an extra action in some feature areas, and at what minimum role? Not determined.
- Should the destination import previously stored feature-area settings that used a simple yes/no shape, and if so map them to the visible flag with the default access level? Whether custom role labels count as roles in the roles summary is also undetermined.
