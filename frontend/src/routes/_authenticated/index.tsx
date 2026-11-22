import { createFileRoute } from '@tanstack/react-router'
import { ModuleOutlet } from '@/modules/_outlet'

export const Route = createFileRoute('/_authenticated/')({
  component: ModuleOutlet,
})
