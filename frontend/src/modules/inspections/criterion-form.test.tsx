import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { CriterionForm } from './criterion-form'

describe('CriterionForm', () => {
  it('shows the swap message and blocks saving a back-to-front range', async () => {
    const onSubmit = vi.fn()
    const screen = await render(<CriterionForm onSubmit={onSubmit} />)
    await screen.getByLabelText('inspections.criteria.code').fill('C-1')
    await screen.getByLabelText('inspections.criteria.title').fill('Gap')
    await screen.getByLabelText('inspections.criteria.rule_type').selectOptions('range')
    await screen.getByLabelText('inspections.criteria.lower').fill('20')
    await screen.getByLabelText('inspections.criteria.upper').fill('10')
    await expect.element(screen.getByTestId('criterion-swap')).toBeInTheDocument()
    await expect
      .element(screen.getByRole('button', { name: 'inspections.criteria.save' }))
      .toBeDisabled()
  })

  it('accepts equal limits and warns, without swapping, on a non-numeric lower limit', async () => {
    const onSubmit = vi.fn()
    const screen = await render(<CriterionForm onSubmit={onSubmit} />)
    await screen.getByLabelText('inspections.criteria.code').fill('C-2')
    await screen.getByLabelText('inspections.criteria.title').fill('Flat')
    await screen.getByLabelText('inspections.criteria.rule_type').selectOptions('range')
    await screen.getByLabelText('inspections.criteria.lower').fill('15')
    await screen.getByLabelText('inspections.criteria.upper').fill('15')
    expect(screen.getByTestId('criterion-swap').elements()).toHaveLength(0)
    await screen.getByLabelText('inspections.criteria.lower').fill('abc')
    await screen.getByLabelText('inspections.criteria.upper').fill('5')
    expect(screen.getByTestId('criterion-swap').elements()).toHaveLength(0)
    await expect.element(screen.getByTestId('criterion-warning')).toBeInTheDocument()
  })

  it('fills absolute limits from a nominal and its deviations', async () => {
    const screen = await render(<CriterionForm onSubmit={vi.fn()} />)
    await screen.getByLabelText('inspections.criteria.rule_type').selectOptions('range')
    await screen.getByLabelText('inspections.criteria.nominal').fill('1.1')
    await screen.getByLabelText('inspections.criteria.minus').fill('0.2')
    await screen.getByLabelText('inspections.criteria.plus').fill('0.2')
    await screen.getByTestId('criterion-fill').click()
    await expect
      .element(screen.getByLabelText('inspections.criteria.lower'))
      .toHaveValue('0.9')
    await expect
      .element(screen.getByLabelText('inspections.criteria.upper'))
      .toHaveValue('1.3')
  })

  it('shows the server message verbatim and keeps what was typed', async () => {
    const screen = await render(
      <CriterionForm
        onSubmit={vi.fn()}
        serverError='2 records are judged against this criterion. Create a new criterion.'
      />
    )
    await screen.getByLabelText('inspections.criteria.title').fill('Kept')
    await expect
      .element(screen.getByTestId('criterion-server-error'))
      .toHaveTextContent(
        '2 records are judged against this criterion. Create a new criterion.'
      )
    await expect
      .element(screen.getByLabelText('inspections.criteria.title'))
      .toHaveValue('Kept')
  })

  it('submits the typed fields with empty text as null', async () => {
    const onSubmit = vi.fn()
    const screen = await render(<CriterionForm onSubmit={onSubmit} />)
    await screen.getByLabelText('inspections.criteria.code').fill('C-3')
    await screen.getByLabelText('inspections.criteria.title').fill('Plain')
    await screen
      .getByRole('button', { name: 'inspections.criteria.save' })
      .click()
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        code: 'C-3',
        title: 'Plain',
        rule_type: 'free_text',
        lower_limit: null,
        description: null,
      })
    )
  })
})
