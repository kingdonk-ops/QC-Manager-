import { useState } from 'react'
import { usePeople } from '@/modules/people/api'
import { useProjects } from '@/modules/projects/api'
import { History, Pencil, Plus, Send, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Schedule,
  type ScheduleIn,
  useDeleteSchedule,
  useRuns,
  useSaveSchedule,
  useSchedules,
  useSendNow,
  useTemplates,
} from './api'

const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

function when(s: Schedule) {
  if (s.cadence === 'daily') return `Daily at ${s.time_of_day}`
  if (s.cadence === 'weekly')
    return `${WEEKDAYS[s.weekday ?? 0]}s at ${s.time_of_day}`
  return `Monthly on day ${s.day_of_month} at ${s.time_of_day}`
}

function ScheduleDialog({
  schedule,
  onClose,
}: {
  schedule: Schedule | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: templates = [] } = useTemplates()
  const { data: projects = [] } = useProjects()
  const { data: people = [] } = usePeople(
    '',
    false,
    can(session, 'people.read')
  )
  const save = useSaveSchedule()
  const [draft, setDraft] = useState<ScheduleIn>(() => ({
    name: schedule?.name ?? '',
    template_id: schedule?.template_id ?? templates[0]?.id ?? 0,
    project_ids: schedule?.project_ids ?? [],
    cadence: (schedule?.cadence as ScheduleIn['cadence']) ?? 'weekly',
    weekday: schedule?.weekday ?? 0,
    day_of_month: schedule?.day_of_month ?? 1,
    time_of_day: schedule?.time_of_day ?? '07:00',
    timezone: schedule?.timezone ?? 'Australia/Perth',
    format: (schedule?.format as ScheduleIn['format']) ?? 'pdf',
    recipient_user_ids: schedule?.recipient_user_ids ?? [session.id],
    recipient_emails: schedule?.recipient_emails ?? [],
    enabled: schedule?.enabled ?? true,
  }))
  const [emails, setEmails] = useState(
    (schedule?.recipient_emails ?? []).join(', ')
  )
  const set = (patch: Partial<ScheduleIn>) => setDraft({ ...draft, ...patch })
  const toggle = (list: number[], id: number, on: boolean) =>
    on ? [...list, id] : list.filter((x) => x !== id)
  const templateId = draft.template_id || templates[0]?.id || 0

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {schedule ? schedule.name : t('reporting.new_schedule')}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-3 md:grid-cols-2'>
          <div className='grid gap-1'>
            <Label>{t('reporting.name')}</Label>
            <Input
              value={draft.name}
              onChange={(e) => set({ name: e.target.value })}
            />
          </div>
          <div className='grid gap-1'>
            <Label>{t('reporting.template')}</Label>
            <Select
              value={String(templateId)}
              onValueChange={(v) => set({ template_id: Number(v) })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {templates.map((tpl) => (
                  <SelectItem key={tpl.id} value={String(tpl.id)}>
                    {tpl.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='grid gap-1'>
            <Label>{t('reporting.cadence')}</Label>
            <Select
              value={draft.cadence}
              onValueChange={(v) =>
                set({ cadence: v as ScheduleIn['cadence'] })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='daily'>{t('reporting.daily')}</SelectItem>
                <SelectItem value='weekly'>{t('reporting.weekly')}</SelectItem>
                <SelectItem value='monthly'>
                  {t('reporting.monthly')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          {draft.cadence === 'weekly' ? (
            <div className='grid gap-1'>
              <Label>{t('reporting.weekday')}</Label>
              <Select
                value={String(draft.weekday ?? 0)}
                onValueChange={(v) => set({ weekday: Number(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {WEEKDAYS.map((d, i) => (
                    <SelectItem key={d} value={String(i)}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : draft.cadence === 'monthly' ? (
            <div className='grid gap-1'>
              <Label>{t('reporting.day_of_month')}</Label>
              <Input
                type='number'
                min={1}
                max={31}
                value={draft.day_of_month ?? 1}
                onChange={(e) =>
                  set({ day_of_month: Number(e.target.value) || 1 })
                }
              />
            </div>
          ) : (
            <div />
          )}
          <div className='grid gap-1'>
            <Label>{t('reporting.time')}</Label>
            <Input
              type='time'
              value={draft.time_of_day}
              onChange={(e) => set({ time_of_day: e.target.value })}
            />
          </div>
          <div className='grid gap-1'>
            <Label>{t('reporting.timezone')}</Label>
            <Input
              value={draft.timezone}
              onChange={(e) => set({ timezone: e.target.value })}
            />
          </div>
          <div className='grid gap-1'>
            <Label>{t('reporting.format')}</Label>
            <Select
              value={draft.format}
              onValueChange={(v) => set({ format: v as 'pdf' })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='pdf'>PDF</SelectItem>
                <SelectItem value='xlsx'>Excel</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <label className='flex items-end gap-2 pb-2 text-sm'>
            <Switch
              checked={draft.enabled}
              onCheckedChange={(enabled) => set({ enabled })}
            />
            {t('reporting.enabled')}
          </label>
        </div>
        <div className='grid gap-1'>
          <Label>{t('reporting.projects')}</Label>
          <div className='flex max-h-32 flex-wrap gap-x-4 gap-y-1 overflow-y-auto rounded-md border p-2'>
            {projects.map((p) => (
              <label key={p.id} className='flex items-center gap-1 text-sm'>
                <Checkbox
                  checked={draft.project_ids.includes(p.id)}
                  onCheckedChange={(on) =>
                    set({ project_ids: toggle(draft.project_ids, p.id, !!on) })
                  }
                />
                {p.code} {p.name}
              </label>
            ))}
          </div>
        </div>
        {people.length ? (
          <div className='grid gap-1'>
            <Label>{t('reporting.recipient_users')}</Label>
            <div className='flex max-h-32 flex-wrap gap-x-4 gap-y-1 overflow-y-auto rounded-md border p-2'>
              {people.map((u) => (
                <label key={u.id} className='flex items-center gap-1 text-sm'>
                  <Checkbox
                    checked={(draft.recipient_user_ids ?? []).includes(u.id)}
                    onCheckedChange={(on) =>
                      set({
                        recipient_user_ids: toggle(
                          draft.recipient_user_ids ?? [],
                          u.id,
                          !!on
                        ),
                      })
                    }
                  />
                  {u.name}
                </label>
              ))}
            </div>
          </div>
        ) : null}
        <div className='grid gap-1'>
          <Label>{t('reporting.recipient_emails')}</Label>
          <Textarea
            rows={2}
            placeholder='pm@example.com, client@example.com'
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={
              !draft.name || !draft.project_ids.length || save.isPending
            }
            onClick={() =>
              save.mutate(
                {
                  id: schedule?.id,
                  body: {
                    ...draft,
                    template_id: templateId,
                    recipient_emails: emails
                      .split(/[,;\s]+/)
                      .map((e) => e.trim())
                      .filter(Boolean),
                  },
                },
                { onSuccess: onClose }
              )
            }
          >
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Runs({ scheduleId }: { scheduleId: number }) {
  const { t } = useTranslation()
  const { data: runs = [] } = useRuns(scheduleId)
  if (!runs.length)
    return (
      <p className='text-xs text-muted-foreground'>{t('reporting.no_runs')}</p>
    )
  return (
    <table className='w-full text-xs'>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id} className='border-t'>
            <td className='py-1 pe-2 whitespace-nowrap'>
              {r.created_at ? new Date(r.created_at).toLocaleString() : ''}
            </td>
            <td className='pe-2'>
              <StatusBadge
                status={r.status === 'success' ? 'done' : 'failed'}
              />
            </td>
            <td className='pe-2'>{r.trigger}</td>
            <td className='text-muted-foreground'>{r.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function SchedulesPage() {
  const { t } = useTranslation()
  const session = useSession()
  const { data: schedules = [], isLoading } = useSchedules()
  const { data: projects = [] } = useProjects()
  const [editing, setEditing] = useState<Schedule | 'new' | null>(null)
  const [history, setHistory] = useState<number | null>(null)
  const send = useSendNow()
  const remove = useDeleteSchedule()
  const codes = new Map(projects.map((p) => [p.id, p.code]))

  return (
    <Page
      title={t('reporting.schedules')}
      description={t('reporting.schedules_description')}
      actions={
        can(session, 'reporting.create') ? (
          <Button size='sm' onClick={() => setEditing('new')}>
            <Plus /> {t('reporting.new_schedule')}
          </Button>
        ) : null
      }
    >
      {isLoading ? (
        <p className='text-sm text-muted-foreground'>{t('common.loading')}</p>
      ) : schedules.length === 0 ? (
        <p className='text-sm text-muted-foreground'>
          {t('reporting.no_schedules')}
        </p>
      ) : null}
      <div className='flex flex-col gap-3'>
        {schedules.map((s) => (
          <Card key={s.id} className='py-3'>
            <CardContent className='flex flex-col gap-2 px-4'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='font-medium'>{s.name}</span>
                <Badge variant='outline'>{s.template_name}</Badge>
                <Badge variant='secondary'>{s.format.toUpperCase()}</Badge>
                {!s.enabled ? (
                  <Badge variant='outline'>{t('reporting.paused')}</Badge>
                ) : null}
                {s.last_status ? (
                  <StatusBadge
                    status={s.last_status === 'success' ? 'done' : 'failed'}
                  />
                ) : null}
                <div className='ms-auto flex gap-1'>
                  {can(session, 'reporting.update') ? (
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={send.isPending}
                      onClick={() => send.mutate(s.id)}
                    >
                      <Send /> {t('reporting.send_now')}
                    </Button>
                  ) : null}
                  <Button
                    size='sm'
                    variant='ghost'
                    onClick={() => setHistory(history === s.id ? null : s.id)}
                  >
                    <History /> {t('reporting.history')}
                  </Button>
                  {can(session, 'reporting.update') ? (
                    <Button
                      size='sm'
                      variant='ghost'
                      onClick={() => setEditing(s)}
                    >
                      <Pencil />
                    </Button>
                  ) : null}
                  {can(session, 'reporting.delete') ? (
                    <Button
                      size='sm'
                      variant='ghost'
                      className='hover:text-red-600'
                      aria-label={t('reporting.delete')}
                      onClick={() => remove.mutate(s.id)}
                    >
                      <Trash2 />
                    </Button>
                  ) : null}
                </div>
              </div>
              <p className='text-sm text-muted-foreground'>
                {when(s)} ({s.timezone}) ·{' '}
                {s.project_ids
                  .map((id) => codes.get(id) ?? `#${id}`)
                  .join(', ')}{' '}
                · {s.recipient_user_ids.length + s.recipient_emails.length}{' '}
                {t('reporting.recipients')}
                {s.next_run_at
                  ? ` · ${t('reporting.next')} ${new Date(s.next_run_at).toLocaleString()}`
                  : ''}
              </p>
              {history === s.id ? <Runs scheduleId={s.id} /> : null}
            </CardContent>
          </Card>
        ))}
      </div>
      {editing ? (
        <ScheduleDialog
          schedule={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </Page>
  )
}
