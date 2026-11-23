import { lazy } from 'react'
import { HardHat } from 'lucide-react'
import type { ModuleManifest } from '../_types'
import { messages } from './messages'

export const manifest: ModuleManifest = {
  id: 'temporary_works',
  name: 'Temporary works',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/temporary-works',
      component: lazy(() => import('./temporary-works-page')),
      permission: 'temporary_works.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.temporary_works',
      to: '/temporary-works',
      icon: HardHat,
      group: 'quality_safety',
      order: 42,
      permission: 'temporary_works.read',
      accountTypes: ['staff'],
    },
  ],
  messages: { en: { ...messages } },
}
