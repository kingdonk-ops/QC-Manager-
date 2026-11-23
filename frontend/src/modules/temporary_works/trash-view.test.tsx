import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { DeletedItem, DeletedPermit } from './api'
import { RetentionForm } from './retention-setting'
import { TrashLists } from './trash-view'

const item = {
  id: 1,
  reference: 'TW-1',
  title: 'Props',
  family: 'propping',
  status: 'identified',
  deleted_at: '2026-03-01T00:00:00Z',
  purge_on: '2026-03-31T00:00:00Z',
} as unknown as DeletedItem

const permit = {
  id: 2,
  number: 'PL-1',
  kind: 'load',
  status: 'draft',
  deleted_at: '2026-03-01T00:00:00Z',
  purge_on: null,
} as unknown as DeletedPermit

const lists = (over: Partial<Parameters<typeof TrashLists>[0]> = {}) => (
  <TrashLists
    items={[item]}
    permits={[permit]}
    view='bin'
    canRestore
    onRestoreItem={vi.fn()}
    onRestorePermit={vi.fn()}
    {...over}
  />
)

describe('TrashLists', () => {
  it('lists deleted items and permits with Restore for the restore permission', async () => {
    const screen = await render(lists())
    expect(screen.getByTestId('trash-row').elements()).toHaveLength(2)
    expect(screen.getByTestId('restore-button').elements()).toHaveLength(2)
  })

  it('offers no Restore without the restore permission', async () => {
    const screen = await render(lists({ canRestore: false }))
    expect(screen.getByTestId('restore-button').elements()).toHaveLength(0)
  })

  it('shows when the purge may remove a record in the recycle bin only', async () => {
    const bin = await render(lists())
    await expect.element(bin.getByTestId('purge-on')).toBeInTheDocument()
  })

  it('shows no purge date in the Deleted folder', async () => {
    const folder = await render(lists({ view: 'deleted' }))
    expect(folder.getByTestId('purge-on').elements()).toHaveLength(0)
    await expect
      .element(folder.getByTestId('trash-lists'))
      .toHaveAttribute('data-view', 'deleted')
  })

  it('reports which record to restore', async () => {
    const onRestoreItem = vi.fn()
    const screen = await render(
      lists({ permits: [], onRestoreItem })
    )
    await screen.getByTestId('restore-button').click()
    expect(onRestoreItem).toHaveBeenCalledWith(1)
  })

  it('says when a view is empty', async () => {
    const screen = await render(lists({ items: [], permits: [] }))
    expect(screen.getByTestId('trash-row').elements()).toHaveLength(0)
  })
})

describe('RetentionForm', () => {
  const form = (onSave = vi.fn(), days = 30) => (
    <RetentionForm days={days} min={1} max={60} defaultDays={30} onSave={onSave} />
  )

  it('saves a new number of days within the range', async () => {
    const onSave = vi.fn()
    const screen = await render(form(onSave))
    await screen.getByTestId('retention-input').fill('45')
    await screen.getByTestId('retention-save').click()
    expect(onSave).toHaveBeenCalledWith(45)
  })

  it('refuses a value above the maximum or below the minimum', async () => {
    const screen = await render(form())
    await screen.getByTestId('retention-input').fill('61')
    await expect.element(screen.getByTestId('retention-save')).toBeDisabled()
    await screen.getByTestId('retention-input').fill('0')
    await expect.element(screen.getByTestId('retention-save')).toBeDisabled()
  })

  it('keeps Save disabled while the value is unchanged', async () => {
    const screen = await render(form())
    await expect.element(screen.getByTestId('retention-save')).toBeDisabled()
  })
})
