import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { DeletedNotice, ReasonForm } from './draft-dialogs'

describe('ReasonForm', () => {
  it('keeps the button disabled until a reason is typed, then sends it trimmed', async () => {
    const onSubmit = vi.fn()
    const screen = await render(<ReasonForm onSubmit={onSubmit} />)
    await expect.element(screen.getByTestId('tw-return-submit')).toBeDisabled()
    await screen
      .getByLabelText('temporary_works.return.reason')
      .fill('  Design reissued  ')
    await expect.element(screen.getByTestId('tw-return-submit')).toBeEnabled()
    await screen.getByTestId('tw-return-submit').click()
    expect(onSubmit).toHaveBeenCalledWith('Design reissued')
  })

  it('stays disabled for a reason of spaces only', async () => {
    const screen = await render(<ReasonForm onSubmit={vi.fn()} />)
    await screen.getByLabelText('temporary_works.return.reason').fill('   ')
    await expect.element(screen.getByTestId('tw-return-submit')).toBeDisabled()
  })

  it('shows the server refusal as it came', async () => {
    const screen = await render(
      <ReasonForm refusal='already-draft: The item is already in draft.' onSubmit={vi.fn()} />
    )
    await expect
      .element(screen.getByTestId('tw-return-refusal'))
      .toHaveTextContent('already-draft: The item is already in draft.')
  })
})

describe('DeletedNotice', () => {
  it('says the record went to the recycle bin when the server says so', async () => {
    const screen = await render(
      <DeletedNotice result={{ message: 'ok', destination: 'bin' }} />
    )
    const notice = screen.getByTestId('tw-deleted-notice')
    await expect.element(notice).toHaveAttribute('data-destination', 'bin')
    await expect.element(notice).toHaveTextContent('temporary_works.deleted_to_bin')
  })

  it('says the record went to the Deleted folder when the server says so', async () => {
    const screen = await render(
      <DeletedNotice result={{ message: 'ok', destination: 'folder' }} />
    )
    await expect
      .element(screen.getByTestId('tw-deleted-notice'))
      .toHaveTextContent('temporary_works.deleted_to_folder')
  })
})
