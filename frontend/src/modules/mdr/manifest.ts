import { lazy } from 'react'
import { BookCheck } from 'lucide-react'
import type { ModuleManifest } from '../_types'
import { overrideMessages } from './override-messages'

export const manifest: ModuleManifest = {
  id: 'mdr',
  name: 'MDR / turnover dossiers',
  version: '0.1.0',
  depends: ['projects', 'files', 'asset_tree'],
  routes: [
    {
      path: '/mdr',
      component: lazy(() => import('./mdr-page')),
      permission: 'mdr.read',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.mdr',
      to: '/mdr',
      icon: BookCheck,
      group: 'documents',
      order: 60,
      permission: 'mdr.read',
    },
  ],
  messages: {
    en: {
      ...overrideMessages,
      'nav.mdr': 'MDR dossiers',
      'mdr.title': 'MDR / turnover dossiers',
      'mdr.description':
        'Build the turnover dossier for part of the asset tree: pick the scope and sections, check readiness, compile a draft, then issue, sign and hand over.',
      'mdr.no_project': 'Choose a project to see its dossiers.',
      'mdr.new': 'New dossier',
      'mdr.new_hint':
        'Scope and sections are set on the dossier afterwards. It is numbered by the project numbering scheme for "mdr" if there is one.',
      'mdr.create': 'Create',
      'mdr.code': 'Number',
      'mdr.title_field': 'Title',
      'mdr.description_field': 'Description',
      'mdr.status': 'Status',
      'mdr.scope': 'Scope',
      'mdr.whole_project': 'Whole project',
      'mdr.scope_no_tree': 'This project has no asset hierarchy yet.',
      'mdr.collections': 'Collections',
      'mdr.sections': 'Sections (in print order)',
      'mdr.not_available': 'Not available',
      'mdr.up': 'Move up',
      'mdr.down': 'Move down',
      'mdr.save_outline': 'Save scope and sections',
      'mdr.readiness': 'Readiness',
      'mdr.purpose': 'Issue purpose',
      'mdr.for_review': 'For client review',
      'mdr.for_final': 'Final (Rev 0)',
      'mdr.advisory': 'advisory',
      'mdr.compile_draft': 'Compile draft',
      'mdr.issue_review': 'Issue for review',
      'mdr.issue_final': 'Issue final',
      'mdr.reissue_final': 'Re-issue final',
      'mdr.revisions': 'Revisions',
      'mdr.history': 'History',
      'mdr.draft': 'Draft',
      'mdr.pages': '{{count}} pages',
      'mdr.download': 'Download',
      'mdr.compiled_by': 'Compiled by {{name}}',
      'mdr.signed_by': 'Signed by {{name}} {{at}}',
      'mdr.decided_by': '{{decision}} by {{name}}',
      'mdr.sign': 'Sign',
      'mdr.sign_title': 'Sign Rev {{rev}}',
      'mdr.sign_hint':
        'Your attestation is added as the last page; the SHA-256 of the signed file is recorded with the revision and in the audit ledger.',
      'mdr.accept': 'Accept',
      'mdr.reject': 'Reject',
      'mdr.reject_note': 'Why is this revision rejected?',
      'mdr.no_revisions': 'Nothing compiled yet.',
      'mdr.check_copy': 'Check a copy',
      'mdr.check_copy_hint':
        'Pick a PDF you hold: its SHA-256 is computed in your browser (the file is not uploaded) and compared with the stored revisions.',
      'mdr.copy_matches': 'Matches Rev {{rev}} ({{signed}}).',
      'mdr.copy_differs':
        'This copy matches no stored version of this dossier.',
      'mdr.signed': 'signed',
      'mdr.unsigned': 'before signing',
    },
  },
}
