/**
 * Form drafts, display-only validation and the request bodies of the item and permit dialogs. Validation here only
 * mirrors the obvious field rules (required fields, day order) so people see a message early; the server decides.
 */
import type {
  Item,
  ItemCreate,
  ItemUpdate,
  Permit,
  PermitCreate,
  PermitUpdate,
} from './api'

export type ItemDraft = {
  reference: string
  title: string
  family: string
  category: string
  designer: string
  checker: string
  coordinator_name: string
  coordinator_user_id: number | null
  required_load_on: string
  required_strike_on: string
  design_due_on: string
  location: string
  sort_order: string
  description: string
  notes: string
  scaffold_id: number | null
  related: { key: string; value: string }[]
}

/** An error is a message key; the dialog shows it once the field has been touched. */
export type Errors = Record<string, string>

const text = (v: string | null | undefined) => v ?? ''

export function itemDraft(
  item?: Item,
  preset?: { family?: string; scaffold_id?: number }
): ItemDraft {
  return {
    reference: text(item?.reference),
    title: text(item?.title),
    family: item?.family ?? preset?.family ?? '',
    category:
      item?.design_check_category === null ||
      item?.design_check_category === undefined
        ? ''
        : String(item.design_check_category),
    designer: text(item?.designer),
    checker: text(item?.checker),
    coordinator_name: text(item?.coordinator_name),
    coordinator_user_id: item?.coordinator_user_id ?? null,
    required_load_on: text(item?.required_load_on),
    required_strike_on: text(item?.required_strike_on),
    design_due_on: text(item?.design_due_on),
    location: text(item?.location),
    sort_order: String(item?.sort_order ?? 0),
    description: text(item?.description),
    notes: text(item?.notes),
    scaffold_id: item?.scaffold_id ?? preset?.scaffold_id ?? null,
    related: Object.entries(item?.related_refs ?? {}).map(([key, value]) => ({
      key,
      value: String(value),
    })),
  }
}

const blank = (v: string) => v.trim() === ''

export function validateItem(d: ItemDraft): Errors {
  const errors: Errors = {}
  if (blank(d.reference)) errors.reference = 'temporary_works.error.required'
  if (blank(d.title)) errors.title = 'temporary_works.error.required'
  if (blank(d.family)) errors.family = 'temporary_works.error.required'
  if (
    d.required_load_on &&
    d.required_strike_on &&
    d.required_strike_on < d.required_load_on
  )
    errors.required_strike_on = 'temporary_works.error.date_order'
  if (!/^\d{1,7}$/.test(d.sort_order.trim()))
    errors.sort_order = 'temporary_works.error.sort_order'
  return errors
}

/** Empty text is absent: a null clears, an omission leaves alone. */
const orNull = (v: string) => (blank(v) ? null : v.trim())

const related = (d: ItemDraft) =>
  Object.fromEntries(
    d.related
      .filter((r) => !blank(r.key) && !blank(r.value))
      .map((r) => [r.key.trim(), r.value.trim()])
  )

/** The create body: reference, title and family are required, everything else is sent only when filled in. */
export function itemCreateBody(projectId: number, d: ItemDraft): ItemCreate {
  const body: Record<string, unknown> = {
    project_id: projectId,
    reference: d.reference.trim(),
    title: d.title.trim(),
    family: d.family,
  }
  const optional: [string, unknown][] = [
    ['design_check_category', blank(d.category) ? null : Number(d.category)],
    ['designer', orNull(d.designer)],
    ['checker', orNull(d.checker)],
    ['coordinator_name', orNull(d.coordinator_name)],
    ['coordinator_user_id', d.coordinator_user_id],
    ['required_load_on', orNull(d.required_load_on)],
    ['required_strike_on', orNull(d.required_strike_on)],
    ['design_due_on', orNull(d.design_due_on)],
    ['location', orNull(d.location)],
    ['description', orNull(d.description)],
    ['notes', orNull(d.notes)],
    ['scaffold_id', d.scaffold_id],
  ]
  for (const [key, value] of optional)
    if (value !== null && value !== undefined) body[key] = value
  const sort = Number(d.sort_order)
  if (sort > 0) body.sort_order = sort
  const refs = related(d)
  if (Object.keys(refs).length > 0) body.related_refs = refs
  return body as ItemCreate
}

