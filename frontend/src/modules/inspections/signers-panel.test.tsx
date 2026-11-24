import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { AdditionalSignatoryDialog } from './countersign-dialog'
import { type SignatoryStatus, parseRequired } from './signatories-api'
import { LineSignerCount, RequiredField, SignersView } from './signers-panel'

const status = (over: Partial<SignatoryStatus>): SignatoryStatus => ({
  inspection_id: 7,
  required: 2,
  collected: 1,
  met: false,
  signers: [
    { user_id: 11, name: 'Ada Field', roles: ['inspector', 'additional_signatory'] },
  ],
  ...over,
})

describe('SignersView', () => {
  it('shows one collected of two required with one person listed once for two roles', async () => {
    const screen = await render(
      <SignersView status={status({})} canAdd={false} onAdd={vi.fn()} />
    )
    const count = screen.getByTestId('signers-count')
    await expect.element(count).toHaveAttribute('data-collected', '1')
    await expect.element(count).toHaveAttribute('data-required', '2')
    await expect
      .element(screen.getByTestId('signers-met'))
      .toHaveAttribute('data-met', 'false')
    await expect.element(screen.getByTestId('signer-row')).toBeInTheDocument()
    await expect
      .element(screen.getByTestId('signer-row'))
      .toHaveTextContent('Ada Field')
    await expect
      .element(screen.getByTestId('signer-row'))
      .toHaveTextContent('inspections.role.additional_signatory')
  })

  it('says the requirement is met once the server says so', async () => {
    const screen = await render(
      <SignersView
        status={status({
          collected: 2,
          met: true,
          signers: [
            { user_id: 11, name: 'Ada Field', roles: ['inspector'] },
            { user_id: 12, name: 'Bo Quality', roles: ['additional_signatory'] },
          ],
        })}
        canAdd={false}
        onAdd={vi.fn()}
      />
    )
    await expect
      .element(screen.getByTestId('signers-met'))
      .toHaveAttribute('data-met', 'true')
    await expect
      .element(screen.getByTestId('signer-row').first())
      .toBeInTheDocument()
  })

  it('stays compact for the default requirement of one', async () => {
    const screen = await render(
      <SignersView
        status={status({ required: 1, collected: 1, met: true })}
        canAdd={false}
        onAdd={vi.fn()}
      />
    )
    await expect.element(screen.getByTestId('signers-count')).toBeInTheDocument()
    expect(screen.getByTestId('signer-row').elements()).toHaveLength(0)
    expect(screen.getByTestId('signers-met').elements()).toHaveLength(0)
  })

  it('offers the additional-signatory action only when allowed', async () => {
    const hidden = await render(
      <SignersView status={status({})} canAdd={false} onAdd={vi.fn()} />
    )
    expect(hidden.getByTestId('signer-add').elements()).toHaveLength(0)
    await hidden.unmount()

    const onAdd = vi.fn()
    const shown = await render(
      <SignersView status={status({})} canAdd onAdd={onAdd} />
    )
    await shown.getByTestId('signer-add').click()
    expect(onAdd).toHaveBeenCalledOnce()
  })
})

describe('AdditionalSignatoryDialog', () => {
  it('sends the action only after the statement is accepted', async () => {
    const onSubmit = vi.fn()
    const screen = await render(
      <AdditionalSignatoryDialog
        name='Ada Field'
        code='ITP-001'
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )
    await expect.element(screen.getByTestId('signer-submit')).toBeDisabled()
    await screen.getByRole('checkbox').click()
    await expect.element(screen.getByTestId('signer-submit')).toBeEnabled()
    await screen.getByTestId('signer-submit').click()
    expect(onSubmit).toHaveBeenCalledOnce()
  })

  it("shows the server's refusal as it came", async () => {
    const screen = await render(
      <AdditionalSignatoryDialog
        name='Ada Field'
        code='ITP-001'
        error='You have already signed this line as an additional signatory.'
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )
    await expect
      .element(screen.getByTestId('signer-error'))
      .toHaveTextContent(
        'You have already signed this line as an additional signatory.'
      )
  })
})

describe('LineSignerCount', () => {
  it('shows nothing for a requirement of one', async () => {
    const screen = await render(<LineSignerCount required={1} collected={1} />)
    expect(screen.getByTestId('line-signers').elements()).toHaveLength(0)
  })

  it('shows collected over required above one', async () => {
    const screen = await render(<LineSignerCount required={3} collected={1} />)
    const note = screen.getByTestId('line-signers')
    await expect.element(note).toHaveAttribute('data-collected', '1')
    await expect.element(note).toHaveAttribute('data-required', '3')
  })
})

describe('RequiredField', () => {
  const label = 'inspections.signers.required_field'

  it('has a visible label and the allowed range as helper text tied to the input', async () => {
    const screen = await render(<RequiredField value={1} onChange={vi.fn()} />)
    await expect.element(screen.getByText(label)).toBeVisible()
    const input = screen.getByLabelText(label)
    await expect.element(input).toHaveAttribute('min', '1')
    await expect.element(input).toHaveAttribute('max', '10')
    const help = screen.getByTestId('required-help')
    await expect
      .element(help)
      .toHaveTextContent('inspections.signers.required_help')
    await expect
      .element(input)
      .toHaveAttribute('aria-describedby', help.element().id)
    expect(screen.getByRole('alert').elements()).toHaveLength(0)
  })

  it('shows the range error beside the label for an out-of-range value', async () => {
    const screen = await render(<RequiredField value={1} onChange={vi.fn()} />)
    const input = screen.getByLabelText(label)
    await input.fill('0')
    await expect.element(input).toHaveAttribute('aria-invalid', 'true')
    await expect
      .element(screen.getByRole('alert'))
      .toHaveTextContent('inspections.signers.required_range')
    await expect.element(screen.getByTestId('required-help')).toBeVisible()
  })

  it('flags a count outside one to ten and does not send it', async () => {
    const onChange = vi.fn()
    const screen = await render(<RequiredField value={1} onChange={onChange} />)
    await screen.getByLabelText(label).fill('11')
    await expect.element(screen.getByRole('alert')).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('sends a valid count and clears the error', async () => {
    const onChange = vi.fn()
    const screen = await render(<RequiredField value={1} onChange={onChange} />)
    await screen.getByLabelText(label).fill('0')
    await expect.element(screen.getByRole('alert')).toBeInTheDocument()
    await screen.getByLabelText(label).fill('3')
    expect(onChange).toHaveBeenLastCalledWith(3)
    expect(screen.getByRole('alert').elements()).toHaveLength(0)
  })

  it('treats an empty field as omitted, meaning one', async () => {
    const onChange = vi.fn()
    const screen = await render(<RequiredField value={4} onChange={onChange} />)
    await screen.getByLabelText(label).fill('')
    expect(onChange).toHaveBeenLastCalledWith(1)
    expect(screen.getByRole('alert').elements()).toHaveLength(0)
  })
})

describe('parseRequired', () => {
  it('accepts whole numbers from one to ten only', () => {
    expect(parseRequired('1')).toBe(1)
    expect(parseRequired(' 10 ')).toBe(10)
    expect(parseRequired('0')).toBeNull()
    expect(parseRequired('11')).toBeNull()
    expect(parseRequired('2.5')).toBeNull()
    expect(parseRequired('abc')).toBeNull()
    expect(parseRequired('')).toBeNull()
  })
})
