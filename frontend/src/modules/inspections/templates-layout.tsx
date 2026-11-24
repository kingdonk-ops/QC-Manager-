import type { ReactNode } from 'react'

/**
 * The templates page body: a fixed-width list column beside the editor. Both columns may shrink below their
 * content (so the toolbar wraps inside the list column and wide editor rows never push under the list), and the
 * list column never grows past 320px.
 */
export function TemplatesLayout({
  toolbar,
  list,
  children,
}: {
  toolbar?: ReactNode
  list: ReactNode
  children: ReactNode
}) {
  return (
    <div className='grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]'>
      <div
        data-testid='templates-list'
        className='grid min-w-0 content-start gap-2'
      >
        {toolbar ? <div className='flex flex-wrap gap-2'>{toolbar}</div> : null}
        {list}
      </div>
      <div data-testid='templates-editor' className='min-w-0'>
        {children}
      </div>
    </div>
  )
}
