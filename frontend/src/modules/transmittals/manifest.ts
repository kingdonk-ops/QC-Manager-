import { lazy } from 'react'
import { Send } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'transmittals',
  name: 'Transmittals',
  version: '0.1.0',
  depends: ['projects', 'contacts', 'files'],
  routes: [
    {
      path: '/transmittals',
      component: lazy(() => import('./transmittals-page')),
      permission: 'transmittals.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.transmittals',
      to: '/transmittals',
      icon: Send,
      group: 'documents',
      order: 20,
      permission: 'transmittals.read',
    },
  ],
  messages: {
    en: {
      'nav.transmittals': 'Transmittals',
      'transmittals.title': 'Transmittals',
      'transmittals.description':
        'Issue project documents to contacts with a cover sheet, and track who has received and acknowledged them.',
      'transmittals.no_project': 'Choose a project in the top bar.',
      'transmittals.empty': 'No transmittals yet.',
    },
  },
}
