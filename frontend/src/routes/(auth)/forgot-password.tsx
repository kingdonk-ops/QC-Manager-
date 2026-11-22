import { createFileRoute } from '@tanstack/react-router'
import { ForgotPassword } from '@/features/auth/recovery'

export const Route = createFileRoute('/(auth)/forgot-password')({
  component: ForgotPassword,
})
