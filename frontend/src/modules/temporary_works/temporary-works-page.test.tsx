import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Item, Rollup } from './api'
import { applyFilters, NO_FILTERS } from './filter-rules'
import { RegisterBody } from './register-body'

const item = (id: number, over: Partial<Item> = {}): Item =>
  ({
    id,
    project_id: 1,
    reference: `TW-${id}`,
    title: `Item ${id}`,
    family: 'propping',
    status: 'in_use',
    held_from: null,
    design_check_category: 1,
    scaffold_id: null,
    created_at: '2026-01-10T00:00:00Z',
    updated_at: '2026-01-10T00:00:00Z',
    ...over,
  }) as unknown as Item

const rollup = (over: Partial<Rollup> = {}): Rollup =>
  ({
    as_of: '2026-03-02',
    total: 2,
    compliant: false,
    gates: [],
    breaches: [
      { item_id: 1, reference: 'TW-1', title: 'Item 1', reason: 'In use with no valid permit to load' },
    ],
    status_counts: { loaded: 1, in_use: 1 },
    category_counts: {},
    design_clearance: '50.00',
    overdue_to_load: [],
    overdue_to_strike: [],
    warnings: [],
    ...over,
  }) as unknown as Rollup

const actions = { onItem: vi.fn(), onPermit: vi.fn() }
const props = {
  items: [item(1), item(2, { status: 'loaded', family: 'formwork' })],
  total: 2,
  permits: [],
  has: () => true,
  actions,
  nowMs: Date.parse('2026-03-31T00:00:00Z'),
}

describe('RegisterBody', () => {
  it('leads with the breach banner, counts the breach and tints the breaching row', async () => {
    const screen = await render(<RegisterBody {...props} rollup={rollup()} />)
    await expect
      .element(screen.getByTestId('breach-banner'))
      .toHaveAttribute('data-count', '1')
    await expect
      .element(screen.getByTestId('figure-breaches'))
      .toHaveAttribute('data-tone', 'bad')
    const tinted = screen
      .getByTestId('item-row')
      .elements()
      .filter((r) => r.getAttribute('data-breach') === 'true')
    expect(tinted).toHaveLength(1)
  })

  it('shows the reassurance banner when the server reports no breach', async () => {
    const screen = await render(
      <RegisterBody {...props} rollup={rollup({ breaches: [] })} />
    )
    await expect
      .element(screen.getByTestId('no-breach-banner'))
      .toBeInTheDocument()
    expect(screen.getByTestId('breach-banner').elements()).toHaveLength(0)
  })

  it('shows items bearing load as loaded plus in use from the server status counts', async () => {
    const screen = await render(<RegisterBody {...props} rollup={rollup()} />)
    await expect
      .element(screen.getByTestId('figure-bearing-load'))
      .toHaveTextContent('2')
    await expect
      .element(screen.getByTestId('figure-clearance'))
      .toHaveTextContent('50.00%')
  })

  it('shows loading placeholders and no figures before the register arrives', async () => {
    const screen = await render(
      <RegisterBody {...props} items={[]} total={0} loading />
    )
    await expect.element(screen.getByTestId('rows-loading')).toBeInTheDocument()
    expect(screen.getByTestId('figure-items').elements()).toHaveLength(0)
  })

  it('narrows the list with the search and updates the showing count', async () => {
    const screen = await render(<RegisterBody {...props} rollup={rollup()} />)
    await expect
      .element(screen.getByTestId('showing-count'))
      .toHaveAttribute('data-shown', '2')
    await screen.getByLabelText('temporary_works.search').fill('TW-2')
    await expect
      .element(screen.getByTestId('showing-count'))
      .toHaveAttribute('data-shown', '1')
    await screen.getByLabelText('temporary_works.search').fill('nothing matches')
    await expect.element(screen.getByTestId('rows-empty')).toHaveTextContent(
      'temporary_works.no_results'
    )
  })

  it('says when the register holds more items than were loaded', async () => {
    const screen = await render(
      <RegisterBody {...props} rollup={rollup()} total={250} />
    )
    await expect
      .element(screen.getByTestId('rows-truncated'))
      .toBeInTheDocument()
  })
})

describe('applyFilters', () => {
  const rows = [
    item(1),
    item(2, { status: 'loaded', family: 'formwork', design_check_category: null }),
  ]
  it('filters by status, family and category', () => {
    expect(applyFilters(rows, { ...NO_FILTERS, status: 'loaded' })).toHaveLength(1)
    expect(applyFilters(rows, { ...NO_FILTERS, family: 'propping' })).toHaveLength(1)
    expect(applyFilters(rows, { ...NO_FILTERS, category: '1' })).toHaveLength(1)
    expect(
      applyFilters(rows, { ...NO_FILTERS, category: 'unassigned' })
    ).toHaveLength(1)
  })

  it('searches reference and title without regard to case', () => {
    expect(applyFilters(rows, { ...NO_FILTERS, search: 'tw-1' })).toHaveLength(1)
    expect(applyFilters(rows, { ...NO_FILTERS, search: 'item' })).toHaveLength(2)
  })
})
