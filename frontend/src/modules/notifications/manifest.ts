import { lazy } from 'react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'notifications',
  name: 'Notifications',
  version: '0.1.0',
  routes: [
    {
      path: '/notifications',
      component: lazy(() => import('./notifications-page')),
    },
  ],
  messages: { en: { 'notifications.title': 'Notifications' } },
}
