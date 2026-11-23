import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { ApiError } from '@/api/client'
import { refusalText } from './api'
import { TransitionForm } from './transition-dialog'

const optionValues = (select: HTMLSelectElement) =>
  Array.from(select.options).map((o) => o.value)

describe('TransitionForm', () => {
  it('offers only the next steps for the status: forward, back and on hold', async () => {
    const screen = await render(
      <TransitionForm status='design_checked' onSubmit={vi.fn()} />
    )
    const select = screen
      .getByLabelText('temporary_works.transition.next')
      .element() as HTMLSelectElement
    expect(optionValues(select)).toEqual([
      'approved_to_load',
      'design_submitted',
      'on_hold',
    ])
  })

  it('offers only the status held from when the item is on hold', async () => {
    const screen = await render(
      <TransitionForm status='on_hold' heldFrom='loaded' onSubmit={vi.fn()} />
    )
    const select = screen
      .getByLabelText('temporary_works.transition.next')
      .element() as HTMLSelectElement
    expect(optionValues(select)).toEqual(['loaded'])
  })

  it('offers nothing for a removed item', async () => {
    const screen = await render(
      <TransitionForm status='removed' onSubmit={vi.fn()} />
    )
    await expect.element(screen.getByTestId('tw-no-steps')).toBeInTheDocument()
  })

  it('sends a forward step without a note', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <TransitionForm status='design_checked' onSubmit={onSubmit} />
    )
    await screen.getByTestId('tw-transition-submit').click()
    expect(onSubmit).toHaveBeenCalledWith({
      status: 'approved_to_load',
      note: null,
    })
  })

  it('needs a note to step back, then sends it', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <TransitionForm status='design_checked' onSubmit={onSubmit} />
    )
    await screen
      .getByLabelText('temporary_works.transition.next')
      .selectOptions('design_submitted')
    await expect.element(screen.getByTestId('tw-transition-submit')).toBeDisabled()
    await screen
      .getByLabelText('temporary_works.transition.note')
      .fill('Calculations need rework')
    await expect.element(screen.getByTestId('tw-transition-submit')).toBeEnabled()
    await screen.getByTestId('tw-transition-submit').click()
    expect(onSubmit).toHaveBeenCalledWith({
      status: 'design_submitted',
      note: 'Calculations need rework',
    })
  })

  it('needs a note to put an item on hold', async () => {
    const screen = await render(
      <TransitionForm status='loaded' onSubmit={vi.fn()} />
    )
    await screen
      .getByLabelText('temporary_works.transition.next')
      .selectOptions('on_hold')
    await expect.element(screen.getByTestId('tw-transition-submit')).toBeDisabled()
  })

  it('shows the server refusal word for word', async () => {
    const reason =
      'load-gate: Loading needs a valid permit to load that records both the design check and the inspection.'
    const screen = await render(
      <TransitionForm
        status='approved_to_load'
        refusal={reason}
        onSubmit={vi.fn()}
      />
    )
    await expect.element(screen.getByTestId('tw-refusal')).toHaveTextContent(reason)
  })

  it('shows no refusal box when there is none', async () => {
    const screen = await render(
      <TransitionForm status='approved_to_load' onSubmit={vi.fn()} />
    )
    expect(screen.getByTestId('tw-refusal').elements()).toHaveLength(0)
  })
})

describe('refusalText', () => {
  it('returns a string detail unchanged', () => {
    expect(refusalText(new ApiError(409, 'one-step: not allowed'))).toBe(
      'one-step: not allowed'
    )
  })

  it('joins a list of problems without parsing them', () => {
    expect(
      refusalText(new ApiError(422, [{ msg: 'first' }, { msg: 'second' }]))
    ).toBe('first; second')
  })

  it('falls back to the error message for anything else', () => {
    expect(refusalText(new Error('boom'))).toBe('boom')
  })
})
