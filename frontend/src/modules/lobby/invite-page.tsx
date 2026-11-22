import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { useProjectStore } from '@/stores/project-store'
import { handleServerError } from '@/lib/handle-server-error'
import { useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Page } from '@/components/layout/page'
import { acceptInvite, forgetInvite, inviteToken, previewInvite } from './api'

export default function InvitePage() {
  const { t } = useTranslation()
  const session = useSession()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const [token] = useState(inviteToken)
  useEffect(() => {
    if (window.location.hash) history.replaceState(null, '', '/invite')
  }, [])
  const preview = useQuery({
    queryKey: ['lobby', 'invite', token],
    enabled: Boolean(token),
    retry: false,
    queryFn: () => previewInvite(token ?? ''),
  })
  const accept = useMutation({
    mutationFn: () => acceptInvite(token ?? ''),
    onSuccess: (joined) => {
      forgetInvite()
      void qc.invalidateQueries({ queryKey: ['projects'] })
      setProjectId(joined.project_id)
      void navigate({ to: '/' })
    },
    onError: handleServerError,
  })
  const p = preview.data
  return (
    <Page title={t('lobby.invite_title')}>
      {!token || preview.isError ? (
        <p className='text-sm text-muted-foreground'>
          {t('lobby.invite_invalid')}
        </p>
      ) : p ? (
        <div className='grid max-w-md gap-3 rounded-md border p-4'>
          <p>
            {t('lobby.invited_to')}{' '}
            <strong>
              {p.project_code} {p.project_name}
            </strong>
          </p>
          {p.for_you ? (
            <Button onClick={() => accept.mutate()} disabled={accept.isPending}>
              {t('lobby.join_project')}
            </Button>
          ) : (
            <p className='text-sm text-muted-foreground'>
              {t('lobby.wrong_account')} {p.email_hint} ({session.email})
            </p>
          )}
          <p className='text-xs text-muted-foreground'>
            {t('lobby.expires')} {new Date(p.expires_at).toLocaleString()}
          </p>
        </div>
      ) : null}
    </Page>
  )
}
