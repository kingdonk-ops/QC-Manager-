import { describe, expect, it } from 'vitest'
import { page } from 'vitest/browser'
import { render } from 'vitest-browser-react'
import '@/styles/index.css'
import { TemplatesLayout } from './templates-layout'

const box = (el: Element) => el.getBoundingClientRect()

describe('templates layout', () => {
  it('keeps the list column and the editor apart at 1440px, even with a wide toolbar and wide editor rows', async () => {
    await page.viewport(1440, 900)
    const screen = await render(
      <TemplatesLayout
        toolbar={
          <>
            <button>New template</button>
            <button>New ITP plan</button>
            <button>Add standard templates</button>
          </>
        }
        list={<button>Weld visual check</button>}
      >
        <form>
          <label htmlFor='name'>Name</label>
          <input id='name' />
          <div style={{ width: 2400 }}>a very wide item row</div>
        </form>
      </TemplatesLayout>
    )
    const list = screen.getByTestId('templates-list').element()
    const editor = screen.getByTestId('templates-editor').element()
    const input = screen.getByLabelText('Name').element()

    expect(box(list).width).toBeLessThanOrEqual(320)
    expect(box(editor).left).toBeGreaterThanOrEqual(box(list).right)
    expect(box(input).left).toBeGreaterThanOrEqual(box(list).right)
    // The toolbar wraps inside its own column instead of spilling over the editor.
    for (const b of screen.getByRole('button').elements())
      expect(box(b).right).toBeLessThanOrEqual(box(list).right + 0.5)
  })
})
