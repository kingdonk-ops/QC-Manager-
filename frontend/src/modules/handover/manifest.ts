import { lazy } from 'react'
import { ArrowRightLeft } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'handover',
  name: 'Shift Handover',
  version: '0.1.0',
  depends: ['projects', 'notifications'],
  routes: [
    {
      path: '/handover',
      component: lazy(() => import('./handover-page')),
      permission: 'handover.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.handover',
      to: '/handover',
      icon: ArrowRightLeft,
      group: 'project_management',
      order: 31,
      permission: 'handover.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.handover': 'Shift Handover',
      'handover.title': 'Shift Handover',
      'handover.description':
        'What the incoming supervisor needs to know: open items, safety, permits, equipment and work in progress.',
      'handover.no_project': 'Choose a project in the top bar.',
      'handover.code': 'No.',
      'handover.date': 'Date',
      'handover.shift': 'Shift',
      'handover.area': 'Area',
      'handover.from': 'From',
      'handover.to': 'To',
      'handover.status': 'Status',
      'handover.open': 'Open items',
      'handover.waiting': 'Waiting',
      'handover.for_you': 'Handovers waiting for your acknowledgement',
      'handover.filter': 'Show',
      'handover.all': 'All handovers',
      'handover.to_me': 'Handed to me',
      'handover.from_me': 'Written by me',
      'handover.unacknowledged': 'Not yet acknowledged',
      'handover.new': 'New handover',
      'handover.from_shift': 'From shift',
      'handover.to_shift': 'To shift',
      'handover.whole_project': 'Whole project',
      'handover.incoming': 'Incoming supervisor',
      'handover.carry_help':
        'Items still open in this area’s last handover are brought across; edit them before you hand over.',
      'handover.start': 'Start handover',
    },
  },
}
