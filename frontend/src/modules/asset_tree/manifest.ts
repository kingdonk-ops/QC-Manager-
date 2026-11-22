import { lazy } from 'react'
import { Network } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'asset_tree',
  name: 'Asset hierarchy',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/asset-tree',
      component: lazy(() => import('./asset-tree-page')),
      permission: 'asset_tree.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.asset_tree',
      to: '/asset-tree',
      icon: Network,
      group: 'assets',
      order: 5,
      permission: 'asset_tree.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.group.assets': 'Assets',
      'nav.asset_tree': 'Asset hierarchy',
    },
  },
}
