import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import type { RiskMatrix } from './api'
import { HeatMap } from './heat-map'

const impacts = ['low', 'medium', 'high', 'critical']
const bands = [
  { key: 'rare', label: 'Rare', min: '0.1', max: '0.2' },
  { key: 'unlikely', label: 'Unlikely', min: '0.3', max: '0.4' },
  { key: 'possible', label: 'Possible', min: '0.5', max: '0.5' },
  { key: 'likely', label: 'Likely', min: '0.6', max: '0.7' },
  { key: 'almost_certain', label: 'Almost certain', min: '0.8', max: '0.9' },
]

const matrix = {
  project_id: 1,
  currency: 'AUD',
  bands,
  impacts,
  cells: bands.flatMap((b) =>
    impacts.map((i) => ({
      band: b.key,
      impact: i,
      count: b.key === 'likely' && i === 'high' ? 2 : 0,
      exposure: b.key === 'likely' && i === 'high' ? '35000.00' : '0',
    }))
  ),
  total_exposure: '35000.00',
  total_residual_exposure: '35000.00',
  total_schedule_days: 0,
  count: 2,
  open_count: 2,
  high_critical_count: 2,
  by_category: [],
  top: [],
} as unknown as RiskMatrix

describe('HeatMap', () => {
  it('shows a cell per band and impact, and selects one on click', async () => {
    const onSelect = vi.fn()
    const screen = await render(
      <HeatMap
        matrix={matrix}
        onSelect={onSelect}
        format={(v) => `$${Number(v)}`}
      />
    )

    await expect.element(screen.getByText('Almost certain')).toBeInTheDocument()
    expect(screen.getByRole('button').elements()).toHaveLength(20)

    const busy = screen.getByRole('button', { name: /2\s*\$35000/ })
    await busy.click()
    expect(onSelect).toHaveBeenCalledWith({ band: 'likely', impact: 'high' })
  })

  it('clears the filter when the selected cell is clicked again', async () => {
    const onSelect = vi.fn()
    const screen = await render(
      <HeatMap
        matrix={matrix}
        selected={{ band: 'likely', impact: 'high' }}
        onSelect={onSelect}
        format={(v) => `$${Number(v)}`}
      />
    )
    await screen.getByRole('button', { pressed: true }).click()
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })
})
