import { lazy } from 'react'
import { FolderKanban } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'projects',
  name: 'Projects',
  version: '0.1.0',
  depends: ['team'],
  routes: [
    { path: '/projects', component: lazy(() => import('./projects-page')) },
  ],
  navItems: [
    {
      labelKey: 'nav.projects',
      to: '/projects',
      icon: FolderKanban,
      group: 'general',
      order: 10,
    },
  ],
  messages: {
    en: {
      'nav.projects': 'Projects',
      'projects.title': 'Projects',
      'projects.description':
        'Every project you can see. Clients see the projects of their team.',
      'projects.new': 'New project',
      'projects.code': 'Code',
      'projects.name': 'Name',
      'projects.client': 'Client',
      'projects.location': 'Location',
      'projects.status': 'Status',
      'projects.currency': 'Currency',
      'projects.client_team': 'Client team',
    },
  },
}
