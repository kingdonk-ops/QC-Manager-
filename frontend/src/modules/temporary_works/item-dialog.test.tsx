import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Item } from './api'
import {
  itemCreateBody,
  itemDraft,
  itemUpdateBody,
  validateItem,
} from './form-schemas'
import { ItemForm } from './item-dialog'
import { WarningsList } from './warnings-list'

const stored = (over: Partial<Item> = {}): Item =>
  ({
    id: 5,
    project_id: 1,
    reference: 'TW-5',
    title: 'Slab props',
    family: 'propping',
    description: null,
    design_check_category: 2,
    designer: 'Dee',
    checker: 'Chris',
    coordinator_name: null,
    coordinator_user_id: null,
    status: 'identified',
    held_from: null,
    required_load_on: '2026-03-10',
    required_strike_on: null,
    design_due_on: null,
    location: 'Level 3',
    asset_node_id: null,
    sort_order: 0,
    notes: null,
    scaffold_id: null,
    related_refs: {},
    ...over,
  }) as unknown as Item

function form(onSubmit = vi.fn()) {
  return (
    <ItemForm
      initial={itemDraft()}
      scaffolds={[{ value: '7', label: 'SC-7' }]}
      submitLabel='go'
      onSubmit={onSubmit}
    />
  )
}

describe('ItemForm', () => {
  it('shows a message for an untouched-then-empty field only after interaction', async () => {
    const screen = await render(form())
    expect(screen.getByTestId('tw-reference-error').elements()).toHaveLength(0)
    await screen.getByLabelText('temporary_works.item.reference').click()
    await screen.getByLabelText('temporary_works.item.title').click()
    await expect
      .element(screen.getByTestId('tw-reference-error'))
      .toHaveTextContent('temporary_works.error.required')
    expect(screen.getByTestId('tw-title-error').elements()).toHaveLength(0)
  })

  it('shows every missing required field when submitted empty, without sending', async () => {
    const onSubmit = vi.fn()
    const screen = await render(form(onSubmit))
    await screen.getByTestId('tw-item-submit').click()
    await expect.element(screen.getByTestId('tw-reference-error')).toBeInTheDocument()
    await expect.element(screen.getByTestId('tw-title-error')).toBeInTheDocument()
    await expect.element(screen.getByTestId('tw-family-error')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends the draft once reference, title and family are filled in', async () => {
    const onSubmit = vi.fn()
    const screen = await render(form(onSubmit))
    await screen.getByLabelText('temporary_works.item.reference').fill('TW-9')
    await screen.getByLabelText('temporary_works.item.title').fill('Hoarding')
    await screen
      .getByLabelText('temporary_works.item.family')
      .selectOptions('hoarding')
    await screen.getByTestId('tw-item-submit').click()
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      reference: 'TW-9',
      title: 'Hoarding',
      family: 'hoarding',
    })
  })

  it('offers the scaffold picker only for the scaffold family', async () => {
    const screen = await render(form())
    expect(screen.getByLabelText('temporary_works.item.scaffold').elements()).toHaveLength(0)
    await screen
      .getByLabelText('temporary_works.item.family')
      .selectOptions('scaffold')
    await expect
      .element(screen.getByLabelText('temporary_works.item.scaffold'))
      .toBeInTheDocument()
  })

  it('presets the scaffold family and link', async () => {
    const screen = await render(
      <ItemForm
        initial={itemDraft(undefined, { family: 'scaffold', scaffold_id: 7 })}
        scaffolds={[{ value: '7', label: 'SC-7' }]}
        submitLabel='go'
        onSubmit={vi.fn()}
      />
    )
    await expect
      .element(screen.getByLabelText('temporary_works.item.scaffold'))
      .toHaveValue('7')
  })

  it('shows the day-order message once the strike day is touched', async () => {
    const screen = await render(form())
    await screen.getByLabelText('temporary_works.required_load').fill('2026-03-10')
    await screen.getByLabelText('temporary_works.required_strike').fill('2026-03-01')
    await screen.getByLabelText('temporary_works.item.location').click()
    await expect
      .element(screen.getByTestId('tw-required-strike-error'))
      .toHaveTextContent('temporary_works.error.date_order')
  })
})

describe('request bodies', () => {
  it('carries only reference, title and family as required on create', () => {
    const d = {
      ...itemDraft(),
      reference: ' TW-1 ',
      title: 'Props',
      family: 'propping',
    }
    expect(Object.keys(itemCreateBody(3, d)).sort()).toEqual([
      'family',
      'project_id',
      'reference',
      'title',
    ])
    expect(itemCreateBody(3, d)).toMatchObject({ project_id: 3, reference: 'TW-1' })
  })

  it('sends the optional fields that were filled in', () => {
    const d = {
      ...itemDraft(),
      reference: 'A',
      title: 'B',
      family: 'scaffold',
      category: '2',
      scaffold_id: 7,
      related: [{ key: 'rfi', value: 'RFI-1' }],
    }
    expect(itemCreateBody(1, d)).toMatchObject({
      design_check_category: 2,
      scaffold_id: 7,
      related_refs: { rfi: 'RFI-1' },
    })
  })

  it('sends an explicit null for a cleared field and omits untouched ones', () => {
    const item = stored()
    const d = { ...itemDraft(item), designer: '' }
    expect(itemUpdateBody(item, d)).toEqual({ designer: null })
  })

  it('sends only what changed, and nothing when nothing did', () => {
    const item = stored()
    expect(itemUpdateBody(item, itemDraft(item))).toEqual({})
    expect(
      itemUpdateBody(item, { ...itemDraft(item), title: 'New', category: '' })
    ).toEqual({ title: 'New', design_check_category: null })
  })

  it('validates the three required fields and the day order', () => {
    expect(Object.keys(validateItem(itemDraft())).sort()).toEqual([
      'family',
      'reference',
      'title',
    ])
    const d = {
      ...itemDraft(stored()),
      required_load_on: '2026-03-10',
      required_strike_on: '2026-03-01',
    }
    expect(validateItem(d).required_strike_on).toBe(
      'temporary_works.error.date_order'
    )
  })
})

describe('WarningsList', () => {
  it('lists the warnings a save returned', async () => {
    const screen = await render(
      <WarningsList
        warnings={[{ rule: 'design-due-late', message: 'Design is due late' }]}
      />
    )
    await expect
      .element(screen.getByTestId('warnings-list'))
      .toHaveTextContent('Design is due late')
  })

  it('shows nothing when there are no warnings', async () => {
    const screen = await render(<WarningsList warnings={[]} />)
    expect(screen.getByTestId('warnings-list').elements()).toHaveLength(0)
  })
})
