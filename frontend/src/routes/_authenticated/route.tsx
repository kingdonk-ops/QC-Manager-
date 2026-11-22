import { createFileRoute, redirect } from '@tanstack/react-router'
import { ApiError } from '@/api/client'
import { whoamiQuery } from '@/lib/session'
import { AuthenticatedLayout } from '@/components/layout/authenticated-layout'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.ensureQueryData(whoamiQuery)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: '/sign-in', search: { redirect: location.href } })
      }
      throw error
    }
  },
  component: AuthenticatedLayout,
})
