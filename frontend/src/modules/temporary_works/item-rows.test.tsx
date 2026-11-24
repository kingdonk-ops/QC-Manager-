import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Item, Permit, Rollup } from './api'
import { ItemRows, type RowActions } from './item-rows'

const item = (over: Partial<Item> = {}): Item =>
  ({
    id: 1,
    project_id: 1,
    reference: 'TW-1',
    title: 'Slab props',
    family: 'propping',
    status: 'in_use',
    held_from: null,
    design_check_category: 2,
    scaffold_id: null,
    required_load_on: '2026-03-01',
    required_strike_on: null,
    design_due_on: null,
    designer: null,
    checker: null,
    coordinator_name: null,
    location: null,
    ...over,
  }) as unknown as Item

const permit = (over: Partial<Permit> = {}): Permit =>
  ({
    id: 10,
    item_id: 1,
    number: 'PL-1',
    kind: 'load',
    status: 'issued',
    valid_from: '2026-03-01',
    valid_to: null,
    design_check_accepted: true,
    inspection_passed: false,
    ...over,
  }) as unknown as Permit

const gate = (open: boolean) =>
  ({
    item_id: 1,
    reference: 'TW-1',
    status: 'in_use',
    load_gate_open: open,
    strike_gate_open: false,
  }) as Rollup['gates'][number]

const noActions: RowActions = { onItem: vi.fn(), onPermit: vi.fn() }
const has = () => true

function rows(over: Partial<Parameters<typeof ItemRows>[0]> = {}) {
  return (
    <ItemRows
      items={[item()]}
      permits={[permit()]}
      gates={[gate(false)]}
      breachIds={new Set()}
      warnings={[]}
      has={has}
      actions={noActions}
      {...over}
    />
  )
}

describe('ItemRows', () => {
  it('tags and tints a breaching item', async () => {
    const screen = await render(rows({ breachIds: new Set([1]) }))
    const row = screen.getByTestId('item-row')
    await expect.element(row).toHaveAttribute('data-breach', 'true')
    await expect.element(screen.getByTestId('breach-tag')).toBeInTheDocument()
  })

  it('shows no breach tag for an item that is not in breach', async () => {
    const screen = await render(rows())
    await expect
      .element(screen.getByTestId('item-row'))
      .toHaveAttribute('data-breach', 'false')
    expect(screen.getByTestId('breach-tag').elements()).toHaveLength(0)
  })

  it('shows the load and strike gate indicators the server reported', async () => {
    const screen = await render(rows())
    await expect
      .element(screen.getByTestId('load-gate'))
      .toHaveAttribute('data-ok', 'false')
    await expect
      .element(screen.getByTestId('strike-gate'))
      .toHaveAttribute('data-ok', 'false')
  })

  it('expands to the permits with kind, number, status, validity and both prerequisites', async () => {
    const screen = await render(rows())
    await screen.getByRole('button', { name: /temporary_works.expand/ }).click()
    await expect.element(screen.getByTestId('permit-table')).toBeInTheDocument()
    await expect
      .element(screen.getByTestId('permit-table'))
      .toHaveTextContent('PL-1')
    await expect
      .element(screen.getByTestId('permit-table'))
      .toHaveTextContent('temporary_works.kind.load')
    await expect
      .element(screen.getByTestId('permit-status'))
      .toHaveTextContent('temporary_works.permit_status.issued')
    await expect
      .element(screen.getByTestId('permit-validity'))
      .toHaveTextContent('2026-03-01')
    await expect
      .element(screen.getByTestId('prereq-design'))
      .toHaveAttribute('data-ok', 'true')
    await expect
      .element(screen.getByTestId('prereq-inspection'))
      .toHaveAttribute('data-ok', 'false')
  })

  it('shows no prerequisite indicators for a permit to strike', async () => {
    const screen = await render(
      rows({ permits: [permit({ kind: 'strike' })] })
    )
    await screen.getByRole('button', { name: /temporary_works.expand/ }).click()
    expect(screen.getByTestId('prereq-design').elements()).toHaveLength(0)
  })

  it('links a scaffold item to its scaffold and lists its warnings', async () => {
    const screen = await render(
      rows({
        items: [item({ scaffold_id: 7 })],
        warnings: [
          { item_id: 1, reference: 'TW-1', rule: 'scaffold-red', message: 'Scaffold tag is red' },
        ],
      })
    )
    await screen.getByRole('button', { name: /temporary_works.expand/ }).click()
    await expect
      .element(screen.getByTestId('scaffold-link'))
      .toHaveAttribute('href', '/scaffolds?id=7')
    await expect
      .element(screen.getByTestId('item-warnings'))
      .toHaveTextContent('Scaffold tag is red')
  })

  it('shows loading placeholders while loading', async () => {
    const screen = await render(rows({ loading: true }))
    await expect.element(screen.getByTestId('rows-loading')).toBeInTheDocument()
  })

  it('shows a hint when filters leave no rows and a different one for an empty register', async () => {
    const filtered = await render(rows({ items: [], filtered: true }))
    await expect
      .element(filtered.getByTestId('rows-empty'))
      .toHaveTextContent('temporary_works.no_results')
  })

  it('shows the empty register message when nothing was filtered', async () => {
    const screen = await render(rows({ items: [], filtered: false }))
    await expect
      .element(screen.getByTestId('rows-empty'))
      .toHaveTextContent('temporary_works.empty')
  })

  it('offers delete only on a draft item and return to draft only on another', async () => {
    const draft = await render(
      rows({ items: [item({ status: 'identified' })], permits: [] })
    )
    await draft.getByRole('button', { name: /temporary_works.expand/ }).click()
    expect(draft.getByTestId('item-actions').element().querySelector('[data-action="delete"]')).not.toBeNull()
    expect(draft.getByTestId('item-actions').element().querySelector('[data-action="return"]')).toBeNull()
  })

  it('offers return to draft but not delete on an item that has moved on', async () => {
    const screen = await render(rows({ permits: [] }))
    await screen.getByRole('button', { name: /temporary_works.expand/ }).click()
    const actions = screen.getByTestId('item-actions').element()
    expect(actions.querySelector('[data-action="return"]')).not.toBeNull()
    expect(actions.querySelector('[data-action="delete"]')).toBeNull()
  })

  it('reports an item action', async () => {
    const onItem = vi.fn()
    const screen = await render(
      rows({ actions: { onItem, onPermit: vi.fn() }, permits: [] })
    )
    await screen.getByRole('button', { name: /temporary_works.expand/ }).click()
    await screen.getByRole('button', { name: 'temporary_works.edit' }).click()
    expect(onItem).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 'edit')
  })
})
