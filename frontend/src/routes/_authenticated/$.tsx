import { createFileRoute } from '@tanstack/react-router'
import { ModuleOutlet } from '@/modules/_outlet'

/** Every path no file route claims is looked up in the module registry. */
export const Route = createFileRoute('/_authenticated/$')({
  component: ModuleOutlet,
})