/**
 * The edit body: only what changed. A cleared optional field is an explicit null; untouched fields are left out, so
 * the server does not judge them again.
 */
export function itemUpdateBody(original: Item, d: ItemDraft): ItemUpdate {
  const body: Record<string, unknown> = {}
  const text = (key: keyof Item, value: string) => {
    const before = (original[key] as string | null | undefined) ?? null
    const after = orNull(value)
    if (before !== after) body[key] = after
  }
  if (d.reference.trim() !== original.reference)
    body.reference = d.reference.trim()
  if (d.title.trim() !== original.title) body.title = d.title.trim()
  if (d.family !== original.family) body.family = d.family
  const category = blank(d.category) ? null : Number(d.category)
  if (category !== (original.design_check_category ?? null))
    body.design_check_category = category
  text('designer', d.designer)
  text('checker', d.checker)
  text('coordinator_name', d.coordinator_name)
  if (d.coordinator_user_id !== (original.coordinator_user_id ?? null))
    body.coordinator_user_id = d.coordinator_user_id
  text('required_load_on', d.required_load_on)
  text('required_strike_on', d.required_strike_on)
  text('design_due_on', d.design_due_on)
  text('location', d.location)
  text('description', d.description)
  text('notes', d.notes)
  if (d.scaffold_id !== (original.scaffold_id ?? null))
    body.scaffold_id = d.scaffold_id
  const sort = Number(d.sort_order)
  if (sort !== original.sort_order) body.sort_order = sort
  const refs = related(d)
  if (JSON.stringify(refs) !== JSON.stringify(original.related_refs ?? {}))
    body.related_refs = refs
  return body as ItemUpdate
}

export type PermitDraft = {
  number: string
  kind: string
  issued_by_name: string
  valid_from: string
  valid_to: string
  conditions: string
  design_check_accepted: boolean
  inspection_passed: boolean
}

export function permitDraft(permit?: Permit): PermitDraft {
  return {
    number: text(permit?.number),
    kind: permit?.kind ?? 'load',
    issued_by_name: text(permit?.issued_by_name),
    valid_from: text(permit?.valid_from),
    valid_to: text(permit?.valid_to),
    conditions: text(permit?.conditions),
    design_check_accepted: permit?.design_check_accepted ?? false,
    inspection_passed: permit?.inspection_passed ?? false,
  }
}

export function validatePermit(d: PermitDraft): Errors {
  const errors: Errors = {}
  if (blank(d.number)) errors.number = 'temporary_works.error.required'
  if (blank(d.kind)) errors.kind = 'temporary_works.error.required'
  if (d.valid_from && d.valid_to && d.valid_to < d.valid_from)
    errors.valid_to = 'temporary_works.error.valid_order'
  return errors
}

/** The prerequisite flags belong to permits to load; for the other kinds they stay unticked. */
export function permitCreateBody(d: PermitDraft): PermitCreate {
  const body: Record<string, unknown> = {
    number: d.number.trim(),
    kind: d.kind,
  }
  const optional: [string, string][] = [
    ['issued_by_name', d.issued_by_name],
    ['valid_from', d.valid_from],
    ['valid_to', d.valid_to],
    ['conditions', d.conditions],
  ]
  for (const [key, value] of optional) if (!blank(value)) body[key] = value.trim()
  if (d.kind === 'load') {
    body.design_check_accepted = d.design_check_accepted
    body.inspection_passed = d.inspection_passed
  }
  return body as PermitCreate
}

export function permitUpdateBody(
  original: Permit,
  d: PermitDraft
): PermitUpdate {
  const body: Record<string, unknown> = {}
  const text = (key: keyof Permit, value: string) => {
    const before = (original[key] as string | null | undefined) ?? null
    const after = orNull(value)
    if (before !== after) body[key] = after
  }
  if (d.number.trim() !== original.number) body.number = d.number.trim()
  if (d.kind !== original.kind) body.kind = d.kind
  text('issued_by_name', d.issued_by_name)
  text('valid_from', d.valid_from)
  text('valid_to', d.valid_to)
  text('conditions', d.conditions)
  if (d.kind === 'load') {
    if (d.design_check_accepted !== original.design_check_accepted)
      body.design_check_accepted = d.design_check_accepted
    if (d.inspection_passed !== original.inspection_passed)
      body.inspection_passed = d.inspection_passed
  }
  return body as PermitUpdate
}
