/**
 * Display helpers for the temporary works register: vocabularies, label keys, the next steps offered for each item
 * status and the permission each action needs. These mirror the server for display only; the server decides every
 * move, and every gate, breach, overdue or clearance figure is read from its answers, never worked out here.
 */

export const FAMILIES = [
  'falsework',
  'formwork',
  'propping',
  'excavation_support',
  'scaffold',
  'facade_retention',
  'crane_base',
  'edge_protection',
  'dewatering',
  'hoarding',
  'other',
] as const

/** The ten main-flow statuses in order; on hold is the eleventh and sits outside the flow. */
export const MAIN_FLOW = [
  'identified',
  'design_brief',
  'design_submitted',
  'design_checked',
  'approved_to_load',
  'loaded',
  'in_use',
  'approved_to_strike',
  'struck',
  'removed',
] as const

export const ON_HOLD = 'on_hold'
export const ITEM_STATUSES = [...MAIN_FLOW, ON_HOLD] as const
/** The draft state of an item: the only status it can be deleted in. */
export const DRAFT_ITEM = 'identified'

export const CATEGORIES = [0, 1, 2, 3] as const
export const PERMIT_KINDS = ['load', 'strike', 'dismantle'] as const
export const PERMIT_STATUSES = [
  'draft',
  'issued',
  'active',
  'expired',
  'closed',
] as const
export const DRAFT_PERMIT = 'draft'

export type ItemStatus = (typeof ITEM_STATUSES)[number]
export type PermitKind = (typeof PERMIT_KINDS)[number]

export const PERM = {
  read: 'temporary_works.read',
  create: 'temporary_works.create',
  update: 'temporary_works.update',
  delete: 'temporary_works.delete',
  transition: 'temporary_works.transition',
  issue: 'temporary_works.issue',
  returnToDraft: 'temporary_works.return_to_draft',
  restore: 'temporary_works.restore',
} as const

export const statusKey = (status: string) => `temporary_works.status.${status}`
export const familyKey = (family: string) => `temporary_works.family.${family}`
export const kindKey = (kind: string) => `temporary_works.kind.${kind}`
export const permitStatusKey = (status: string) =>
  `temporary_works.permit_status.${status}`
export const categoryKey = (category: number | null | undefined) =>
  category === null || category === undefined
    ? 'temporary_works.category_unassigned'
    : `temporary_works.category.${category}`

/**
 * The statuses an item can be offered from `status`: one step forward, one step back (which needs a note), and on hold
 * from any live status. From on hold only the status it was held from; a removed item goes nowhere.
 */
export function nextSteps(status: string, heldFrom?: string | null): string[] {
  if (status === ON_HOLD)
    return heldFrom && (MAIN_FLOW as readonly string[]).includes(heldFrom)
      ? [heldFrom]
      : []
  const here = (MAIN_FLOW as readonly string[]).indexOf(status)
  if (here < 0 || status === 'removed') return []
  const steps: string[] = []
  if (here + 1 < MAIN_FLOW.length) steps.push(MAIN_FLOW[here + 1])
  if (here > 0) steps.push(MAIN_FLOW[here - 1])
  return [...steps, ON_HOLD]
}

/** A step back, or going on hold, needs a note saying why. */
export function stepNeedsNote(status: string, target: string): boolean {
  if (target === ON_HOLD) return true
  const here = (MAIN_FLOW as readonly string[]).indexOf(status)
  const there = (MAIN_FLOW as readonly string[]).indexOf(target)
  return here >= 0 && there >= 0 && there < here
}

type Held = (permission: string) => boolean

export type PermitAction =
  | 'edit'
  | 'issue'
  | 'activate'
  | 'close'
  | 'return'
  | 'delete'

/** The buttons a permit offers the caller, by its status and the permissions held. */
export function permitActions(status: string, has: Held): PermitAction[] {
  const out: PermitAction[] = []
  if (status === 'draft' && has(PERM.update)) out.push('edit')
  if (status === 'draft' && has(PERM.issue)) out.push('issue')
  if (status === 'issued' && has(PERM.issue)) out.push('activate')
  if ((status === 'issued' || status === 'active') && has(PERM.issue))
    out.push('close')
  if (status !== 'draft' && has(PERM.returnToDraft)) out.push('return')
  if (status === 'draft' && has(PERM.delete)) out.push('delete')
  return out
}

export type ItemAction =
  | 'edit'
  | 'transition'
  | 'add_permit'
  | 'return'
  | 'delete'

/** The buttons an item offers the caller: return to draft needs its own permission; delete only while in draft. */
export function itemActions(
  status: string,
  heldFrom: string | null | undefined,
  has: Held
): ItemAction[] {
  const out: ItemAction[] = []
  if (has(PERM.update)) out.push('edit')
  if (has(PERM.transition) && nextSteps(status, heldFrom).length > 0)
    out.push('transition')
  if (has(PERM.create)) out.push('add_permit')
  if (status !== DRAFT_ITEM && has(PERM.returnToDraft)) out.push('return')
  if (status === DRAFT_ITEM && has(PERM.delete)) out.push('delete')
  return out
}

/** The server's clearance percentage as text, or a dash when it is absent (an empty register). */
export function formatClearance(value: string | null | undefined): string {
  return value === null || value === undefined || value === ''
    ? '—'
    : `${value}%`
}

/** Where a deleted record went, from the delete answer: the recycle bin or the Deleted folder. */
export function destinationKey(destination: string | null | undefined) {
  return destination === 'bin'
    ? 'temporary_works.deleted_to_bin'
    : 'temporary_works.deleted_to_folder'
}
