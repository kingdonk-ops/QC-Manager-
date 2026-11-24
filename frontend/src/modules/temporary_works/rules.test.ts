import { describe, expect, it } from 'vitest'
import { messages } from './messages'
import {
  DRAFT_ITEM,
  FAMILIES,
  ITEM_STATUSES,
  MAIN_FLOW,
  ON_HOLD,
  PERM,
  PERMIT_KINDS,
  PERMIT_STATUSES,
  categoryKey,
  destinationKey,
  familyKey,
  formatClearance,
  itemActions,
  kindKey,
  nextSteps,
  permitActions,
  permitStatusKey,
  statusKey,
  stepNeedsNote,
} from './rules'

const everything = () => true
const nothing = () => false
const only =
  (...held: string[]) =>
  (p: string) =>
    held.includes(p)

describe('vocabularies', () => {
  it('has eleven item statuses with on hold outside the main flow', () => {
    expect(ITEM_STATUSES).toHaveLength(11)
    expect(MAIN_FLOW).toHaveLength(10)
    expect((MAIN_FLOW as readonly string[]).includes(ON_HOLD)).toBe(false)
  })

  it('gives every status, family, kind and permit status a message', () => {
    for (const s of ITEM_STATUSES) expect(messages[statusKey(s)]).toBeTruthy()
    for (const f of FAMILIES) expect(messages[familyKey(f)]).toBeTruthy()
    for (const k of PERMIT_KINDS) expect(messages[kindKey(k)]).toBeTruthy()
    for (const s of PERMIT_STATUSES)
      expect(messages[permitStatusKey(s)]).toBeTruthy()
    for (const c of [0, 1, 2, 3, null])
      expect(messages[categoryKey(c)]).toBeTruthy()
  })
})

describe('nextSteps', () => {
  it('defines a list for every status', () => {
    for (const s of ITEM_STATUSES)
      expect(Array.isArray(nextSteps(s, 'design_brief'))).toBe(true)
  })

  it('offers one step forward, one back and on hold from a live status', () => {
    expect(nextSteps('design_checked')).toEqual([
      'approved_to_load',
      'design_submitted',
      ON_HOLD,
    ])
  })

  it('offers only the forward step and on hold from the first status', () => {
    expect(nextSteps(DRAFT_ITEM)).toEqual(['design_brief', ON_HOLD])
  })

  it('offers only the held-from status from on hold, and nothing without one', () => {
    expect(nextSteps(ON_HOLD, 'loaded')).toEqual(['loaded'])
    expect(nextSteps(ON_HOLD, null)).toEqual([])
  })

  it('offers nothing for a removed or unknown status', () => {
    expect(nextSteps('removed')).toEqual([])
    expect(nextSteps('mystery')).toEqual([])
  })

  it('needs a note for a step back and for on hold only', () => {
    expect(stepNeedsNote('loaded', 'approved_to_load')).toBe(true)
    expect(stepNeedsNote('loaded', ON_HOLD)).toBe(true)
    expect(stepNeedsNote('loaded', 'in_use')).toBe(false)
  })
})

describe('formatClearance', () => {
  it('shows a dash when absent and the percentage otherwise', () => {
    expect(formatClearance(null)).toBe('—')
    expect(formatClearance(undefined)).toBe('—')
    expect(formatClearance('50.00')).toBe('50.00%')
  })
})

describe('permit actions', () => {
  it('offers issue, activate and close only to holders of the issue permission', () => {
    expect(permitActions('draft', only(PERM.update))).toEqual(['edit'])
    expect(permitActions('draft', only(PERM.issue))).toEqual(['issue'])
    expect(permitActions('issued', only(PERM.issue))).toEqual([
      'activate',
      'close',
    ])
    expect(permitActions('active', only(PERM.issue))).toEqual(['close'])
    expect(permitActions('issued', nothing)).toEqual([])
  })

  it('offers return to draft only with its own permission and never on a draft', () => {
    expect(permitActions('issued', only(PERM.returnToDraft))).toEqual([
      'return',
    ])
    expect(permitActions('draft', only(PERM.returnToDraft))).toEqual([])
  })

  it('offers delete only on a draft', () => {
    expect(permitActions('draft', only(PERM.delete))).toEqual(['delete'])
    expect(permitActions('issued', only(PERM.delete))).toEqual([])
  })
})

describe('item actions', () => {
  it('offers delete only while in draft', () => {
    expect(itemActions(DRAFT_ITEM, null, only(PERM.delete))).toEqual(['delete'])
    expect(itemActions('loaded', null, only(PERM.delete))).toEqual([])
  })

  it('offers return to draft only with its own permission and never in draft', () => {
    expect(itemActions('loaded', null, only(PERM.returnToDraft))).toEqual([
      'return',
    ])
    expect(itemActions('loaded', null, only(PERM.update))).toEqual(['edit'])
    expect(itemActions(DRAFT_ITEM, null, only(PERM.returnToDraft))).toEqual([])
  })

  it('offers a transition only when a next step exists', () => {
    expect(itemActions('removed', null, everything)).not.toContain(
      'transition'
    )
    expect(itemActions('loaded', null, everything)).toContain('transition')
  })
})

describe('destinationKey', () => {
  it('tells the recycle bin from the Deleted folder', () => {
    expect(destinationKey('bin')).toBe('temporary_works.deleted_to_bin')
    expect(destinationKey('folder')).toBe('temporary_works.deleted_to_folder')
  })
})
