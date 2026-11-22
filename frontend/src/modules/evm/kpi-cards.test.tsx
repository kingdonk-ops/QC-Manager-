import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Metrics } from './api'
import { KpiCards } from './kpi-cards'

const total: Metrics = {
  bac: 1000,
  pv: 500,
  ev: 400,
  ac: 450,
  sv: -100,
  cv: -50,
  spi: 0.8,
  cpi: 0.9412,
  eac: 1062.5,
  etc: 612.5,
  vac: -62.5,
  tcpi: 1.0909,
  tcpi_eac: 0.98,
  percent_planned: 50,
  percent_complete: 40,
  productivity: 0.9412,
}

describe('KpiCards', () => {
  it('colours each index by its threshold', async () => {
    const { container } = await render(
      <KpiCards total={total} basis='hours' currency='AUD' />
    )
    const tones = Array.from(container.querySelectorAll('[data-tone]')).map(
      (el) => el.getAttribute('data-tone')
    )
    // SPI red, CPI amber, EAC amber, VAC amber, TCPI amber, progress uncoloured
    expect(tones).toEqual(['bad', 'warn', 'warn', 'warn', 'warn', 'none'])
    expect(container.textContent).toContain('0.80')
    expect(container.textContent).toContain('40.0%')
  })

  it('shows dashes when nothing has been recorded', async () => {
    const empty: Metrics = {
      ...total,
      ev: 0,
      ac: 0,
      spi: null,
      cpi: null,
      eac: null,
      etc: null,
      vac: null,
      tcpi_eac: null,
      productivity: null,
    }
    const { container } = await render(
      <KpiCards total={empty} basis='hours' currency='AUD' />
    )
    expect(container.querySelectorAll('[data-tone="none"]').length).toBe(5)
    expect(container.textContent).toContain('—')
  })
})
