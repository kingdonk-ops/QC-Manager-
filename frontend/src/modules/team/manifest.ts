import { lazy } from 'react'
import { Users } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'team',
  name: 'Teams',
  version: '0.1.0',
  routes: [
    {
      path: '/teams',
      component: lazy(() => import('./teams-page')),
      permission: 'team.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.teams',
      to: '/teams',
      icon: Users,
      group: 'admin',
      order: 10,
      permission: 'team.read',
    },
  ],
  messages: {
    en: {
      'nav.teams': 'Teams',
      'teams.title': 'Teams',
      'teams.description':
        'Teams linked to an Entra group take their members from it.',
      'teams.name': 'Team',
      'teams.members': 'Members',
      'teams.source': 'Members from',
      'teams.entra': 'Entra group',
      'teams.manual': 'This app',
      'teams.new': 'New team',
      'teams.group_id': 'Entra group object id (optional)',
      'teams.member': 'Name',
      'teams.email': 'Email',
      'teams.role': 'Role',
      'teams.pick': 'Select a team to see its members.',
      'teams.sync': 'Sync from Entra',
    },
  },
}
