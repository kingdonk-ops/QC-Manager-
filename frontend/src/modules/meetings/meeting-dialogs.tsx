import { useState } from 'react'
import { useContactNames } from '@/modules/contacts/api'
import { useAssignees } from '@/modules/tasks/api'
import { ArrowDown, ArrowUp, Plus, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { statusLabel } from '@/components/records/status'
import {
  type MeetingDetail,
  type Person,
  type Series,
  type SeriesIn,
  useCreateMeeting,
  useDeleteSeries,
  useSaveSeries,
  useSeries,
} from './api'
import { PersonPicker } from './person-picker'

const NO_SERIES = 'none'
const CADENCES = ['weekly', 'fortnightly', 'monthly'] as const

function nextSlot(series?: Series) {
  const day = series?.next_date ?? new Date().toISOString().slice(0, 10)
  return `${day}T09:00`
}

export function NewMeetingDialog({
  projectId,
  onCreated,
  onClose,
}: {
  projectId: number
  onCreated: (meeting: MeetingDetail) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { data: allSeries = [] } = useSeries(projectId)
  const series = allSeries.filter((s) => s.active)
  const create = useCreateMeeting()
  const [seriesId, setSeriesId] = useState<number | null>(null)
  const chosen = series.find((s) => s.id === seriesId)
  const [draft, setDraft] = useState({
    title: '',
    starts_at: nextSlot(),
    duration_minutes: '',
    location: '',
    online_link: '',
    copy_template: true,
  })
  const set = (patch: Partial<typeof draft>) =>
    setDraft((d) => ({ ...d, ...patch }))

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('meetings.new')}</DialogTitle>
          <DialogDescription>{t('meetings.new_help')}</DialogDescription>
        </DialogHeader>
        <form
          id='new-meeting'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                series_id: seriesId,
                title: draft.title || null,
                starts_at: new Date(draft.starts_at).toISOString(),
                duration_minutes: draft.duration_minutes
                  ? Number(draft.duration_minutes)
                  : null,
                location: draft.location || null,
                online_link: draft.online_link || null,
                copy_template: draft.copy_template,
              },
              {
                onSuccess: (m) => {
                  toast.success(t('meetings.created', { code: m.code }))
                  onCreated(m)
                },
              }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='nm-series'>{t('meetings.series')}</Label>
            <Select
              value={seriesId ? String(seriesId) : NO_SERIES}
              onValueChange={(v) => {
                const id = v === NO_SERIES ? null : Number(v)
                setSeriesId(id)
                set({
                  starts_at: nextSlot(series.find((s) => s.id === id)),
                })
              }}
            >
              <SelectTrigger id='nm-series' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_SERIES}>
                  {t('meetings.one_off')}
                </SelectItem>
                {series.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name} · {statusLabel(s.cadence)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='nm-title'>{t('meetings.title_field')}</Label>
            <Input
              id='nm-title'
              required={!chosen}
              maxLength={300}
              placeholder={chosen?.name}
              value={draft.title}
              onChange={(e) => set({ title: e.target.value })}
            />
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='nm-start'>{t('meetings.when')}</Label>
              <Input
                id='nm-start'
                type='datetime-local'
                required
                value={draft.starts_at}
                onChange={(e) => set({ starts_at: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='nm-duration'>{t('meetings.duration')}</Label>
              <Input
                id='nm-duration'
                type='number'
                min={0}
                max={1440}
                placeholder={String(chosen?.duration_minutes ?? 60)}
                value={draft.duration_minutes}
                onChange={(e) => set({ duration_minutes: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='nm-location'>{t('meetings.location')}</Label>
              <Input
                id='nm-location'
                maxLength={300}
                placeholder={chosen?.location ?? ''}
                value={draft.location}
                onChange={(e) => set({ location: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='nm-link'>{t('meetings.online_link')}</Label>
              <Input
                id='nm-link'
                type='url'
                maxLength={500}
                placeholder={chosen?.online_link ?? ''}
                value={draft.online_link}
                onChange={(e) => set({ online_link: e.target.value })}
              />
            </div>
          </div>
          {chosen ? (
            <label className='flex items-center gap-2 text-sm'>
              <Switch
                checked={draft.copy_template}
                onCheckedChange={(copy_template) => set({ copy_template })}
              />
              {t('meetings.copy_template', {
                items: chosen.agenda_template.length,
                people: chosen.default_attendees.length,
              })}
            </label>
          ) : null}
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type='submit' form='new-meeting' disabled={create.isPending}>
            {t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type TemplateRow = { title: string; duration_minutes: number | null }

export function SeriesDialog({
  projectId,
  series,
  onClose,
}: {
  projectId: number
  series: Series | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, series ? 'meetings.update' : 'meetings.create')
  const save = useSaveSeries()
  const remove = useDeleteSeries()
  const { data: users = [] } = useAssignees()
  const [draft, setDraft] = useState({
    name: series?.name ?? '',
    cadence: (series?.cadence ?? 'weekly') as SeriesIn['cadence'],
    location: series?.location ?? '',
    online_link: series?.online_link ?? '',
    duration_minutes: String(series?.duration_minutes ?? 60),
    active: series?.active ?? true,
  })
  const [template, setTemplate] = useState<TemplateRow[]>(
    (series?.agenda_template ?? []).map((i) => ({
      title: String(i.title ?? ''),
      duration_minutes:
        i.duration_minutes == null ? null : Number(i.duration_minutes),
    }))
  )
  const [people, setPeople] = useState<Person[]>(
    (series?.default_attendees ?? []) as Person[]
  )
  const { data: contactNames = {} } = useContactNames(
    people.map((p) => p.contact_id ?? 0).filter(Boolean)
  )
  const userNames = new Map(users.map((u) => [u.id, u.name]))
  const nameOf = (p: Person) =>
    p.user_id
      ? (userNames.get(p.user_id) ?? `#${p.user_id}`)
      : ((contactNames as Record<string, string>)[String(p.contact_id)] ??
        `#${p.contact_id}`)
  const set = (patch: Partial<typeof draft>) =>
    setDraft((d) => ({ ...d, ...patch }))
  const moveRow = (i: number, delta: number) =>
    setTemplate((rows) => {
      const next = [...rows]
      const [row] = next.splice(i, 1)
      next.splice(i + delta, 0, row)
      return next
    })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {series ? series.name : t('meetings.new_series')}
          </DialogTitle>
          <DialogDescription>{t('meetings.series_help')}</DialogDescription>
        </DialogHeader>
        <form
          id='series-form'
          className='grid gap-4'
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(
              {
                id: series?.id,
                body: {
                  project_id: projectId,
                  name: draft.name,
                  cadence: draft.cadence,
                  location: draft.location || null,
                  online_link: draft.online_link || null,
                  duration_minutes: Number(draft.duration_minutes) || 60,
                  active: draft.active,
                  agenda_template: template.filter((r) => r.title.trim()),
                  default_attendees: people.map((p) =>
                    p.user_id
                      ? { user_id: p.user_id }
                      : { contact_id: p.contact_id }
                  ),
                },
              },
              {
                onSuccess: () => {
                  toast.success(t('meetings.series_saved'))
                  onClose()
                },
              }
            )
          }}
        >
          <fieldset disabled={!editable} className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='s-name'>{t('meetings.series_name')}</Label>
              <Input
                id='s-name'
                required
                maxLength={200}
                value={draft.name}
                onChange={(e) => set({ name: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='s-cadence'>{t('meetings.cadence')}</Label>
              <Select
                value={draft.cadence}
                onValueChange={(v) =>
                  set({ cadence: v as SeriesIn['cadence'] })
                }
              >
                <SelectTrigger id='s-cadence' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CADENCES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {statusLabel(c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='s-duration'>{t('meetings.duration')}</Label>
              <Input
                id='s-duration'
                type='number'
                min={0}
                max={1440}
                value={draft.duration_minutes}
                onChange={(e) => set({ duration_minutes: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='s-location'>{t('meetings.location')}</Label>
              <Input
                id='s-location'
                maxLength={300}
                value={draft.location}
                onChange={(e) => set({ location: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='s-link'>{t('meetings.online_link')}</Label>
              <Input
                id='s-link'
                type='url'
                maxLength={500}
                value={draft.online_link}
                onChange={(e) => set({ online_link: e.target.value })}
              />
            </div>
            <label className='flex items-center gap-2 text-sm'>
              <Switch
                checked={draft.active}
                onCheckedChange={(active) => set({ active })}
              />
              {t('meetings.active')}
            </label>
          </fieldset>

          <section className='grid gap-2'>
            <h4 className='text-sm font-medium'>
              {t('meetings.agenda_template')}
            </h4>
            {template.map((row, i) => (
              <div key={i} className='flex items-center gap-2'>
                <span className='w-6 text-end text-sm tabular-nums'>
                  {i + 1}.
                </span>
                <Input
                  className='h-8 flex-1'
                  value={row.title}
                  maxLength={300}
                  disabled={!editable}
                  aria-label={t('meetings.item_title')}
                  onChange={(e) =>
                    setTemplate((rows) =>
                      rows.map((r, j) =>
                        j === i ? { ...r, title: e.target.value } : r
                      )
                    )
                  }
                />
                <Input
                  className='h-8 w-20'
                  type='number'
                  min={0}
                  max={1440}
                  placeholder={t('meetings.min')}
                  disabled={!editable}
                  aria-label={t('meetings.minutes_allocated')}
                  value={row.duration_minutes ?? ''}
                  onChange={(e) =>
                    setTemplate((rows) =>
                      rows.map((r, j) =>
                        j === i
                          ? {
                              ...r,
                              duration_minutes: e.target.value
                                ? Number(e.target.value)
                                : null,
                            }
                          : r
                      )
                    )
                  }
                />
                {editable ? (
                  <>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      className='size-7'
                      disabled={i === 0}
                      aria-label={t('meetings.move_up')}
                      onClick={() => moveRow(i, -1)}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      className='size-7'
                      disabled={i === template.length - 1}
                      aria-label={t('meetings.move_down')}
                      onClick={() => moveRow(i, 1)}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      className='size-7 text-muted-foreground hover:text-red-600'
                      aria-label={t('meetings.remove')}
                      onClick={() =>
                        setTemplate((rows) => rows.filter((_, j) => j !== i))
                      }
                    >
                      <Trash2 />
                    </Button>
                  </>
                ) : null}
              </div>
            ))}
            {editable ? (
              <Button
                type='button'
                size='sm'
                variant='outline'
                className='w-fit'
                onClick={() =>
                  setTemplate((rows) => [
                    ...rows,
                    { title: '', duration_minutes: null },
                  ])
                }
              >
                <Plus /> {t('meetings.add_item')}
              </Button>
            ) : null}
          </section>

          <section className='grid gap-2'>
            <div className='flex items-center justify-between'>
              <h4 className='text-sm font-medium'>
                {t('meetings.default_attendees')}
              </h4>
              {editable ? (
                <PersonPicker
                  projectId={projectId}
                  exclude={
                    new Set(
                      people.map((p) =>
                        p.user_id ? `u:${p.user_id}` : `c:${p.contact_id}`
                      )
                    )
                  }
                  onPick={(person) => setPeople((ps) => [...ps, person])}
                />
              ) : null}
            </div>
            <div className='flex flex-wrap gap-1.5'>
              {people.map((p) => (
                <Badge
                  key={p.user_id ? `u${p.user_id}` : `c${p.contact_id}`}
                  variant='secondary'
                  className='gap-1'
                >
                  {nameOf(p)}
                  {editable ? (
                    <button
                      type='button'
                      aria-label={t('meetings.remove')}
                      onClick={() =>
                        setPeople((ps) => ps.filter((x) => x !== p))
                      }
                    >
                      <X className='size-3' />
                    </button>
                  ) : null}
                </Badge>
              ))}
              {!people.length ? (
                <span className='text-sm text-muted-foreground'>
                  {t('meetings.no_attendees')}
                </span>
              ) : null}
            </div>
          </section>
        </form>
        <DialogFooter className='gap-2'>
          {series && can(session, 'meetings.delete') ? (
            <Button
              variant='ghost'
              className='me-auto text-red-600'
              onClick={() => {
                if (window.confirm(t('meetings.confirm_delete_series')))
                  remove.mutate(series.id, { onSuccess: onClose })
              }}
            >
              <Trash2 /> {t('meetings.delete')}
            </Button>
          ) : null}
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {editable ? (
            <Button type='submit' form='series-form' disabled={save.isPending}>
              {series ? t('common.save') : t('common.create')}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
