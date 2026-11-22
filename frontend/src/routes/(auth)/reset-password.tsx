import { z } from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { ResetPassword } from '@/features/auth/recovery'

export const Route = createFileRoute('/(auth)/reset-password')({
  component: ResetPassword,
  validateSearch: z.object({ token: z.string().optional() }),
})
