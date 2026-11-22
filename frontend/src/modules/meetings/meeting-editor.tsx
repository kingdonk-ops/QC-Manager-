import { useState } from 'react'
import {
  CheckCheck,
  FileDown,
  Mail,
  RotateCcw,
  Trash2,
  XCircle,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import { AgendaBuilder } from './agenda-builder'
import {
  type MeetingDetail,
  minutesPdfUrl,
  useDeleteMeeting,
  useIssueMinutes,
  useSetStatus,
  useUpdateMeeting,
} from './api'
import { formatWhen, toLocalInput } from './format'
import {
  ActionsPanel,
  AttendeesPanel,
  HistoryPanel,
  MinutesPanel,
  PreviousPanel,
} from './meeting-panels'

function Header({
  meeting,
  editable,
}: {
  meeting: MeetingDetail
  editable: boolean
}) {
  const { t } = useTranslation()
  const update = useUpdateMeeting(meeting.id)
  const [draft, setDraft] = useState({
    title: meeting.title,
    starts_at: toLocalInput(meeting.starts_at),
    duration_minutes: String(meeting.duration_minutes),
    location: meeting.location ?? '',
    online_link: meeting.online_link ?? '',
  })
  const set = (patch: Partial<typeof draft>) =>
    setDraft((d) => ({ ...d, ...patch }))
  return (
    <form
      className='grid gap-3 sm:grid-cols-2'
      onSubmit={(e) => {
        e.preventDefault()
        update.mutate(
          {
            title: draft.title,
            starts_at: new Date(draft.starts_at).toISOString(),
            duration_minutes: Number(draft.duration_minutes) || 60,
            location: draft.location || null,
            online_link: draft.online_link || null,
          },
          { onSuccess: () => toast.success(t('meetings.saved')) }
        )
      }}
    >
      <fieldset disabled={!editable} className='contents'>
        <div className='grid gap-1.5 sm:col-span-2'>
          <Label htmlFor='m-title'>{t('meetings.title_field')}</Label>
          <Input
            id='m-title'
            required
            maxLength={300}
            value={draft.title}
            onChange={(e) => set({ title: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='m-start'>{t('meetings.when')}</Label>
          <Input
            id='m-start'
            type='datetime-local'
            required
            value={draft.starts_at}
            onChange={(e) => set({ starts_at: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='m-duration'>{t('meetings.duration')}</Label>
          <Input
            id='m-duration'
            type='number'
            min={0}
            max={1440}
            value={draft.duration_minutes}
            onChange={(e) => set({ duration_minutes: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='m-location'>{t('meetings.location')}</Label>
          <Input
            id='m-location'
            maxLength={300}
            value={draft.location}
            onChange={(e) => set({ location: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='m-link'>{t('meetings.online_link')}</Label>
          <Input
            id='m-link'
            type='url'
            maxLength={500}
            value={draft.online_link}
            onChange={(e) => set({ online_link: e.target.value })}
          />
        </div>
      </fieldset>
      {editable ? (
        <Button type='submit' className='w-fit' disabled={update.isPending}>
          {t('common.save')}
        </Button>
      ) : null}
    </form>
  )
}

function StatusActions({
  meeting,
  onDeleted,
}: {
  meeting: MeetingDetail
  onDeleted: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const transition = can(session, 'meetings.transition')
  const status = useSetStatus(meeting.id)
  const issue = useIssueMinutes(meeting.id)
  const remove = useDeleteMeeting()
  const [confirming, setConfirming] = useState(false)
  const s = meeting.status
  return (
    <div className='flex flex-wrap items-center gap-2'>
      {transition && s === 'planned' ? (
        <>
          <Button size='sm' onClick={() => status.mutate('held')}>
            <CheckCheck /> {t('meetings.mark_held')}
          </Button>
          <Button
            size='sm'
            variant='outline'
            onClick={() => status.mutate('cancelled')}
          >
            <XCircle /> {t('meetings.cancel_meeting')}
          </Button>
        </>
      ) : null}
      {transition && (s === 'held' || s === 'cancelled') ? (
        <Button
          size='sm'
          variant='outline'
          onClick={() => status.mutate('planned')}
        >
          <RotateCcw /> {t('meetings.reopen')}
        </Button>
      ) : null}
      {transition && s === 'minutes_issued' ? (
        <Button
          size='sm'
          variant='outline'
          onClick={() => status.mutate('held')}
        >
          <RotateCcw /> {t('meetings.revise')}
        </Button>
      ) : null}
      {transition && (s === 'held' || s === 'minutes_issued') ? (
        <Button size='sm' onClick={() => setConfirming(true)}>
          <Mail /> {s === 'held' ? t('meetings.issue') : t('meetings.reissue')}
        </Button>
      ) : null}
      <Button size='sm' variant='outline' asChild>
        <a href={minutesPdfUrl(meeting.id)} download>
          <FileDown /> {t('meetings.pdf')}
        </a>
      </Button>
      {can(session, 'meetings.delete') ? (
        <Button
          size='sm'
          variant='ghost'
          className='ms-auto text-red-600'
          onClick={() => {
            if (window.confirm(t('meetings.confirm_delete')))
              remove.mutate(meeting.id, { onSuccess: onDeleted })
          }}
        >
          <Trash2 /> {t('meetings.delete')}
        </Button>
      ) : null}
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('meetings.issue_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('meetings.issue_body', {
                count: meeting.attendees?.filter((a) => a.email).length ?? 0,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                issue.mutate(undefined, {
                  onSuccess: (r) => {
                    toast.success(
                      t('meetings.issued', { count: r.emailed.length })
                    )
                    if (r.no_email?.length)
                      toast.warning(
                        t('meetings.not_emailed', {
                          names: r.no_email.join(', '),
                        })
                      )
                  },
                })
              }
            >
              {t('meetings.issue')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export function MeetingEditor({
  meeting,
  onClose,
}: {
  meeting: MeetingDetail
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'meetings.update')
  const tabs: Record<string, React.ReactNode> = {
    [t('meetings.agenda')]: (
      <AgendaBuilder meeting={meeting} editable={editable} />
    ),
    [t('meetings.attendees')]: (
      <AttendeesPanel meeting={meeting} editable={editable} />
    ),
    [t('meetings.minutes')]: (
      <MinutesPanel meeting={meeting} editable={editable} />
    ),
    [t('meetings.actions')]: (
      <ActionsPanel meeting={meeting} editable={editable} />
    ),
  }
  if (meeting.series_id)
    tabs[t('meetings.previous')] = (
      <PreviousPanel meeting={meeting} editable={editable} />
    )
  tabs[t('meetings.history')] = <HistoryPanel meetingId={meeting.id} />

  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={`${meeting.code} ${meeting.title}`}
      subtitle={
        <>
          {formatWhen(meeting.starts_at)}
          {meeting.series_name ? ` · ${meeting.series_name}` : ''}
        </>
      }
      badges={<StatusBadge status={meeting.status} />}
      record={{
        projectId: meeting.project_id,
        entityType: 'meeting',
        entityId: meeting.id,
      }}
      tabs={tabs}
    >
      <div className='grid gap-5'>
        <StatusActions meeting={meeting} onDeleted={onClose} />
        <Header key={meeting.id} meeting={meeting} editable={editable} />
      </div>
    </RecordSheet>
  )
}
