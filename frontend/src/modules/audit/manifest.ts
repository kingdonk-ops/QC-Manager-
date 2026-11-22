import { lazy } from 'react'
import { ScrollText } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'audit',
  name: 'Audit ledger',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/admin/audit',
      component: lazy(() => import('./audit-page')),
      permission: 'audit.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.audit',
      to: '/admin/audit',
      icon: ScrollText,
      group: 'admin',
      order: 40,
      permission: 'audit.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.audit': 'Audit ledger',
      'audit.title': 'Audit ledger',
      'audit.description':
        'Every high-value action, append-only and hash-chained: each entry carries the hash of the one before it, so an edited or removed entry breaks the chain.',
      'audit.verify': 'Verify chain',
      'audit.intact': 'The chain is intact',
      'audit.intact_detail':
        '{{count}} entries checked from the first. Head hash {{head}}…',
      'audit.broken': 'The chain is broken at entry {{seq}}',
      'audit.when': 'When',
      'audit.actor': 'Actor',
      'audit.action': 'Action',
      'audit.entity': 'Entity',
      'audit.summary': 'Summary',
      'audit.change': 'Before → after',
      'audit.hash': 'Hash',
      'audit.entity_type': 'Entity type',
      'audit.entity_id': 'Entity id',
      'audit.action_prefix': 'Action (prefix)',
      'audit.any_actor': 'Any actor',
      'audit.from': 'From',
      'audit.to': 'To',
      'audit.search': 'Search summaries',
      'audit.count': '{{count}} entries',
      'audit.newer': 'Newer',
      'audit.older': 'Older',
    },
  },
}
