import { lazy } from 'react'
import { FolderOpen } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'files',
  name: 'Documents',
  version: '0.1.0',
  routes: [
    {
      path: '/documents',
      component: lazy(() => import('./documents-page')),
      permission: 'files.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.documents',
      to: '/documents',
      icon: FolderOpen,
      group: 'documents',
      order: 0,
      permission: 'files.read',
    },
  ],
  messages: {
    en: {
      'nav.documents': 'Documents',
      'documents.title': 'Documents',
      'documents.description':
        'Drawings, contracts, specifications and photos for the project. Upload a file with the same name to add a revision.',
    },
  },
}
