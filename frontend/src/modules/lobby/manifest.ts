import { lazy } from 'react'
import { DoorOpen, KeyRound } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'lobby',
  name: 'Project lobby',
  version: '0.1.0',
  depends: ['projects', 'portal'],
  routes: [
    { path: '/lobby', component: lazy(() => import('./lobby-page')) },
    { path: '/invite', component: lazy(() => import('./invite-page')) },
    {
      path: '/lobby/requests',
      component: lazy(() => import('./access-page')),
      permission: 'projects.manage_access',
    },
  ],
  navItems: [
    {
      labelKey: 'nav.lobby',
      to: '/lobby',
      icon: DoorOpen,
      group: 'general',
      order: 90,
    },
    {
      labelKey: 'nav.project_access',
      to: '/lobby/requests',
      icon: KeyRound,
      group: 'admin',
      order: 25,
      permission: 'projects.manage_access',
    },
  ],
  messages: {
    en: {
      'nav.lobby': 'Join a project',
      'nav.project_access': 'Project access',
      'lobby.title': 'Project lobby',
      'lobby.description':
        'Projects you can ask to join, and projects you have been invited to.',
      'lobby.request': 'Request access',
      'lobby.request_again': 'Request again',
      'lobby.request_again_from': 'Request again from',
      'lobby.message': 'Message to the project admins (optional)',
      'lobby.send': 'Send request',
      'lobby.join': 'Join',
      'lobby.joined': 'You joined',
      'lobby.open': 'Open project',
      'lobby.withdraw': 'Withdraw',
      'lobby.none_internal':
        'No projects are listed in the lobby. Enter a project code if you know one.',
      'lobby.none_external':
        'You have no pending invitations. Ask the project team to invite you.',
      'lobby.code': 'Project code',
      'lobby.find': 'Find',
      'lobby.active_requests': 'Your requests',
      'lobby.no_requests': 'No requests.',
      'lobby.access_title': 'Project access',
      'lobby.access_description':
        'Decide access requests, list the project in the lobby, and invite people by link.',
      'lobby.requests': 'Access requests',
      'lobby.status': 'Status',
      'lobby.approve': 'Approve',
      'lobby.reject': 'Reject',
      'lobby.reason': 'Reason (shown to the requester)',
      'lobby.listed': 'Listed in the lobby for company staff',
      'lobby.invite': 'Invite someone',
      'lobby.email': 'Email',
      'lobby.name_if_new': 'Name (for a new account)',
      'lobby.send_invite': 'Send invite',
      'lobby.copy': 'Copy link',
      'lobby.copied': 'Link copied',
      'lobby.pending_invites': 'Pending invites',
      'lobby.resend': 'Re-send',
      'lobby.revoke': 'Revoke',
      'lobby.members': 'People given access',
      'lobby.client_team': 'client team',
      'lobby.direct': 'project member',
      'lobby.invite_title': 'Project invitation',
      'lobby.invite_invalid':
        'This invite link is no longer valid: it was used, replaced, revoked or has expired.',
      'lobby.invited_to': 'You are invited to',
      'lobby.join_project': 'Join project',
      'lobby.wrong_account': 'This invite is for',
      'lobby.expires': 'Link expires',
      'project.browse': 'Browse / join another project',
    },
  },
}
