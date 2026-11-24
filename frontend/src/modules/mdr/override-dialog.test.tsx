import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Blocker,
  type Override,
  blockersOf,
  unoverridableOf,
} from './override-api'
import { GateCounts, OverrideDialog, OverrideHistory } from './override-dialog'

const blockers: Blocker[] = [
  { key: 'quality_gates', title: 'Quality gates', messages: ['GATE-001 pending'] },
  { key: 'open_issues', title: 'Open issues', messages: ['ISS-004 open'] },
]

const override = (over: Partial<Override>): Override => ({
  id: 1,
  dossier_id: 9,
  reference: 'MDR-001-01',
  purpose: 'review',
  reason: 'Client agreed to take the dossier early',
  severity: 'major',
  blockers: [],
  gate_numbers: ['GATE-001', 'GATE-002'],
  report_id: 40,
  report_code: 'NCR-012',
  created_by_id: 3,
  created_by_name: 'Manager One',
  ...over,
})

describe('OverrideDialog', () => {
  it('lists the blockers the server reported', async () => {
    const screen = await render(
      <OverrideDialog blockers={blockers} onSubmit={vi.fn()} onClose={vi.fn()} />
    )
    await expect
      .element(screen.getByTestId('override-blocker').first())
      .toHaveTextContent('Quality gates')
    await expect
      .element(screen.getByTestId('override-blockers'))
      .toHaveTextContent('ISS-004 open')
  })

  it('lists a check that can never be overridden as the reason, apart from the blockers it covers', async () => {
    const screen = await render(
      <OverrideDialog
        blockers={blockers}
        unoverridable={[
          {
            key: 'inspections_complete',
            title: 'Every inspection in scope is complete',
            messages: ['INS-007 in progress'],
          },
        ]}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    const cannot = screen.getByTestId('override-cannot')
    await expect.element(cannot).toHaveTextContent('mdr.override.cannot_title')
    await expect
      .element(cannot)
      .toHaveTextContent('Every inspection in scope is complete')
    await expect.element(cannot).toHaveTextContent('INS-007 in progress')
    // It is not listed among the blockers the override would cover.
    await expect
      .element(screen.getByTestId('override-blockers'))
      .not.toHaveTextContent('Every inspection in scope is complete')
  })

  it('disables Record override while a check that is never overridden fails, even with a reason', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <OverrideDialog
        blockers={blockers}
        unoverridable={[{ key: 'inspections_complete', title: 'Inspections', messages: [] }]}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )
    await screen.getByLabelText('mdr.override.reason').fill('Client agreed')
    await expect.element(screen.getByTestId('override-submit')).toBeDisabled()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows no refusal section and allows submit when every failing check can be overridden', async () => {
    const screen = await render(
      <OverrideDialog blockers={blockers} onSubmit={vi.fn()} onClose={vi.fn()} />
    )
    expect(screen.getByTestId('override-cannot').elements()).toHaveLength(0)
    await screen.getByLabelText('mdr.override.reason').fill('Client agreed')
    await expect.element(screen.getByTestId('override-submit')).toBeEnabled()
  })

  it('blocks submit and shows a message while the reason is empty', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <OverrideDialog blockers={blockers} onSubmit={onSubmit} onClose={vi.fn()} />
    )
    await expect.element(screen.getByTestId('override-submit')).toBeDisabled()
    await screen.getByLabelText('mdr.override.reason').fill('   ')
    await expect
      .element(screen.getByTestId('override-reason-error'))
      .toBeInTheDocument()
    await expect.element(screen.getByTestId('override-submit')).toBeDisabled()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends the trimmed reason with the default severity of major', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <OverrideDialog blockers={blockers} onSubmit={onSubmit} onClose={vi.fn()} />
    )
    await screen
      .getByLabelText('mdr.override.reason')
      .fill('  Client agreed on site  ')
    await screen.getByTestId('override-submit').click()
    expect(onSubmit).toHaveBeenCalledWith({
      reason: 'Client agreed on site',
      severity: 'major',
    })
  })

  it('sends the chosen severity', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <OverrideDialog blockers={blockers} onSubmit={onSubmit} onClose={vi.fn()} />
    )
    await screen.getByLabelText('mdr.override.severity').selectOptions('critical')
    await screen.getByLabelText('mdr.override.reason').fill('Urgent handover')
    await screen.getByTestId('override-submit').click()
    expect(onSubmit).toHaveBeenCalledWith({
      reason: 'Urgent handover',
      severity: 'critical',
    })
  })

  it("shows the server's refusal as it came", async () => {
    const screen = await render(
      <OverrideDialog
        blockers={blockers}
        error='The calibration check cannot be overridden.'
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await expect
      .element(screen.getByTestId('override-error'))
      .toHaveTextContent('The calibration check cannot be overridden.')
  })

  it('shows the raised documentation report and the covered holds after the override', async () => {
    const screen = await render(
      <OverrideDialog
        blockers={blockers}
        result={override({})}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await expect
      .element(screen.getByTestId('override-report'))
      .toHaveTextContent('NCR-012')
    await expect
      .element(screen.getByTestId('override-gates'))
      .toHaveTextContent('GATE-001, GATE-002')
  })
})

