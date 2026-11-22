import { lazy } from 'react'
import { Hash } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'numbering',
  name: 'Numbering schemes',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/numbering',
      component: lazy(() => import('./numbering-page')),
      permission: 'numbering.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.numbering',
      to: '/numbering',
      icon: Hash,
      group: 'documents',
      order: 80,
      permission: 'numbering.read',
      accountTypes: ['staff'],
      advancedOnly: true,
    },
  ],
  messages: {
    en: {
      'nav.numbering': 'Numbering schemes',
      'numbering.title': 'Numbering schemes',
      'numbering.description':
        'How documents, ITPs, transmittals and dossiers are numbered in this project. Numbers are never reused; revision and status are never part of a number.',
      'numbering.no_project': 'Choose a project to see its numbering.',
      'numbering.schemes': 'Schemes',
      'numbering.new': 'New scheme',
      'numbering.edit': 'Edit',
      'numbering.save': 'Save scheme',
      'numbering.empty':
        'No schemes yet: records use the default numbers (RFI-001, MDR-001 ...).',
      'numbering.kind': 'Record kind',
      'numbering.name': 'Name',
      'numbering.pattern': 'Pattern',
      'numbering.code_lists': 'Code lists',
      'numbering.code_lists_hint':
        'One code per line, optionally followed by its meaning. Leave a list empty to accept any short code. Tick "counter per" to run a separate sequence per code.',
      'numbering.counter_per': 'Counter per',
      'numbering.preview_value': 'Preview with code…',
      'numbering.start_value': 'Start at',
      'numbering.active': 'Active',
      'numbering.off': 'Off',
      'numbering.next_number': 'Next number',
      'numbering.rules':
        'Changing a scheme only affects new numbers. Numbers already handed out never change.',
      'numbering.allocate': 'Allocate number',
      'numbering.allocated_count': '{{count}} allocated',
      'numbering.register': 'Number register',
      'numbering.all_kinds': 'All kinds',
      'numbering.number': 'Number',
      'numbering.record': 'Record',
      'numbering.allocated_at': 'Allocated',
      'numbering.voided': 'Void',
      'numbering.void': 'Void',
      'numbering.void_reason': 'Why is this number void?',
    },
  },
}
