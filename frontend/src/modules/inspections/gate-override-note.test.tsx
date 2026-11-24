import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { GateOverrideNote, OverriddenGates } from './gate-override-note'
import { GateDecision, ProceedBanner } from './gates-panel'
import type { Gate, GateProceed } from './gates-api'

const gate = (over: Partial<Gate>) =>
  ({ number: 'GATE-001', status: 'pending', ...over }) as Gate

const answer = (over: Partial<GateProceed>): GateProceed => ({
  project_id: 1,
  attachment_kind: 'dossier',
  attachment_id: 5,
  can_proceed: true,
  gate_numbers: [],
  gate_ids: [],
  overridden_gate_numbers: [],
  overridden_gate_ids: [],
  hold_points: [],
  ...over,
})

describe('GateOverrideNote', () => {
  it('annotates a pending gate with the override reference', async () => {
    const screen = await render(
      <GateOverrideNote gate={gate({ override_ref: 'MDR-001-01' })} />
    )
    const note = screen.getByTestId('gate-override-note')
    await expect.element(note).toHaveTextContent('MDR-001-01')
    await expect
      .element(note)
      .toHaveTextContent('inspections.gates.overridden_note')
  })

  it('shows nothing on a gate with no override', async () => {
    const screen = await render(<GateOverrideNote gate={gate({})} />)
    expect(screen.getByTestId('gate-override-note').elements()).toHaveLength(0)
  })

  it('shows nothing once the gate is no longer pending', async () => {
    const screen = await render(
      <GateOverrideNote
        gate={gate({ status: 'released', override_ref: 'MDR-001-01' })}
      />
    )
    expect(screen.getByTestId('gate-override-note').elements()).toHaveLength(0)
  })

  it('is shown beside the decision area of a pending gate, which is still pending', async () => {
    const screen = await render(
      <GateDecision gate={gate({ override_ref: 'MDR-001-01' })} />
    )
    await expect
      .element(screen.getByTestId('gate-override-note'))
      .toBeInTheDocument()
  })
})

describe('can-proceed banner with overridden gates', () => {
  it('lists overridden gates apart from plain blocking ones', async () => {
    const screen = await render(
      <ProceedBanner
        answer={answer({
          can_proceed: false,
          attachment_kind: 'task',
          gate_numbers: ['GATE-003'],
          gate_ids: [3],
          overridden_gate_numbers: ['GATE-001', 'GATE-002'],
          overridden_gate_ids: [1, 2],
        })}
      />
    )
    const banner = screen.getByTestId('proceed-banner')
    await expect.element(banner).toHaveAttribute('data-allowed', 'false')
    await expect.element(banner).toHaveTextContent('GATE-003')
    await expect
      .element(screen.getByTestId('overridden-gates'))
      .toHaveTextContent('GATE-001, GATE-002')
    await expect
      .element(screen.getByTestId('overridden-gates'))
      .not.toHaveTextContent('GATE-003')
  })

  it('allows progress on a dossier whose only blockers are overridden, still listing them', async () => {
    const screen = await render(
      <ProceedBanner
        answer={answer({
          overridden_gate_numbers: ['GATE-001'],
          overridden_gate_ids: [1],
        })}
      />
    )
    await expect
      .element(screen.getByTestId('proceed-banner'))
      .toHaveAttribute('data-allowed', 'true')
    await expect
      .element(screen.getByTestId('overridden-gates'))
      .toHaveTextContent('GATE-001')
  })

  it('has no overridden line when none are covered', async () => {
    const screen = await render(<OverriddenGates answer={answer({})} />)
    expect(screen.getByTestId('overridden-gates').elements()).toHaveLength(0)
  })
})
