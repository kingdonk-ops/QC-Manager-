import { lazy } from 'react'
import { Mails } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'correspondence',
  name: 'Correspondence',
  version: '0.1.0',
  depends: ['projects', 'contacts'],
  routes: [
    {
      path: '/correspondence',
      component: lazy(() => import('./correspondence-page')),
      permission: 'correspondence.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.correspondence',
      to: '/correspondence',
      icon: Mails,
      group: 'documents',
      order: 10,
      permission: 'correspondence.read',
    },
  ],
  messages: {
    en: {
      'nav.correspondence': 'Correspondence',
      'correspondence.title': 'Correspondence',
      'correspondence.description':
        'Letters, emails, notices, instructions and claims in and out, threaded by reply, with response dates.',
      'correspondence.no_project': 'Choose a project in the top bar.',
      'correspondence.empty': 'No correspondence registered yet.',
    },
  },
}
