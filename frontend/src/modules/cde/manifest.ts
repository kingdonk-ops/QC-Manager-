import { lazy } from 'react'
import { Layers } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'cde',
  name: 'CDE',
  version: '0.1.0',
  depends: ['projects', 'files', 'notifications'],
  routes: [
    {
      path: '/cde',
      component: lazy(() => import('./cde-page')),
      permission: 'cde.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.cde',
      to: '/cde',
      icon: Layers,
      group: 'documents',
      order: 10,
      permission: 'cde.read',
    },
  ],
  messages: {
    en: {
      'nav.cde': 'Common Data Environment',
      'cde.title': 'Common Data Environment',
      'cde.description':
        'Information containers by ISO 19650 state: work in progress, shared, published and archived, with suitability codes and approvals.',
      'cde.empty': 'Nothing in this state.',
    },
  },
}
