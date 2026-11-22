import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  ArrowLeft,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  List,
  Plus,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import { useInspections } from './api'
import {
  type InspectionRequest,
  REQUEST_STATUSES,
  type RequestParty,
  formatWhen,
  localToIso,
  pointTone,
  useCalendar,
  useCreateRequest,
  useRequest,
  useRequestAction,
  useRequests,
} from './quality-api'

function startOfWeek(d: Date): Date {
  const out = new Date(d)
  out.setHours(0, 0, 0, 0)
  out.setDate(out.getDate() - ((out.getDay() + 6) % 7))
  return out
}

function NewRequest({
  projectId,
  onClose,
  onMade,
}: {
  projectId: number
  onClose: () => void
  onMade: (id: number) => void
}) {
  const { t } = useTranslation()
  const { data: records = [] } = useInspections(projectId, 'planned')
  const create = useCreateRequest()
  const callable = records.filter(
    (r) => r.kind === 'itp' || r.category === 'qa_itp'
  )
  const [draft, setDraft] = useState({
    title: '',
    start: '',
    duration: 60,
    discipline: '',
    location_ref: '',
    notes: '',
    ids: [] as number[],
    witness: null as number | null,
    recipients: [] as number[],
    contacts: '',
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>{t('inspections.new_request')}</DialogTitle>
          <DialogDescription>
            {t('inspections.new_request_help')}
          </DialogDescription>
        </DialogHeader>
        <form
          id='new-request'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                title: draft.title,
                scheduled_start: localToIso(draft.start),
                duration_minutes: draft.duration,
                discipline: draft.discipline || null,
                location_ref: draft.location_ref || null,
                notes: draft.notes || null,
                inspection_ids: draft.ids,
                parties: [
                  {
                    party: 'client',
                    witness_user_id: draft.witness,
                    recipient_user_ids: draft.recipients,
                    contact_ids: draft.contacts
                      .split(/[ ,]+/)
                      .map(Number)
                      .filter((n) => n > 0),
                  },
                ],
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onMade(made.id)
                },
              }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='req-title'>{t('inspections.title_col')}</Label>
            <Input
              id='req-title'
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </div>
          <div className='grid gap-3 sm:grid-cols-3'>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='req-start'>{t('inspections.scheduled')}</Label>
              <Input
                id='req-start'
                type='datetime-local'
                required
                value={draft.start}
                onChange={(e) => setDraft({ ...draft, start: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='req-duration'>{t('inspections.duration')}</Label>
              <Input
                id='req-duration'
                type='number'
                min={15}
                max={720}
                value={draft.duration}
                onChange={(e) =>
                  setDraft({ ...draft, duration: Number(e.target.value) })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='req-discipline'>
                {t('inspections.discipline')}
              </Label>
              <Input
                id='req-discipline'
                placeholder='M, C, CV'
                value={draft.discipline}
                onChange={(e) =>
                  setDraft({ ...draft, discipline: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='req-location'>{t('inspections.location')}</Label>
              <Input
                id='req-location'
                placeholder='Grid C4 / batch 7'
                value={draft.location_ref}
                onChange={(e) =>
                  setDraft({ ...draft, location_ref: e.target.value })
                }
              />
            </div>
          </div>
          <fieldset className='grid gap-1.5'>
            <legend className='text-sm font-medium'>
              {t('inspections.call_out')}
            </legend>
            <div className='max-h-48 overflow-y-auto rounded-md border p-2'>
              {callable.length ? (
                callable.map((r) => (
                  <label
                    key={r.id}
                    className='flex items-center gap-2 py-1 text-sm'
                  >
                    <input
                      type='checkbox'
                      checked={draft.ids.includes(r.id)}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          ids: e.target.checked
                            ? [...draft.ids, r.id]
                            : draft.ids.filter((x) => x !== r.id),
                        })
                      }
                    />
                    <span className='font-mono'>{r.code}</span> {r.title}
                    <span className='ms-auto text-xs text-muted-foreground'>
                      {r.anchor_label}
                    </span>
                  </label>
                ))
              ) : (
                <p className='text-sm text-muted-foreground'>
                  {t('inspections.nothing_to_call_out')}
                </p>
              )}
            </div>
          </fieldset>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label>{t('inspections.client_witness')}</Label>
              <UserSelect
                value={draft.witness}
                onChange={(id) => setDraft({ ...draft, witness: id })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label>{t('inspections.also_notify')}</Label>
              <UserSelect
                value={draft.recipients[0] ?? null}
                onChange={(id) =>
                  setDraft({ ...draft, recipients: id ? [id] : [] })
                }
              />
            </div>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='req-contacts'>
                {t('inspections.client_contacts')}
              </Label>
              <Input
                id='req-contacts'
                placeholder='12, 15'
                value={draft.contacts}
                onChange={(e) =>
                  setDraft({ ...draft, contacts: e.target.value })
                }
              />
            </div>
          </div>
          <Textarea
            aria-label={t('inspections.notes')}
            placeholder={t('inspections.notes')}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          />
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-request'
            disabled={create.isPending || !draft.ids.length || !draft.start}
          >
            {t('inspections.save_draft')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PartyLine({
  party,
  request,
}: {
  party: RequestParty
  request: InspectionRequest
}) {
  const { t } = useTranslation()
  const session = useSession()
  const act = useRequestAction(request.id)
  const open = ['requested', 'confirmed'].includes(request.status)
  const reviewer = can(session, 'inspections.review')
  const witness =
    party.witness_user_id === session.id ||
    party.recipients.some(
      (r) => r.user_id === session.id && r.on_behalf_of_user_id
    )
  const own =
    witness || (party.party === 'client' && can(session, 'inspections.respond'))
  const [waiver, setWaiver] = useState('')
  return (
    <div className='grid gap-2 rounded-md border p-3 text-sm'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='font-medium'>
          {t(`inspections.party.${party.party}`)}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-semibold ${pointTone(party.point)}`}
        >
          {party.point}
        </span>
        {party.witness_name ? (
          <span className='text-muted-foreground'>{party.witness_name}</span>
        ) : null}
        <span className='ms-auto flex flex-wrap gap-1'>
          <StatusBadge status={party.attendance} />
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-xs',
              party.notice_delivery === 'failed'
                ? 'bg-red-600 text-white'
                : party.notice_delivery === 'delivered'
                  ? 'bg-green-600 text-white'
                  : 'bg-muted'
            )}
          >
            {t(`inspections.delivery.${party.notice_delivery}`)}
          </span>
          {party.acknowledged ? (
            <span className='rounded bg-sky-600 px-1.5 py-0.5 text-xs text-white'>
              {t('inspections.acknowledged')}
            </span>
          ) : null}
        </span>
      </div>
      {party.recipients.length ? (
        <ul className='text-xs text-muted-foreground'>
          {party.recipients.map((r) => (
            <li key={r.id}>
              {r.name ?? `#${r.contact_id}`}
              {r.on_behalf_of_name
                ? ` (${t('inspections.on_behalf')} ${r.on_behalf_of_name})`
                : ''}{' '}
              · {t(`inspections.delivery.${r.delivery}`)}
              {r.delivery_reason ? ` (${r.delivery_reason})` : ''}
              {r.acknowledged_at
                ? ` · ${t('inspections.acknowledged')} ${formatWhen(r.acknowledged_at)}`
                : ''}
            </li>
          ))}
        </ul>
      ) : null}
      {open && party.external_hw ? (
        <div className='flex flex-wrap items-center gap-2'>
          {party.recipients.some((r) => r.user_id === session.id) ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => act.mutate({ action: 'acknowledge', body: {} })}
            >
              {t('inspections.acknowledge')}
            </Button>
          ) : null}
          {reviewer || witness ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() =>
                act.mutate({
                  action: 'attendance',
                  body: {
                    party: party.party as 'client',
                    attendance: 'attended',
                  },
                })
              }
            >
              {t('inspections.attended')}
            </Button>
          ) : null}
          {reviewer ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() =>
                act.mutate({
                  action: 'attendance',
                  body: {
                    party: party.party as 'client',
                    attendance: 'absent',
                  },
                })
              }
            >
              {t('inspections.absent')}
            </Button>
          ) : null}
          {own || (reviewer && party.point === 'W') ? (
            <>
              {!own ? (
                <Input
                  className='h-8 w-40'
                  placeholder={t('inspections.waiver_ref')}
                  value={waiver}
                  onChange={(e) => setWaiver(e.target.value)}
                />
              ) : null}
              <Button
                size='sm'
                variant='outline'
                disabled={!own && !waiver.trim()}
                onClick={() =>
                  act.mutate({
                    action: 'waive',
                    body: {
                      party: party.party as 'client',
                      waiver_ref: waiver || null,
                    },
                  })
                }
              >
                {t('inspections.waive')}
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function RequestDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: r } = useRequest(id)
  const act = useRequestAction(id)
  const [reason, setReason] = useState('')
  const [when, setWhen] = useState('')
  const [findings, setFindings] = useState<string[]>([])
  const creator = can(session, 'inspections.create')
  const reviewer = can(session, 'inspections.review')
  const done = (data: InspectionRequest) =>
    setFindings(data.findings.map((f) => String(f.message)))
  if (!r) return null
  const open = ['requested', 'confirmed'].includes(r.status)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {r.code ?? t('inspections.draft')} · {r.title}
          </DialogTitle>
          <DialogDescription>
            {formatWhen(r.scheduled_start)} → {formatWhen(r.scheduled_end)}
            {r.location_ref ? ` · ${r.location_ref}` : ''}
          </DialogDescription>
        </DialogHeader>
        <div className='flex flex-wrap items-center gap-2 text-sm'>
          <StatusBadge status={r.status} />
          {r.required_notice_hours ? (
            <span
              className={
                r.notice_met === false ? 'text-red-600' : 'text-green-700'
              }
            >
              {t('inspections.notice', { hours: r.required_notice_hours })}{' '}
              {r.notice_met === false
                ? t('inspections.notice_short')
                : r.notice_met
                  ? t('inspections.notice_met')
                  : ''}
            </span>
          ) : null}
          {r.reschedule_count ? (
            <span className='text-muted-foreground'>
              {t('inspections.rescheduled_n', { count: r.reschedule_count })}
            </span>
          ) : null}
        </div>
        {findings.length ? (
          <ul className='text-sm text-amber-600'>
            {findings.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        ) : null}
        <div className='grid gap-1 text-sm'>
          {r.inspections.map((i) => (
            <Link
              key={String(i.id)}
              to='/$'
              params={{ _splat: `inspections/${String(i.id)}` }}
              className='flex gap-2 hover:underline'
            >
              <span className='font-mono'>{String(i.code)}</span>
              {String(i.title)}
              <span className='ms-auto'>
                <StatusBadge status={String(i.status)} />
              </span>
            </Link>
          ))}
        </div>
        <div className='grid gap-2'>
          {r.parties.map((p) => (
            <PartyLine key={p.id} party={p} request={r} />
          ))}
        </div>
        <div className='grid gap-2 border-t pt-3'>
          {r.status === 'draft' && creator ? (
            <Button
              onClick={() =>
                act.mutate({ action: 'issue' }, { onSuccess: done })
              }
            >
              {t('inspections.issue')}
            </Button>
          ) : null}
          {r.status === 'requested' &&
          (can(session, 'inspections.respond') || reviewer) ? (
            <Button
              variant='outline'
              onClick={() =>
                act.mutate({
                  action: 'confirm',
                  body: { confirmation_ref: reason || null },
                })
              }
            >
              {t('inspections.confirm')}
            </Button>
          ) : null}
          {open && reviewer ? (
            <div className='flex flex-wrap gap-2'>
              <Button
                variant='outline'
                onClick={() =>
                  act.mutate({
                    action: 'outcome',
                    body: { outcome: 'witnessed' },
                  })
                }
              >
                {t('inspections.outcome.witnessed')}
              </Button>
              <Button
                variant='outline'
                onClick={() =>
                  act.mutate({
                    action: 'outcome',
                    body: { outcome: 'no_show' },
                  })
                }
              >
                {t('inspections.outcome.no_show')}
              </Button>
              <Button
                variant='outline'
                disabled={!reason.trim()}
                onClick={() =>
                  act.mutate({
                    action: 'outcome',
                    body: { outcome: 'failed', reason: reason.slice(0, 60) },
                  })
                }
              >
                {t('inspections.outcome.failed')}
              </Button>
            </div>
          ) : null}
          {r.status !== 'draft' &&
          ['requested', 'confirmed', 'no_show', 'failed'].includes(r.status) &&
          (creator || can(session, 'inspections.respond')) ? (
            <div className='flex flex-wrap items-end gap-2'>
              <Input
                type='datetime-local'
                className='w-56'
                aria-label={t('inspections.new_time')}
                value={when}
                onChange={(e) => setWhen(e.target.value)}
              />
              <Button
                variant='outline'
                disabled={!when || !reason.trim()}
                onClick={() =>
                  act.mutate(
                    {
                      action: 'reschedule',
                      body: { scheduled_start: localToIso(when), reason },
                    },
                    { onSuccess: done }
                  )
                }
              >
                {t('inspections.reschedule')}
              </Button>
            </div>
          ) : null}
          {['draft', 'requested', 'confirmed'].includes(r.status) && creator ? (
            <Button
              variant='ghost'
              disabled={r.status !== 'draft' && !reason.trim()}
              onClick={() =>
                act.mutate({
                  action: 'cancel',
                  body: { reason: reason || null },
                })
              }
            >
              {t('inspections.cancel_request')}
            </Button>
          ) : null}
          <Textarea
            aria-label={t('inspections.reason')}
            placeholder={t('inspections.reason_hint')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Calendar({
  projectId,
  onOpen,
}: {
  projectId: number
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const [week, setWeek] = useState(() => startOfWeek(new Date()))
  const end = useMemo(() => {
    const d = new Date(week)
    d.setDate(d.getDate() + 7)
    return d
  }, [week])
  const { data: events = [] } = useCalendar(
    projectId,
    week.toISOString(),
    end.toISOString()
  )
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(week)
    d.setDate(d.getDate() + i)
    return d
  })
  const shift = (n: number) => {
    const d = new Date(week)
    d.setDate(d.getDate() + n * 7)
    setWeek(d)
  }
  return (
    <div className='grid gap-2'>
      <div className='flex items-center gap-2'>
        <Button
          size='icon'
          variant='outline'
          aria-label={t('inspections.previous_week')}
          onClick={() => shift(-1)}
        >
          <ChevronLeft />
        </Button>
        <span className='text-sm font-medium'>
          {week.toLocaleDateString()} – {days[6].toLocaleDateString()}
        </span>
        <Button
          size='icon'
          variant='outline'
          aria-label={t('inspections.next_week')}
          onClick={() => shift(1)}
        >
          <ChevronRight />
        </Button>
      </div>
      <div className='grid gap-2 md:grid-cols-7'>
        {days.map((day) => {
          const mine = events.filter(
            (e) => new Date(e.start).toDateString() === day.toDateString()
          )
          return (
            <Card key={day.toISOString()} className='min-h-32'>
              <CardContent className='grid content-start gap-1 p-2'>
                <p className='text-xs font-medium text-muted-foreground'>
                  {day.toLocaleDateString(undefined, {
                    weekday: 'short',
                    day: 'numeric',
                    month: 'short',
                  })}
                </p>
                {mine.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => onOpen(e.id)}
                    className='grid gap-0.5 rounded border p-1 text-start text-xs hover:bg-muted'
                  >
                    <span className='flex items-center gap-1'>
                      <span
                        className={`rounded px-1 font-semibold ${pointTone(e.strongest_point)}`}
                      >
                        {e.strongest_point === 'none' ? '·' : e.strongest_point}
                      </span>
                      {new Date(e.start).toLocaleTimeString(undefined, {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                      <span className='font-mono'>{e.code ?? '—'}</span>
                    </span>
                    <span className='truncate'>{e.title}</span>
                    <span className='text-muted-foreground'>
                      {e.status.replace('_', ' ')}
                      {e.parties
                        .map(
                          (p) =>
                            ` · ${String(p.party)} ${String(p.attendance)}/${String(p.notice_delivery)}`
                        )
                        .join('')}
                    </span>
                  </button>
                ))}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function Requests({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [view, setView] = useState<'list' | 'calendar'>('list')
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)
  const { data: rows = [] } = useRequests(projectId, status)
  return (
    <div className='grid gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <Button
          size='sm'
          variant={view === 'list' ? 'default' : 'outline'}
          onClick={() => setView('list')}
        >
          <List /> {t('inspections.list')}
        </Button>
        <Button
          size='sm'
          variant={view === 'calendar' ? 'default' : 'outline'}
          onClick={() => setView('calendar')}
        >
          <CalendarDays /> {t('inspections.calendar')}
        </Button>
        {view === 'list' ? (
          <NativeSelect
            className='h-8 w-44'
            aria-label={t('inspections.status')}
            placeholder={t('inspections.all_statuses')}
            values={REQUEST_STATUSES}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          />
        ) : null}
        {can(session, 'inspections.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('inspections.new_request')}
          </Button>
        ) : null}
      </div>
      {view === 'calendar' ? (
        <Calendar projectId={projectId} onOpen={setOpenId} />
      ) : rows.length ? (
        <div className='grid gap-2'>
          {rows.map((r) => (
            <button
              key={r.id}
              onClick={() => setOpenId(r.id)}
              className='grid gap-2 rounded-md border p-3 text-start text-sm hover:bg-muted md:grid-cols-[100px_1fr_180px_120px_160px] md:items-center'
            >
              <span className='font-mono'>
                {r.code ?? t('inspections.draft')}
              </span>
              <span>
                <span className='font-medium'>{r.title}</span>
                <span className='block text-xs text-muted-foreground'>
                  {r.inspections.map((i) => String(i.code)).join(', ')}
                </span>
              </span>
              <span>{formatWhen(r.scheduled_start)}</span>
              <StatusBadge status={r.status} />
              <span className='flex flex-wrap gap-1'>
                {r.parties
                  .filter((p) => p.external_hw)
                  .map((p) => (
                    <span
                      key={p.id}
                      className={`rounded px-1.5 py-0.5 text-xs ${pointTone(p.point)}`}
                    >
                      {t(`inspections.party_short.${p.party}`)} {p.point} ·{' '}
                      {p.attendance}
                    </span>
                  ))}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_requests')}
        </p>
      )}
      {creating ? (
        <NewRequest
          projectId={projectId}
          onClose={() => setCreating(false)}
          onMade={setOpenId}
        />
      ) : null}
      {openId ? (
        <RequestDetail id={openId} onClose={() => setOpenId(null)} />
      ) : null}
    </div>
  )
}

export default function RequestsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.requests')}
      description={t('inspections.requests_description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      {project ? (
        <Requests key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_project')}
        </p>
      )}
    </Page>
  )
}
