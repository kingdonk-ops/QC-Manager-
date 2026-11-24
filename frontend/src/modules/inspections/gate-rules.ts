/**
 * Display-only mirrors of the gate rules (which kinds can be waived, whether a kind blocks by default, the ranking
 * of authority levels, tones). The server decides every action; these only choose what to offer and how to show it.
 */

export const GATE_KINDS = ['hold', 'witness', 'surveillance', 'review'] as const
export const GATE_STATUSES = ['pending', 'released', 'waived', 'void'] as const
export const ATTACHMENT_KINDS = [
  'node',
  'item',
  'inspection',
  'task',
  'dossier',
] as const

/** Ascending: an asserted level meets a requirement when it is equal or higher. */
export const AUTHORITIES = [
  'contractor_qc',
  'contractor_qa',
  'client',
  'third_party_inspector',
  'authority_having_jurisdiction',
] as const

export const LINE_STATES = [
  'review',
  'passed',
  'released',
  'blocked',
  'pending',
] as const

const WAIVABLE: ReadonlySet<string> = new Set([
  'witness',
  'surveillance',
  'review',
])

/** Witness, surveillance and review gates can be waived; a hold never is. */
export function isWaivable(kind: string): boolean {
  return WAIVABLE.has(kind)
}

/** Only a hold blocks progress unless the blocking flag is set explicitly. */
export function defaultBlocking(kind: string): boolean {
  return kind === 'hold'
}

export function authorityRank(level: string): number {
  return AUTHORITIES.indexOf(level as (typeof AUTHORITIES)[number])
}

export function authoritySatisfies(asserted: string, required: string) {
  const a = authorityRank(asserted)
  const r = authorityRank(required)
  return a >= 0 && r >= 0 && a >= r
}

/** The attachment kind and identifier come together or not at all. */
export function attachmentPairValid(
  kind: string | null | undefined,
  id: number | string | null | undefined
): boolean {
  const hasKind = !!kind
  const hasId = id !== null && id !== undefined && `${id}`.trim() !== ''
  return hasKind === hasId
}

export type GateLike = { kind: string; status: string }

export type GateActionSet = {
  release: boolean
  waive: boolean
  void: boolean
  delete: boolean
}

/** What to offer on a gate to someone who holds the approve, update or delete permission. */
export function gateActions(
  gate: GateLike,
  perms: { approve: boolean; delete: boolean }
): GateActionSet {
  const pending = gate.status === 'pending'
  return {
    release: pending && perms.approve,
    waive: pending && perms.approve && isWaivable(gate.kind),
    void: pending && perms.approve,
    delete: pending && perms.delete,
  }
}

export function canSubmitWaiver(reason: string): boolean {
  return reason.trim() !== ''
}

export function statusTone(status: string): string {
  switch (status) {
    case 'released':
      return 'bg-green-600 text-white'
    case 'waived':
      return 'bg-sky-600 text-white'
    case 'void':
      return 'bg-muted text-muted-foreground line-through'
    default:
      return 'bg-amber-500 text-white'
  }
}

/** Colour of an ITP line light from the server's gate state. */
export function lightTone(state: string): string {
  switch (state) {
    case 'passed':
    case 'released':
      return 'bg-green-600'
    case 'blocked':
      return 'bg-red-600'
    case 'pending':
      return 'bg-amber-500'
    default:
      return 'bg-slate-400'
  }
}
