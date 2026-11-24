import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { OutcomeFields } from './outcome-fields'
import { NO_OUTCOME, type OutcomeState, outcomeBody } from './outcome-state'

describe('outcomeBody', () => {
  it('carries the conditional flag and a minor severity for a conditional pass', () => {
    expect(
      outcomeBody('pass', { ...NO_OUTCOME, conditional: true, measured: ' 52.5 ' })
    ).toEqual({
      conditional: true,
      measured_value: '52.5',
      report_severity: 'minor',
    })
  })

  it('never sends conditional with a fail, and defaults the severity to major', () => {
    expect(outcomeBody('fail', { ...NO_OUTCOME, conditional: true })).toEqual({
      conditional: false,
      measured_value: null,
      report_severity: 'major',
    })
  })

  it('sends no severity for a plain pass', () => {
    expect(outcomeBody('pass', NO_OUTCOME).report_severity).toBeNull()
  })

  it('keeps a severity the person chose', () => {
    expect(
      outcomeBody('pass', { conditional: true, measured: '', severity: 'critical' })
        .report_severity
    ).toBe('critical')
  })
})

function Harness({ result }: { result: 'pass' | 'fail' }) {
  const [state, setState] = useState<OutcomeState>(NO_OUTCOME)
  return <OutcomeFields result={result} value={state} onChange={setState} />
}

describe('OutcomeFields', () => {
  it('offers the conditional option for a pass and shows a minor severity once ticked', async () => {
    const screen = await render(<Harness result='pass' />)
    expect(
      screen.getByLabelText('inspections.criterion.report_severity').elements()
    ).toHaveLength(0)
    await screen.getByTestId('outcome-conditional').click()
    await expect
      .element(screen.getByLabelText('inspections.criterion.report_severity'))
      .toHaveValue('minor')
  })

  it('hides the conditional option for a fail and defaults the severity to major', async () => {
    const screen = await render(<Harness result='fail' />)
    expect(screen.getByTestId('outcome-conditional').elements()).toHaveLength(0)
    await expect
      .element(screen.getByLabelText('inspections.criterion.report_severity'))
      .toHaveValue('major')
  })
})
