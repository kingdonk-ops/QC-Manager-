import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { WaiveForm } from './gate-dialogs'
import { gateActions } from './gate-rules'
import { GateActions, ProceedBanner } from './gates-panel'
import { LineLight } from './line-light'
import type { GateProceed } from './gates-api'
import type { ItpLine } from './quality-api'

const perms = { approve: true, delete: false }

describe('GateActions', () => {
  // Locators from render() search the whole page body, so each gate kind is rendered in its own test;
  // a second render in the same test would also see the first render's buttons.
  it('offers waive on a witness gate', async () => {
    const witness = await render(
      <GateActions
        actions={gateActions({ kind: 'witness', status: 'pending' }, perms)}
        onAct={vi.fn()}
      />
    )
    await expect
      .element(witness.getByRole('button', { name: 'inspections.gates.waive' }))
      .toBeInTheDocument()
  })

  it('never offers waive on a hold gate', async () => {
    const hold = await render(
      <GateActions
        actions={gateActions({ kind: 'hold', status: 'pending' }, perms)}
        onAct={vi.fn()}
      />
    )
    expect(
      hold.getByRole('button', { name: 'inspections.gates.waive' }).elements()
    ).toHaveLength(0)
    await expect
      .element(hold.getByRole('button', { name: 'inspections.gates.release' }))
      .toBeInTheDocument()
  })

  it('reports which action was chosen', async () => {
    const onAct = vi.fn()
    const screen = await render(
      <GateActions
        actions={gateActions({ kind: 'review', status: 'pending' }, perms)}
        onAct={onAct}
      />
    )
    await screen
      .getByRole('button', { name: 'inspections.gates.waive' })
      .click()
    expect(onAct).toHaveBeenCalledWith('waive')
  })
})

describe('WaiveForm', () => {
  it('keeps the waive button disabled until a reason is typed, then sends it', async () => {
    const onSubmit = vi.fn()
    const screen = await render(<WaiveForm onSubmit={onSubmit} />)
    await expect.element(screen.getByTestId('waive-submit')).toBeDisabled()
    await screen
      .getByLabelText('inspections.gates.reason')
      .fill('  Client agreed on site  ')
    await expect.element(screen.getByTestId('waive-submit')).toBeEnabled()
    await screen.getByTestId('waive-submit').click()
    expect(onSubmit).toHaveBeenCalledWith('Client agreed on site')
  })
})

const answer = (over: Partial<GateProceed>): GateProceed => ({
  project_id: 1,
  attachment_kind: 'inspection',
  attachment_id: 5,
  can_proceed: true,
  gate_numbers: [],
  gate_ids: [],
  overridden_gate_numbers: [],
  overridden_gate_ids: [],
  hold_points: [],
  ...over,
})

describe('ProceedBanner', () => {
  it('says progress is not allowed and lists the blocking gate numbers', async () => {
    const screen = await render(
      <ProceedBanner
        answer={answer({ can_proceed: false, gate_numbers: ['GATE-001'], gate_ids: [1] })}
      />
    )
    const banner = screen.getByTestId('proceed-banner')
    await expect.element(banner).toHaveAttribute('data-allowed', 'false')
    await expect.element(banner).toHaveTextContent('inspections.gates.proceed_no')
    await expect.element(banner).toHaveTextContent('GATE-001')
  })

  it('lists earlier unreleased hold points from the server', async () => {
    const screen = await render(
      <ProceedBanner
        answer={answer({
          can_proceed: false,
          hold_points: [{ id: 9, code: 'ITP-001-02', title: 'Weld hold' }],
        })}
      />
    )
    await expect
      .element(screen.getByTestId('proceed-banner'))
      .toHaveTextContent('ITP-001-02 Weld hold')
  })

  it('says progress is allowed for an empty answer', async () => {
    const screen = await render(<ProceedBanner answer={answer({})} />)
    const banner = screen.getByTestId('proceed-banner')
    await expect.element(banner).toHaveAttribute('data-allowed', 'true')
    await expect.element(banner).toHaveTextContent('inspections.gates.proceed_yes')
  })
})

describe('LineLight', () => {
  it('shows the server state with its reason as the tooltip', async () => {
    const line = {
      gate_state: 'blocked',
      gate_satisfied: false,
      gate_reason: 'Waiting for hold ITP-001-02',
    } as unknown as ItpLine
    const screen = await render(<LineLight line={line} />)
    const light = screen.getByTestId('line-light')
    await expect.element(light).toHaveAttribute('data-state', 'blocked')
    expect(light.element().getAttribute('title')).toContain(
      'Waiting for hold ITP-001-02'
    )
  })
})
