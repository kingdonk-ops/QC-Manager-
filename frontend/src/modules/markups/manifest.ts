import { lazy } from 'react'
import { PenTool } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'markups',
  name: 'PDF Markups',
  version: '0.1.0',
  depends: ['projects', 'files'],
  routes: [
    {
      path: '/markups',
      component: lazy(() => import('./drawings-page')),
      permission: 'markups.read',
    },
    {
      path: '/markups/:fileId',
      component: lazy(() => import('./viewer-page')),
      permission: 'markups.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.markups',
      to: '/markups',
      icon: PenTool,
      group: 'documents',
      order: 10,
      permission: 'markups.read',
    },
  ],
  messages: {
    en: {
      'nav.markups': 'Markups',
      'markups.title': 'Drawing markups',
      'markups.description':
        'Open a PDF drawing to cloud, annotate, stamp and measure it. Everyone sees each other’s markup sets.',
      'markups.none':
        'No PDF drawings in this project yet. Upload them in Documents.',
    },
  },
}
