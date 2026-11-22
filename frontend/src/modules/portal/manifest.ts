import { lazy } from 'react'
import { ClipboardCheck, UserPlus } from 'lucide-react'
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
    {
      path: '/plan-reviews',
      component: lazy(() => import('./reviews-page')),
      permission: 'portal.read',
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
    {
      labelKey: 'nav.plan_reviews',
      to: '/plan-reviews',
      icon: ClipboardCheck,
      group: 'documents',
      permission: 'portal.read',
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
      'nav.plan_reviews': 'Plan reviews',
      'reviews.title': 'Client plan review',
      'reviews.queue': 'Plans to review',
      'reviews.description':
        'Share work plans, ITPs, method statements and schedules with the client and follow their decisions.',
      'reviews.client_description':
        'Plans shared with you for review. Approve, approve with comments or reject each document.',
      'reviews.no_project': 'Choose a project in the top bar.',
      'reviews.new': 'New review',
      'reviews.title_field': 'Title',
      'reviews.kind': 'Kind',
      'reviews.due': 'Due',
      'reviews.message': 'Message to the client',
      'reviews.documents': 'Documents',
      'reviews.save_draft': 'Save as draft',
      'reviews.share': 'Share with client',
      'reviews.withdraw': 'Withdraw',
      'reviews.add_document': 'Add document',
      'reviews.decision_comment': 'Comment (required unless approving)',
      'reviews.approve': 'Approve',
      'reviews.approve_with_comments': 'Approve with comments',
      'reviews.reject': 'Reject',
      'reviews.comments': 'Comments',
      'reviews.comment': 'Comment',
      'reviews.client': 'client',
      'reviews.on_document': 'On document',
      'reviews.whole_package': 'Whole package',
      'reviews.status': 'Status',
      'reviews.all': 'All',
      'reviews.decided': 'decided',
      'reviews.none': 'Nothing here yet.',
    },
  },
}
