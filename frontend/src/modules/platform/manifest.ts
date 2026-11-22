import { lazy } from 'react'
import { Blocks } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'platform',
  name: 'Platform',
  version: '0.1.0',
  routes: [
    {
      path: '/admin/modules',
      component: lazy(() => import('./modules-page')),
      permission: 'platform.modules',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.modules',
      to: '/admin/modules',
      icon: Blocks,
      group: 'admin',
      order: 30,
      permission: 'platform.modules',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.modules': 'Modules',
      'modules.title': 'Modules',
      'modules.description':
        'Switch modules on or off for everyone. A module switched off disappears from menus and its API answers 404; its data is kept for when you switch it back on.',
    },
  },
}
