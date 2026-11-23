import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { Breach } from './api'
import { HeadlineFigures } from './headline-figures'
import { SafetyBanners } from './safety-banners'

const breach = (id: number, reason: string): Breach => ({
  item_id: id,
  reference: `TW-${id}`,
  title: `Item ${id}`,
  reason,
})

describe('SafetyBanners', () => {
  it('leads with the breach banner, its count and the reason of each item', async () => {
    const screen = await render(
      <SafetyBanners
        breaches={[breach(1, 'In use on 2026-03-02 with no valid permit to load')]}
        overdueToLoad={0}
        overdueToStrike={0}
      />
    )
    const banner = screen.getByTestId('breach-banner')
    await expect.element(banner).toHaveAttribute('data-count', '1')
    await expect
      .element(screen.getByTestId('breach-reason'))
      .toHaveTextContent('In use on 2026-03-02 with no valid permit to load')
    await expect
      .element(screen.getByTestId('breach-reason'))
      .toHaveTextContent('TW-1')
    expect(screen.getByTestId('no-breach-banner').elements()).toHaveLength(0)
  })

  it('shows the reassurance banner instead when there is no breach', async () => {
    const screen = await render(
      <SafetyBanners breaches={[]} overdueToLoad={0} overdueToStrike={0} />
    )
    await expect
      .element(screen.getByTestId('no-breach-banner'))
      .toBeInTheDocument()
    expect(screen.getByTestId('breach-banner').elements()).toHaveLength(0)
  })

  it('mentions only the overdue-to-load count when the strike count is zero', async () => {
    const screen = await render(
      <SafetyBanners breaches={[]} overdueToLoad={2} overdueToStrike={0} />
    )
    await expect.element(screen.getByTestId('overdue-load')).toBeInTheDocument()
    expect(screen.getByTestId('overdue-strike').elements()).toHaveLength(0)
  })

  it('hides the secondary banner when both overdue counts are zero', async () => {
    const screen = await render(
      <SafetyBanners breaches={[]} overdueToLoad={0} overdueToStrike={0} />
    )
    expect(screen.getByTestId('overdue-banner').elements()).toHaveLength(0)
  })
})

describe('HeadlineFigures', () => {
  it('shows the four figures with a dash for an absent clearance', async () => {
    const screen = await render(
      <HeadlineFigures total={4} clearance={null} bearingLoad={3} breaches={0} />
    )
    await expect
      .element(screen.getByTestId('figure-items'))
      .toHaveTextContent('4')
    await expect
      .element(screen.getByTestId('figure-clearance'))
      .toHaveTextContent('—')
    await expect
      .element(screen.getByTestId('figure-bearing-load'))
      .toHaveTextContent('3')
    await expect
      .element(screen.getByTestId('figure-breaches'))
      .toHaveAttribute('data-tone', 'none')
  })

  it('gives the breaches figure the error tone above zero and shows the percentage', async () => {
    const screen = await render(
      <HeadlineFigures
        total={4}
        clearance='50.00'
        bearingLoad={1}
        breaches={1}
      />
    )
    await expect
      .element(screen.getByTestId('figure-breaches'))
      .toHaveAttribute('data-tone', 'bad')
    await expect
      .element(screen.getByTestId('figure-clearance'))
      .toHaveTextContent('50.00%')
  })
})
