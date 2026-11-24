import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { LinkedItem, LinkedPermit, LinkedRollup } from './api'
import { PermitsPanel, ScaffoldPermitsTab } from './scaffold-permits-tab'

const item = (over: Partial<LinkedItem> = {}): LinkedItem =>
  ({
    id: 1,
    reference: 'TW-1',
    title: 'Access scaffold',
    status: 'in_use',
    scaffold_id: 7,
    ...over,
  }) as unknown as LinkedItem

const permit = (over: Partial<LinkedPermit> = {}): LinkedPermit =>
  ({
    id: 10,
    item_id: 1,
    number: 'PL-1',
    kind: 'load',
    status: 'issued',
    valid_from: '2026-03-01',
    valid_to: '2026-03-31',
    design_check_accepted: true,
    inspection_passed: true,
    ...over,
  }) as unknown as LinkedPermit

const rollup = (over: Partial<LinkedRollup> = {}): LinkedRollup =>
  ({
    breaches: [],
    gates: [
      {
        item_id: 1,
        reference: 'TW-1',
        status: 'in_use',
        load_gate_open: true,
        strike_gate_open: false,
      },
    ],
    warnings: [],
    ...over,
  }) as unknown as LinkedRollup

const scaffold = {
  effective_tag: 'green' as const,
  inspection_overdue: false,
  next_inspection_due: '2026-04-05T00:00:00Z',
}

const breaching = rollup({
  breaches: [
    {
      item_id: 1,
      reference: 'TW-1',
      title: 'Access scaffold',
      reason: 'In use on 2026-03-02 with no valid permit to load',
    },
  ],
  gates: [
    {
      item_id: 1,
      reference: 'TW-1',
      status: 'in_use',
      load_gate_open: false,
      strike_gate_open: false,
    },
  ],
})

describe('PermitsPanel', () => {
  it('leads with a breach tag and the reason when an item bears load without a valid permit', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={scaffold}
        items={[item()]}
        permits={[]}
        rollup={breaching}
      />
    )
    await expect
      .element(screen.getByTestId('scaffold-breach-reason'))
      .toHaveTextContent('In use on 2026-03-02 with no valid permit to load')
    await expect.element(screen.getByTestId('scaffold-breach-tag')).toBeInTheDocument()
    await expect
      .element(screen.getByTestId('scaffold-load-gate'))
      .toHaveAttribute('data-ok', 'false')
  })

  it('notes that the scaffold tag is red because of a breach', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={{ ...scaffold, effective_tag: 'red' }}
        items={[item()]}
        permits={[]}
        rollup={breaching}
      />
    )
    await expect.element(screen.getByTestId('red-tag-note')).toBeInTheDocument()
  })

  it('shows no red-tag note when the tag is red but nothing is in breach', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={{ ...scaffold, effective_tag: 'red' }}
        items={[item()]}
        permits={[permit()]}
        rollup={rollup()}
      />
    )
    expect(screen.getByTestId('red-tag-note').elements()).toHaveLength(0)
  })

  it('shows the load gate open and the permit with its validity, with no breach', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={scaffold}
        items={[item()]}
        permits={[permit()]}
        rollup={rollup()}
      />
    )
    await expect
      .element(screen.getByTestId('scaffold-load-gate'))
      .toHaveAttribute('data-ok', 'true')
    await expect
      .element(screen.getByTestId('scaffold-permit'))
      .toHaveTextContent('PL-1')
    await expect
      .element(screen.getByTestId('scaffold-permit'))
      .toHaveTextContent('2026-03-31')
    expect(screen.getByTestId('scaffold-breach').elements()).toHaveLength(0)
    expect(screen.getByTestId('scaffold-breach-tag').elements()).toHaveLength(0)
  })

  it('prefers a live permit to load over a closed one', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={scaffold}
        items={[item()]}
        permits={[
          permit({ id: 11, number: 'PL-OLD', status: 'closed' }),
          permit({ id: 10, number: 'PL-LIVE' }),
        ]}
        rollup={rollup()}
      />
    )
    await expect
      .element(screen.getByTestId('scaffold-permit'))
      .toHaveTextContent('PL-LIVE')
  })

  it('shows the scaffold own next inspection and overdue state beside the permit state', async () => {
    const screen = await render(
      <PermitsPanel
        scaffold={{ ...scaffold, inspection_overdue: true }}
        items={[item()]}
        permits={[permit()]}
        rollup={rollup()}
      />
    )
    await expect
      .element(screen.getByTestId('scaffold-inspection'))
      .toHaveAttribute('data-overdue', 'true')
    await expect.element(screen.getByTestId('scaffold-permit')).toBeInTheDocument()
  })

  it('says so when no item is linked', async () => {
    const screen = await render(
      <PermitsPanel scaffold={scaffold} items={[]} permits={[]} rollup={rollup()} />
    )
    await expect.element(screen.getByTestId('scaffold-no-items')).toBeInTheDocument()
  })

  it('shows the create shortcut only when given one, pointing at the register with the scaffold', async () => {
    const editor = await render(
      <PermitsPanel
        scaffold={scaffold}
        items={[]}
        permits={[]}
        rollup={rollup()}
        createHref='/temporary-works?new=scaffold&scaffold_id=7'
      />
    )
    await expect
      .element(editor.getByTestId('scaffold-create-item'))
      .toHaveAttribute('href', '/temporary-works?new=scaffold&scaffold_id=7')
    await expect
      .element(editor.getByTestId('scaffold-register-link'))
      .toHaveAttribute('href', '/temporary-works')
  })

  it('shows no create shortcut to a viewer', async () => {
    const viewer = await render(
      <PermitsPanel scaffold={scaffold} items={[]} permits={[]} rollup={rollup()} />
    )
    expect(viewer.getByTestId('scaffold-create-item').elements()).toHaveLength(0)
  })
})

describe('ScaffoldPermitsTab', () => {
  it('shows nothing and makes no request when the module is off or unreadable', async () => {
    const client = new QueryClient()
    const screen = await render(
      <QueryClientProvider client={client}>
        <ScaffoldPermitsTab
          scaffold={scaffold}
          projectId={1}
          scaffoldId={7}
          on={false}
          canCreate
        />
      </QueryClientProvider>
    )
    expect(screen.getByTestId('scaffold-permits').elements()).toHaveLength(0)
    expect(client.isFetching()).toBe(0)
    expect(client.getQueryCache().getAll()[0]?.state.fetchStatus).toBe('idle')
  })
})
