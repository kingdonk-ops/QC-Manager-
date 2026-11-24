import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Permit } from './api'
import {
  permitCreateBody,
  permitDraft,
  permitUpdateBody,
  validatePermit,
} from './form-schemas'
import { PermitActions } from './permit-actions'
import { PermitForm } from './permit-dialog'
import { PERM } from './rules'

const stored = (over: Partial<Permit> = {}): Permit =>
  ({
    id: 3,
    item_id: 1,
    number: 'PL-1',
    kind: 'load',
    status: 'draft',
    issued_by_name: null,
    valid_from: null,
    valid_to: null,
    conditions: null,
    design_check_accepted: false,
    inspection_passed: false,
    ...over,
  }) as unknown as Permit

describe('PermitForm', () => {
  it('shows the two prerequisite flags for a permit to load only', async () => {
    const screen = await render(
      <PermitForm initial={permitDraft()} submitLabel='go' onSubmit={vi.fn()} />
    )
    await expect.element(screen.getByTestId('tw-prerequisites')).toBeInTheDocument()
    await screen
      .getByLabelText('temporary_works.permit.kind')
      .selectOptions('strike')
    expect(screen.getByTestId('tw-prerequisites').elements()).toHaveLength(0)
  })

  it('asks for a number and shows the message after the first press', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <PermitForm initial={permitDraft()} submitLabel='go' onSubmit={onSubmit} />
    )
    await screen.getByTestId('tw-permit-submit').click()
    await expect
      .element(screen.getByTestId('tw-permit-number-error'))
      .toHaveTextContent('temporary_works.error.required')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends the draft with the number filled in', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <PermitForm initial={permitDraft()} submitLabel='go' onSubmit={onSubmit} />
    )
    await screen.getByLabelText('temporary_works.permit.number').fill('PL-9')
    await screen.getByTestId('tw-permit-submit').click()
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ number: 'PL-9', kind: 'load' })
  })

  it('shows the validity order message once the last valid day is touched', async () => {
    const screen = await render(
      <PermitForm initial={permitDraft()} submitLabel='go' onSubmit={vi.fn()} />
    )
    await screen.getByLabelText('temporary_works.permit.valid_from').fill('2026-03-10')
    await screen.getByLabelText('temporary_works.permit.valid_to').fill('2026-03-01')
    await screen.getByLabelText('temporary_works.permit.conditions').click()
    await expect
      .element(screen.getByTestId('tw-permit-to-error'))
      .toHaveTextContent('temporary_works.error.valid_order')
  })
})

describe('permit bodies', () => {
  it('sends the prerequisite flags for a permit to load and leaves them out for other kinds', () => {
    const load = { ...permitDraft(), number: 'A', kind: 'load', inspection_passed: true }
    expect(permitCreateBody(load)).toMatchObject({
      design_check_accepted: false,
      inspection_passed: true,
    })
    const strike = { ...load, kind: 'strike' }
    expect(permitCreateBody(strike)).not.toHaveProperty('inspection_passed')
  })

  it('sends an explicit null for a cleared field and only the changes on edit', () => {
    const permit = stored({ valid_to: '2026-04-01', conditions: 'Wet weather stop' })
    const d = { ...permitDraft(permit), valid_to: '' }
    expect(permitUpdateBody(permit, d)).toEqual({ valid_to: null })
    expect(permitUpdateBody(permit, permitDraft(permit))).toEqual({})
  })

  it('requires a number and rejects an end before the start', () => {
    expect(Object.keys(validatePermit(permitDraft()))).toEqual(['number'])
    expect(
      validatePermit({
        ...permitDraft(),
        number: 'A',
        valid_from: '2026-03-10',
        valid_to: '2026-03-01',
      }).valid_to
    ).toBe('temporary_works.error.valid_order')
  })
})

describe('PermitActions', () => {
  const has = (...held: string[]) => (p: string) => held.includes(p)

  it('shows issue, activate and close only to holders of the issue permission', async () => {
    const without = await render(
      <PermitActions status='issued' has={has(PERM.update)} onAct={vi.fn()} />
    )
    expect(without.getByTestId('permit-actions').elements()).toHaveLength(0)
  })

  it('offers activate and close on an issued permit to a coordinator', async () => {
    const onAct = vi.fn()
    const screen = await render(
      <PermitActions status='issued' has={has(PERM.issue)} onAct={onAct} />
    )
    await screen.getByRole('button', { name: 'temporary_works.permit.activate' }).click()
    expect(onAct).toHaveBeenCalledWith('activate')
    await expect
      .element(screen.getByRole('button', { name: 'temporary_works.permit.close' }))
      .toBeInTheDocument()
  })

  it('offers issue on a draft', async () => {
    const screen = await render(
      <PermitActions status='draft' has={has(PERM.issue)} onAct={vi.fn()} />
    )
    await expect
      .element(screen.getByRole('button', { name: 'temporary_works.permit.issue' }))
      .toBeInTheDocument()
  })
})
