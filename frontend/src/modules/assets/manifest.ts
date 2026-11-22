import { lazy } from 'react'
import { Boxes } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'assets',
  name: 'Asset Register',
  version: '0.1.0',
  depends: ['projects', 'contacts', 'files'],
  routes: [
    {
      path: '/assets',
      component: lazy(() => import('./assets-page')),
      permission: 'assets.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.assets',
      to: '/assets',
      icon: Boxes,
      group: 'assets',
      permission: 'assets.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.group.assets': 'Assets',
      'nav.assets': 'Asset Register',
      'assets.title': 'Asset register',
      'assets.description':
        'Facilities, floors and spaces, the product types and components installed in them, and the COBie handover workbook.',
    },
  },
}
