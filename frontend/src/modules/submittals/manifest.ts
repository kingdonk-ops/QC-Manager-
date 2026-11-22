import { lazy } from 'react'
import { FileCheck2 } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'submittals',
  name: 'Submittals',
  version: '0.1.0',
  depends: ['projects', 'contacts', 'files', 'notifications'],
  routes: [
    {
      path: '/submittals',
      component: lazy(() => import('./submittals-page')),
      permission: 'submittals.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.submittals',
      to: '/submittals',
      icon: FileCheck2,
      group: 'documents',
      order: 20,
      permission: 'submittals.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.submittals': 'Submittals',
      'submittals.title': 'Submittals',
      'submittals.description':
        'Shop drawings, product data and samples through their review workflow, with revisions and days outstanding.',
      'submittals.empty': 'No submittals yet.',
    },
  },
}
