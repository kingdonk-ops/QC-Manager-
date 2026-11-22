import { lazy } from 'react'
import { MessageSquareText } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'rfi',
  name: 'RFIs',
  version: '0.1.0',
  depends: ['projects', 'contacts', 'notifications', 'tasks'],
  routes: [
    {
      path: '/rfi',
      component: lazy(() => import('./rfi-page')),
      permission: 'rfi.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.rfi',
      to: '/rfi',
      icon: MessageSquareText,
      group: 'project_management',
      permission: 'rfi.read',
    },
  ],
  messages: {
    en: {
      'nav.rfi': 'RFIs',
      'rfi.title': 'Requests for Information',
      'rfi.description':
        'Questions to the designer, client or consultants: who holds the ball, what is overdue, and the answers.',
      'rfi.no_project': 'Choose a project in the top bar.',
      'rfi.empty': 'No RFIs yet.',
    },
  },
}
