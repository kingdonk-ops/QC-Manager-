import { Suspense } from 'react'
import { useLocation } from '@tanstack/react-router'
import { ForbiddenError } from '@/features/errors/forbidden'
import { NotFoundError } from '@/features/errors/not-found-error'
import { ModuleParamsContext, useResolvedRoute } from './_runtime'

/** Shows the registered module page for the current path. */
export function ModuleOutlet() {
  const { pathname } = useLocation()
  const resolved = useResolvedRoute(pathname)

  if (resolved.kind === 'missing') return <NotFoundError />
  if (resolved.kind === 'forbidden') return <ForbiddenError />

  const Page = resolved.route.component
  return (
    <ModuleParamsContext.Provider value={resolved.params}>
      <Suspense
        fallback={<div className='p-6 text-sm text-muted-foreground'>…</div>}
      >
        <Page />
      </Suspense>
    </ModuleParamsContext.Provider>
  )
}
