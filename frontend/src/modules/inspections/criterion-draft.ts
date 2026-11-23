import type { Criterion, CriterionFields } from './criteria-api'

export type CriterionDraft = {
  code: string
  title: string
  description: string
  standards_ref: string
  discipline: string
  category: string
  characteristic: string
  method: string
  unit: string
  rule_type: CriterionFields['rule_type']
  nominal: string
  lower_limit: string
  upper_limit: string
  active: boolean
}

export function draftOf(c?: Criterion | null): CriterionDraft {
  return {
    code: c?.code ?? '',
    title: c?.title ?? '',
    description: c?.description ?? '',
    standards_ref: c?.standards_ref ?? '',
    discipline: c?.discipline ?? '',
    category: c?.category ?? '',
    characteristic: c?.characteristic ?? '',
    method: c?.method ?? '',
    unit: c?.unit ?? '',
    rule_type: (c?.rule_type ?? 'free_text') as CriterionDraft['rule_type'],
    nominal: c?.nominal ?? '',
    lower_limit: c?.lower_limit ?? '',
    upper_limit: c?.upper_limit ?? '',
    active: c?.active ?? true,
  }
}

const orNull = (v: string) => (v.trim() === '' ? null : v.trim())

/** The request fields: empty text becomes null so a cleared field is cleared on the server too. */
export function fieldsOf(d: CriterionDraft): CriterionFields {
  return {
    code: d.code.trim(),
    title: d.title.trim(),
    description: orNull(d.description),
    standards_ref: orNull(d.standards_ref),
    discipline: orNull(d.discipline),
    category: orNull(d.category),
    characteristic: orNull(d.characteristic),
    method: orNull(d.method),
    unit: orNull(d.unit),
    rule_type: d.rule_type,
    nominal: orNull(d.nominal),
    lower_limit: orNull(d.lower_limit),
    upper_limit: orNull(d.upper_limit),
    active: d.active,
  }
}
