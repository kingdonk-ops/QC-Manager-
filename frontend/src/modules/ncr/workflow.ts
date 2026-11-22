/**
 * The issues engine's fixed workflows, mirrored from the backend (`ncr/constants.py`), and the
 * pure helpers the sheet and the template designer use.
 */

export type IssueType = 'punch' | 'ncr'

export type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'date'
  | 'select'
  | 'multiselect'
  | 'checkbox'
  | 'photo'

export type FieldDef = {
  key: string
  label: string
  type: FieldType
  step: string
  required?: boolean
  options?: string[]
  help?: string | null
  unit?: string | null
  min?: number | null
  max?: number | null
}

export const FIELD_TYPES: FieldType[] = [
  'text',
  'textarea',
  'number',
  'date',
  'select',
  'multiselect',
  'checkbox',
  'photo',
]

export const LIFECYCLES: Record<IssueType, string[]> = {
  punch: ['open', 'rectified', 'verified', 'closed'],
  ncr: [
    'open',
    'disposition',
    'root_cause',
    'corrective_action',
    'effectiveness',
    'closed',
  ],
}

export const STEPS: Record<IssueType, string[]> = {
  punch: ['raise', 'rectify', 'verify'],
  ncr: [
    'raise',
    'containment',
    'disposition',
    'root_cause',
    'corrective_action',
    'effectiveness',
  ],
}

/** The first step still open in each status; fields of earlier steps are read-only. */
const STEP_AT: Record<IssueType, Record<string, number>> = {
  punch: { open: 0, rectified: 2, verified: 3 },
  ncr: {
    open: 0,
    disposition: 2,
    root_cause: 3,
    corrective_action: 4,
    effectiveness: 5,
  },
}

export const TERMINAL = ['closed', 'void', 'upgraded', 'escalated']

export type Move = {
  to: string
  /** i18n key of the button label. */
  label: string
  permission: string
  /** A reason is required (sending it back). */
  needsNote?: boolean
  /** The effectiveness sign-off. */
  attest?: boolean
  back?: boolean
}

const MOVES: Record<IssueType, Record<string, Move[]>> = {
  punch: {
    open: [
      {
        to: 'rectified',
        label: 'issues.do.rectify',
        permission: 'ncr.transition',
      },
    ],
    rectified: [
      { to: 'verified', label: 'issues.do.verify', permission: 'ncr.verify' },
      {
        to: 'open',
        label: 'issues.do.reject',
        permission: 'ncr.verify',
        needsNote: true,
        back: true,
      },
    ],
    verified: [
      { to: 'closed', label: 'issues.do.close', permission: 'ncr.verify' },
    ],
  },
  ncr: {
    open: [
      {
        to: 'disposition',
        label: 'issues.do.contained',
        permission: 'ncr.transition',
      },
    ],
    disposition: [
      {
        to: 'root_cause',
        label: 'issues.do.record_disposition',
        permission: 'ncr.verify',
      },
    ],
    root_cause: [
      {
        to: 'corrective_action',
        label: 'issues.do.record_root_cause',
        permission: 'ncr.transition',
      },
    ],
    corrective_action: [
      {
        to: 'effectiveness',
        label: 'issues.do.actions_done',
        permission: 'ncr.transition',
      },
    ],
    effectiveness: [
      {
        to: 'closed',
        label: 'issues.do.verify_effective',
        permission: 'ncr.verify',
        attest: true,
      },
      {
        to: 'corrective_action',
        label: 'issues.do.ineffective',
        permission: 'ncr.verify',
        needsNote: true,
        back: true,
      },
    ],
  },
}

export function asType(value: string | null | undefined): IssueType {
  return value === 'punch' ? 'punch' : 'ncr'
}

export function movesFor(type: IssueType, status: string): Move[] {
  return MOVES[type][status] ?? []
}

export function isOpen(status: string) {
  return !TERMINAL.includes(status)
}

export function stepAt(type: IssueType, status: string) {
  return STEP_AT[type][status] ?? 99
}

/** A field may be edited while its step is not yet completed (and the issue is open). */
export function fieldEditable(
  type: IssueType,
  status: string,
  field: FieldDef
) {
  if (!isOpen(status)) return false
  return STEPS[type].indexOf(field.step) >= stepAt(type, status)
}

/** Which lifecycle step to highlight; terminal states other than closed keep the last one reached. */
export function lifecycleIndex(type: IssueType, status: string) {
  return LIFECYCLES[type].indexOf(status)
}

/** Fields grouped by step, in step order, skipping empty steps. */
export function fieldsByStep(type: IssueType, fields: FieldDef[]) {
  return STEPS[type]
    .map((step) => ({ step, fields: fields.filter((f) => f.step === step) }))
    .filter((g) => g.fields.length > 0)
}

/** Required fields of the steps a move completes that are still empty. */
export function missingFor(
  type: IssueType,
  status: string,
  to: string,
  fields: FieldDef[],
  answers: Record<string, unknown>
) {
  const from = stepAt(type, status)
  const upto = stepAt(type, to)
  const steps = STEPS[type].filter((_, i) => i >= from && i < upto)
  return fields
    .filter((f) => f.required && steps.includes(f.step))
    .filter((f) => isEmpty(answers[f.key]))
    .map((f) => f.label)
}

export function isEmpty(value: unknown) {
  return (
    value === undefined ||
    value === null ||
    value === '' ||
    value === false ||
    (Array.isArray(value) && value.length === 0)
  )
}

/** A field key from a label (units in brackets dropped): lower snake case, starting with a letter, at most 40 characters. */
export function keyFromLabel(label: string, taken: string[] = []) {
  let base = label
    .replace(/\([^)]*\)/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 36)
  if (!/^[a-z]/.test(base)) base = `f_${base}`.slice(0, 36)
  let key = base || 'field'
  let n = 2
  while (taken.includes(key)) key = `${base}_${n++}`
  return key
}

/** Problems in a field list the server would refuse, so the designer can say so before saving. */
export function fieldProblems(type: IssueType, fields: FieldDef[]) {
  const problems: string[] = []
  const seen = new Set<string>()
  for (const f of fields) {
    if (!/^[a-z][a-z0-9_]{0,39}$/.test(f.key))
      problems.push(`${f.label || f.key}: invalid key`)
    if (seen.has(f.key)) problems.push(`${f.key}: used twice`)
    seen.add(f.key)
    if (!f.label.trim()) problems.push(`${f.key}: needs a label`)
    if (!STEPS[type].includes(f.step))
      problems.push(`${f.key}: step ${f.step} is not a ${type} step`)
    if (
      (f.type === 'select' || f.type === 'multiselect') &&
      !(f.options ?? []).length
    )
      problems.push(`${f.key}: needs options`)
  }
  return problems
}