describe('GateCounts', () => {
  it('shows plain pending, overridden-pending and open report counts separately', async () => {
    const screen = await render(
      <GateCounts
        counts={{
          plain_pending_holds: 1,
          overridden_pending_holds: 2,
          open_reports: 3,
        }}
      />
    )
    await expect
      .element(screen.getByTestId('count-plain'))
      .toHaveAttribute('data-count', '1')
    await expect
      .element(screen.getByTestId('count-overridden'))
      .toHaveAttribute('data-count', '2')
    await expect
      .element(screen.getByTestId('count-reports'))
      .toHaveAttribute('data-count', '3')
  })

  it('leaves out a count the server did not give', async () => {
    const screen = await render(
      <GateCounts
        counts={{ plain_pending_holds: 0, overridden_pending_holds: null }}
      />
    )
    await expect
      .element(screen.getByTestId('count-plain'))
      .toHaveAttribute('data-count', '0')
    expect(screen.getByTestId('count-overridden').elements()).toHaveLength(0)
    expect(screen.getByTestId('count-reports').elements()).toHaveLength(0)
  })
})

describe('OverrideHistory', () => {
  it('lists each override with its reference, report and reason', async () => {
    const screen = await render(<OverrideHistory overrides={[override({})]} />)
    const entry = screen.getByTestId('override-entry')
    await expect.element(entry).toHaveTextContent('MDR-001-01')
    await expect.element(entry).toHaveTextContent('NCR-012')
    await expect
      .element(entry)
      .toHaveTextContent('Client agreed to take the dossier early')
  })

  it('shows nothing when there is no override', async () => {
    const screen = await render(<OverrideHistory overrides={[]} />)
    expect(screen.getByTestId('override-history').elements()).toHaveLength(0)
  })
})

describe('overridden check status', () => {
  it('renders as its own state, neither pass nor fail', async () => {
    const screen = await render(<StatusBadge status='overridden' />)
    const badge = screen.getByText('Overridden')
    await expect.element(badge).toBeInTheDocument()
    await expect.element(badge).toHaveClass('text-violet-700')
    await expect.element(badge).not.toHaveClass('text-green-700')
    await expect.element(badge).not.toHaveClass('text-red-700')
  })
})

describe('blockersOf and unoverridableOf', () => {
  const check = (
    key: string,
    over: Partial<Parameters<typeof blockersOf>[0][number]>
  ) => ({
    key,
    title: key.toUpperCase(),
    module: 'm',
    blocking: true,
    status: 'fail',
    overridable: true,
    findings: [],
    ...over,
  })
  const checks = [
    check('a', { findings: [{ message: 'x' }] }),
    check('b', { status: 'pass' }),
    check('c', { blocking: false }),
    check('d', { status: 'overridden', findings: [{ message: 'y' }] }),
    check('e', { overridable: false, findings: [{ message: 'z' }] }),
    check('f', { overridable: false, status: 'pass' }),
    check('g', { overridable: false, blocking: false }),
  ]

  it('takes only failing blocking checks an override may cover, with their findings', () => {
    expect(blockersOf(checks)).toEqual([
      { key: 'a', title: 'A', messages: ['x'] },
    ])
  })

  it('takes only failing blocking checks that can never be overridden', () => {
    expect(unoverridableOf(checks)).toEqual([
      { key: 'e', title: 'E', messages: ['z'] },
    ])
  })
})
