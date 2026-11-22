import { lazy } from 'react'
import { UserCog } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'people',
  name: 'Users',
  version: '0.1.0',
  depends: ['team'],
  routes: [
    {
      path: '/users',
      component: lazy(() => import('./users-page')),
      permission: 'people.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.users',
      to: '/users',
      icon: UserCog,
      group: 'admin',
      order: 5,
      permission: 'people.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.users': 'Users',
      'users.title': 'Users',
      'users.description':
        'Everyone who can sign in: staff from Entra ID and invited external users. Click a row to manage access.',
      'users.search': 'Search name, email or username',
      'users.show_inactive': 'Show deactivated',
      'users.invite': 'Invite external user',
      'users.name': 'Name',
      'users.email': 'Email',
      'users.type': 'Type',
      'users.sign_in': 'Sign-in',
      'users.roles': 'Roles',
      'users.teams': 'Teams',
      'users.status': 'Status',
    },
  },
}
