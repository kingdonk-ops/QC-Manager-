# 07. Punch verification rule

Spec `spec-punch-verifier-001` · compatibility: behavior-compatible · leakage review: passed

## Summary

Close-out of a snag (punch) item runs through resolve, verify and close. Under the default deployment policy the person who verifies a rectified item must be a different person from the one who recorded it as resolved, and verification is only possible from the resolved state. A deployment-level switch can relax this to permission-only verification for small teams. Verify and close need an elevated permission on top of ordinary edit rights, bulk close can only close items that were already verified, and imported BCF status changes cannot perform verification. NCR close-out is a separate flow that has no equivalent separation-of-duties check; whether to add one is a decision point.

## Behaviour

- A punch item moves through the lifecycle open, assigned, in progress, resolved, verified, closed. Allowed forward moves: open to assigned or in progress; assigned to in progress; in progress to resolved; resolved to verified; verified to closed. Allowed backward moves: assigned to open; in progress to assigned or open; resolved to open; verified to open; closed to open. Any other requested move is refused with a client-error result that names the current and requested states. _(pv-beh-001; observed)_
- Reopening to the open state is accepted from every state. A client-facing alias meaning reopened is treated identically to open. Reopening from verified or closed appends an entry to the item's reopen history containing time, acting user, the previous state and the reason when a note was supplied. Any supplied note on a transition is stored as the item's resolution note. _(pv-beh-002; observed)_
- When an item is moved to resolved, the system records the acting user as the resolver and stamps a resolved time. This record is made even when the item has no assignee, so the later separation-of-duties comparison never depends on the assignee field. _(pv-beh-003; observed)_
- Under the default policy, verifying an item requires that the item is currently in the resolved state and that the verifying user is not the recorded resolver. If the item is not resolved (including an item still in progress), the move is refused with a client-error result whose message tells the user to mark the item resolved first because verification is done by a different person. If the verifier is the recorded resolver, the move is refused with a client-error message stating that verification must be done by a different user than the resolver. The two refusal messages are distinguishable from each other. In both refusals the item's state is unchanged. _(pv-beh-004; observed)_
- A successful verification stamps the verification time and records the verifying user on the item; both are later shown on the item (with the verifier's readable name when it can be resolved) and the move is written to the audit trail with actor, previous state, new state and note, and announced as a status-change notification. _(pv-beh-005; observed)_
- A deployment-level policy selects how verification works. The default mode is different-person (described above). The alternative permission-only mode removes the resolver comparison and the resolved-first requirement: anyone holding the verify permission may verify, including the person who resolved the item, and an item may be verified directly from in progress. Closing still requires a verified item under both modes. The setting is intended for small site teams with a single supervisor. _(pv-beh-006; observed)_
- Moves to verified and to closed both require an elevated permission (held by a higher-ranked role tier by default; the destination maps it to its own role model) in addition to the ordinary edit permission; this check happens before any lifecycle logic runs, so a user lacking it is denied regardless of item state. _(pv-beh-007; observed)_
- Bulk close takes a project and a list of item references plus an optional comment and requires the same elevated permission. It closes only items that are verified. Items already closed are counted as skipped. Items in any earlier state are reported as not verified and keep their state, so bulk close cannot bypass verification. Items that do not exist or belong to a different project are reported as errors. A critical-priority item is reported as blocked, with the number of other open critical items, when other critical items in the project are not yet verified or closed. The result lists counts of closed and skipped items and a list of per-item errors, and each success is announced as a status change flagged as bulk. _(pv-beh-008; observed)_
- Closing a single critical-priority item is refused while other critical items in the same project are neither verified nor closed; the refusal message states how many remain. _(pv-beh-009; observed)_
- In the item detail view a close-out stepper shows the six stages in order, highlights the current stage and offers only the moves the backend accepts under the default policy: forward moves as primary actions and reopen or unassign as secondary actions. The direct in-progress-to-verified move is never offered even though the permission-only policy accepts it. A short hint that verification must be done by a different user than the one who resolved the item is shown whenever verify is offered or the item is resolved. An optional note field rides along with the next move and is cleared whenever the item's state changes. _(pv-beh-010; observed)_
- When punch items are exchanged through BCF import, a topic status of open, assigned, in progress or resolved is applied directly to the item, while a topic status of verified or closed is not applied; instead the import reports a warning telling the user to verify or close the item in the application, because verification is a different-person act that a file cannot perform. _(pv-beh-011; observed)_
- NCR close-out is a separate lifecycle (identified, under review, corrective action, verification, closed, plus void) in which closing requires the verification state and a recorded corrective action. If no verifier is recorded when closing by a status edit, the acting user is recorded as verifier; the close operation can also take an explicit verifier. A missing verifier on a closed NCR is a non-blocking warning only. No rule compares the verifier with the person who performed the corrective work; whether such a rule is wanted is listed as a decision point and is not a requirement of this spec. _(pv-beh-012; observed)_
- Enforcement of the different-person rule: it is applied in the business-logic layer at the moment of the move to verified, as one shared decision that returns one of three answers (may verify, refused because the item was never resolved, refused because the verifier is the resolver). The decision compares the acting user with the resolver recorded on the item at resolve time, never with the assignee. It is not enforced by the interface (which only shows a hint), not by the permission layer (which only checks the elevated verify permission), and cannot be skipped by a bulk close (which closes only already verified items) or by a BCF import (which cannot set verified). The only way to bypass it is the deployment-wide permission-only policy. Generic item edits carry no status field, so verification can only be reached through the transition operation. _(pv-beh-013; derived)_
- Behavior on reopen: a move to open (or the reopened alias) is allowed from every state, stores any note as the resolution note, and from verified or closed adds a reopen-history entry (time, actor, previous state, reason). It does not clear the stored resolver, resolved time, verifier or verified time. After a reopen the item must pass through in progress again (open to in progress, or open to assigned then in progress) and be marked resolved again, which overwrites the resolver with the new acting user, before a different-person verification is possible; verifying straight from open is refused as not resolved. A reopen from a state other than verified or closed (for example resolved to open) adds no history entry. Reopening is not restricted by the elevated permission. _(pv-beh-014; observed)_
- Who counts as resolver after reassignment: the resolver is whichever user performed the move to resolved, independent of the assignee. Changing the assignee, by an edit or by moving the item to assigned, never changes the recorded resolver. Consequences: (a) if the item is reassigned after being resolved, the original resolver stays barred from verifying and the new assignee is not barred; (b) the new assignee is only the resolver if they themselves perform the resolve move; (c) if the item is moved back to in progress or open and resolved again by someone else, the newest resolver replaces the earlier one, so the earlier resolver is then free to verify; (d) the move to resolved is not restricted to the assignee, any user with edit rights may perform it (whether to restrict it is a decision point). An item resolved through a path that records no resolver has no one barred (see decision points). _(pv-beh-015; derived)_

## Inputs

- Status transition input: target state, optional free-text note, identity of the acting user, and (for the permission check) the acting user's permissions. The reopened alias is accepted in place of open. _(pv-in-001; observed)_
- Bulk close input: project reference, list of item references, optional comment; acting user identity. _(pv-in-002; observed)_
- Deployment policy input: a two-valued setting, different-person (default) or permission-only, supplied through deployment configuration rather than per project. _(pv-in-003; observed)_

## Outputs

- A successful transition returns the updated item including state, resolved time, verified time, verifier identity, verifier readable name, resolution note and reopen history. _(pv-out-001; observed)_
- Bulk close returns an object with a count of closed items, a count of skipped items and an ordered list of per-item errors each carrying the item reference and a short reason (not found, belongs to another project, not verified, critical blocked with count of other open critical items, or a refusal message). _(pv-out-002; observed)_

## States and transitions

- Resolved to verified: allowed only to a verification-permitted actor and, under the default policy, only when the actor differs from the recorded resolver. Effects: verified time and verifier recorded, audit entry, notification. _(pv-st-001; observed)_
- In progress to verified: refused under the default policy; allowed under permission-only policy. _(pv-st-002; observed)_
- Verified to closed: allowed only with the elevated permission, and for critical items only when no other critical item in the project is still short of verified. _(pv-st-003; observed)_
- Any state to open (reopen): always allowed; from verified or closed it adds a reopen-history entry. It does not alter the stored resolver, verifier or their times. _(pv-st-004; derived)_

## Timing and ordering

- Ordering inside a single transition: elevated-permission check first, then reopen shortcut, then allowed-graph check, then resolver and verifier checks, then critical-close check, then persistence, audit entry and notification. The notification is best-effort and its failure never blocks the transition. _(pv-time-001; derived)_

## Edge cases

- Edge condition: an item is in the resolved state but no resolver is recorded (for example it reached resolved through a file import or a bulk data load rather than through a transition). The different-person comparison then has nothing to compare against. The outcome of verification in this situation is a destination decision (see decision points) and must be defined and tested explicitly rather than left to chance. _(pv-edge-001; derived)_
- An item without an assignee can still be resolved and then protected by the separation rule, because the resolver is the acting user and not the assignee. _(pv-edge-002; observed)_
- If an item is reopened and resolved again by a different person, the resolver record is overwritten with the newest resolver; the earlier resolver is no longer the one excluded from verifying. _(pv-edge-003; derived)_
- In bulk close, one item's failure never stops processing of the others; each item is evaluated independently in the order supplied, unexpected failures are reported as an error entry for that item only. _(pv-edge-004; observed)_

## Errors

- Unknown item: not-found result. Move not in the allowed graph: client-error result naming both states. Verification by the resolver: client-error result. Verification of an item that is not resolved under the default policy: client-error result telling the user to resolve first. Close of a critical item with other unresolved critical items: client-error result with the count. Missing elevated permission for verify or close: permission-denied result. _(pv-err-001; observed)_

## What it must not do

- Bulk close never verifies and never closes an item that is not already verified. A BCF import never sets an item to verified or closed. The stepper never offers a move the backend would refuse under the default policy. _(pv-neg-001; observed)_

## Security

- Separation of duties: under the default policy the same person cannot both resolve and verify an item, and a missing assignee cannot disable the rule. Access to the item's project is checked before any transition. Bulk close checks the same elevated permission as single verify and close so it cannot be used to bypass it, and rejects item references from other projects as errors. _(pv-sec-001; observed)_

## Invariants

- Under the default policy, for every item that reached verified through a transition, the verifier differs from the user recorded as resolver at the time of verification. _(pv-inv-001; derived)_
- An item can only be closed from verified, under either policy, whether closed singly or in bulk. _(pv-inv-002; observed)_

## Notes

- Equal-output expectation: refusal results for same-person and not-yet-resolved verification are client errors with distinguishable messages; bulk close output keeps the closed, skipped and errors structure with per-item reasons; reopen history entries keep time, actor, previous state and optional reason. The BCF format is a public open standard and may be referenced by name. _(pv-comp-001; observed)_

## Non-goals

- Photo evidence capture, export formats and location pinning on punch items are out of scope for this unit.
- No implementation code or storage layout is specified.
- NCR separation of duties is not invented; only the absence is recorded.
- Do not reproduce origin provenance markers.

## Test cases

- **pv-test-001**: Given the default policy and an item in progress, when user Alice marks it resolved and then tries to verify it herself, then the second move is refused.  
  Expected: Client-error result stating verification must be done by a different user than the resolver; item remains resolved.
- **pv-test-002**: Given the default policy and an item resolved by Alice, when Bob (holding the verify permission) verifies it, then it succeeds.  
  Expected: Item is verified; verifier is Bob; verification time is set; an audit entry and notification are produced.
- **pv-test-003**: Given the default policy and an item that is in progress and was never resolved, when any verifier tries to verify it directly, then it is refused.  
  Expected: Client-error result telling the user to mark the item resolved first; state stays in progress.
- **pv-test-004**: Given the permission-only policy and an item in progress, when supervisor Carol resolves it and then verifies it herself, then both moves succeed.  
  Expected: Item ends verified with Carol as verifier.
- **pv-test-005**: Given the permission-only policy and an item in progress that was never resolved, when a verifier verifies it directly, then it is accepted.  
  Expected: Item becomes verified.
- **pv-test-006**: Given an item without an assignee in progress, when Dana resolves it and Dana then attempts verification under the default policy, then it is refused.  
  Expected: Refusal as for any resolver; the empty assignee does not weaken the rule.
- **pv-test-007**: Given an item that is in the resolved state with no recorded resolver (reached via import), when a verify-permitted user attempts verification under the default policy.  
  Expected: Outcome is defined by the destination's resolution of the corresponding decision point; the destination records its chosen rule (refuse, accept, or require a resolver at import) and asserts it deterministically.
- **pv-test-008**: Given a user with ordinary edit rights but not the elevated permission, when they request a move to verified or closed, then it is denied before state is examined.  
  Expected: Permission-denied result; item unchanged.
- **pv-test-009**: Given a project with one verified item, one in progress item, one resolved item, one already closed item and one item from another project, when a manager bulk-closes all five, then only the verified item is closed.  
  Expected: Closed count one, skipped count one; errors list the in-progress and resolved items as not verified and the foreign item as belonging to another project; the unverified items keep their state.
- **pv-test-010**: Given two critical items where one is verified and the other still in progress, when the verified one is closed singly or in bulk, then it is blocked.  
  Expected: Single close returns a client error with the count of remaining critical items; bulk close lists a critical-blocked reason with the count; item stays verified.
- **pv-test-011**: Given a verified item, when it is reopened with a reason by a user, then it returns to open.  
  Expected: Item is open and its reopen history gains an entry with time, actor, previous state verified and the reason.
- **pv-test-012**: Given a BCF archive containing a topic for an existing punch item whose status says verified, when it is imported, then the item's state is not changed.  
  Expected: Import reports a warning that the item must be verified or closed in the application; other topics with open, assigned, in progress or resolved status update their items.
- **pv-test-013**: Given the item detail view for an item in progress and for an item in the resolved state, when the closing stepper is shown, then it offers only accepted moves.  
  Expected: In progress: no verify action; resolved: verify action offered and the different-person hint visible; closed: only reopen.
- **pv-test-014**: Given an NCR in the verification status with a recorded corrective action and no recorded verifier, when a user closes it.  
  Expected: The NCR closes and the closing user is recorded as verifier. Separation of duties between verifier and corrective-action performer is not asserted here; it is a pending decision point.
- **pv-test-015**: Given the default policy and an item resolved by Alice, when the assignee is changed to Bob and then Alice attempts verification, then Alice is refused and Bob (not the resolver) may verify.  
  Expected: Alice refused as the resolver; Bob accepted; the recorded resolver remains Alice throughout.
- **pv-test-016**: Given a verified item first resolved by Alice, when it is reopened, moved back to in progress, and resolved again by Bob, then Alice attempts verification.  
  Expected: Alice is accepted because the resolver is now Bob; Bob would be refused. The reopen produced one history entry with previous state verified.
- **pv-test-017**: Given a reopened item in the open state, when a verify-permitted user tries to verify it directly, then it is refused.  
  Expected: Client error that the item must be resolved first; state stays open.

## Open questions (decisions for QC Manager)

- Decision point: after reopen, should the reopen history also preserve who resolved and verified the item earlier, so audits can see the earlier four-eyes pair?
- Decision point: should the move to resolved be restricted to the assignee (or an administrative role), or may any user with edit rights perform it? The answer changes who can become the resolver.
- Decision point: when an item is in the resolved state but has no recorded resolver (for example after a file import or bulk data load), should the destination treat that as a refusal, as an open pass for any verify-permitted user, or require a resolver to be recorded at import time?
- Decision point: when a BCF import sets an item to resolved, should the importing user be recorded as the resolver, or should the item be left unresolved? Recording no resolver weakens the different-person rule for that item.
- Decision point: after a reopen, should the earlier verifier and verification time be cleared, or kept until the item is verified again?
- Decision point: should the destination offer the permission-only verification mode at all, and if so per deployment or per project?
- Decision point: NCR close-out has no comparison between the verifier and the person who performed the corrective work, and the verifier defaults to whoever closes. Whether to add separation of duties for NCRs is a product decision, not a compatibility requirement.
- Decision point: bulk close does not re-check the different-person rule because it only closes already verified items. Confirm that this is the intended boundary in the destination.
- Unknown: how generic item edits (non-transition updates) interact with state and resolver records was not established.
- Unknown: which role names map to the elevated verify permission in a destination with a different role model.
