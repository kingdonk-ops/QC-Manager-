import { lazy } from 'react'
import { LayoutDashboard } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'overview',
  name: 'Overview',
  version: '0.1.0',
  backend: null,
  routes: [{ path: '/', component: lazy(() => import('./overview-page')) }],
  navItems: [
    {
      labelKey: 'nav.overview',
      to: '/',
      icon: LayoutDashboard,
      group: 'general',
      order: 0,
    },
  ],
  messages: {
    en: {
      'nav.overview': 'Overview',
      'overview.title': 'Welcome, {{name}}',
      'overview.projects': 'Your projects',
      'overview.teams': 'Your teams',
      'overview.none': 'Nothing yet.',
    },
  },
}
