import { lazy } from 'react'
import { UserPlus } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'portal',
  name: 'Client Portal',
  version: '0.1.0',
  depends: ['team'],
  routes: [
    {
      path: '/portal/users',
      component: lazy(() => import('./external-users-page')),
      permission: 'portal.invite',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.portal_users',
      to: '/portal/users',
      icon: UserPlus,
      group: 'admin',
      order: 20,
      permission: 'portal.invite',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.portal_users': 'External users',
      'portal.title': 'External users',
      'portal.description':
        'Clients and partners sign in with an email and password. An invitation emails them a link to set it.',
      'portal.invite': 'Invite',
      'portal.name': 'Name',
      'portal.email': 'Email',
      'portal.teams': 'Teams',
      'portal.activated': 'Password set',
      'portal.resend': 'Resend',
    },
  },
}
