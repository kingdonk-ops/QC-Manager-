import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link2, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Activity,
  type ActivityPatch,
  type Dependency,
  type LinkType,
  useAddDependency,
  useDeleteActivity,
  useDeleteDependency,
  useUpdateActivity,
} from './api'
import { isCritical } from './gantt-colors'

const FIELDS = [
  'name',
  'type',
  'status',
  'duration',
  'percent_complete',
  'actual_start',
  'actual_finish',
  'constraint_type',
  'constraint_date',
  'resource',
  'budget_hours',
  'budget_cost',
  'optimistic_duration',
  'most_likely_duration',
  'pessimistic_duration',
  'notes',
] as const
type Field = (typeof FIELDS)[number]
type Draft = Record<Field, string>

const NUMERIC: Field[] = [
  'duration',
  'percent_complete',
  'optimistic_duration',
  'most_likely_duration',
  'pessimistic_duration',
]

function draftOf(a: Activity): Draft {
  const out = {} as Draft
  for (const f of FIELDS) {
    const v = a[f as keyof Activity]
    out[f] = v === null || v === undefined ? '' : String(v)
  }
  return out
}

/** Only the fields that changed, typed for the PATCH. */
function changes(before: Draft, after: Draft): ActivityPatch {
  const patch: Record<string, unknown> = {}
  for (const f of FIELDS) {
    if (before[f] === after[f]) continue
    const v = after[f]
    if (NUMERIC.includes(f)) patch[f] = v === '' ? null : Number(v)
    else patch[f] = v === '' ? null : v
  }
  return patch as ActivityPatch
}

function History({ id }: { id: number }) {
  const { data = [] } = useQuery({
    queryKey: ['schedule', 'history', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/schedule/activities/{activity_id}/history', {
          params: { path: { activity_id: id } },
        })
      ) as Promise<
        {
          from_status: string | null
          to_status: string
          changed_at: string | null
        }[]
      >,
  })
  return (
    <ul className='space-y-1 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex items-center gap-2'>
          <span className='w-36 text-xs text-muted-foreground'>
            {h.changed_at?.slice(0, 16).replace('T', ' ')}
          </span>
          <StatusBadge status={h.to_status} />
        </li>
      ))}
    </ul>
  )
}

function Links({
  activity,
  activities,
  dependencies,
  projectId,
  editable,
}: {
  activity: Activity
  activities: Activity[]
  dependencies: Dependency[]
  projectId: number
  editable: boolean
}) {
  const { t } = useTranslation()
  const add = useAddDependency(projectId)
  const remove = useDeleteDependency(projectId)
  const [pred, setPred] = useState('')
  const [type, setType] = useState<LinkType>('FS')
  const [lag, setLag] = useState('0')
  const names = new Map(activities.map((a) => [a.id, `${a.code} ${a.name}`]))
  const preds = dependencies.filter((d) => d.successor_id === activity.id)
  const succs = dependencies.filter((d) => d.predecessor_id === activity.id)
  const row = (d: Dependency, other: number) => (
    <li key={d.id} className='flex items-center gap-2'>
      <Badge variant='outline' className='font-mono'>
        {d.type}
        {d.lag ? ` ${d.lag > 0 ? '+' : ''}${d.lag}d` : ''}
      </Badge>
      <span className='flex-1 truncate'>{names.get(other)}</span>
      {activity.driving_predecessor_ids.includes(other) ? (
        <Badge className='bg-red-600 text-white'>{t('schedule.driving')}</Badge>
      ) : null}
      {editable ? (
        <button
          aria-label={t('schedule.unlink')}
          className='text-muted-foreground hover:text-red-600'
          onClick={() => remove.mutate(d.id)}
        >
          <Trash2 className='size-4' />
        </button>
      ) : null}
    </li>
  )
  return (
    <div className='grid gap-4 text-sm'>
      <div>
        <h4 className='mb-1 font-medium'>{t('schedule.predecessors')}</h4>
        <ul className='space-y-1'>
          {preds.map((d) => row(d, d.predecessor_id))}
        </ul>
      </div>
      <div>
        <h4 className='mb-1 font-medium'>{t('schedule.successors')}</h4>
        <ul className='space-y-1'>
          {succs.map((d) => row(d, d.successor_id))}
        </ul>
      </div>
      {editable ? (
        <form
          className='flex flex-wrap items-end gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (!pred) return
            add.mutate({
              predecessor_id: Number(pred),
              successor_id: activity.id,
              type,
              lag: Number(lag) || 0,
            })
          }}
        >
          <Select value={pred} onValueChange={setPred}>
            <SelectTrigger size='sm' className='h-8 w-56'>
              <SelectValue placeholder={t('schedule.add_predecessor')} />
            </SelectTrigger>
            <SelectContent>
              {activities
                .filter((a) => a.id !== activity.id && a.type !== 'summary')
                .map((a) => (
                  <SelectItem key={a.id} value={String(a.id)}>
                    {a.code} {a.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <Select value={type} onValueChange={(v) => setType(v as LinkType)}>
            <SelectTrigger size='sm' className='h-8 w-20'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(['FS', 'SS', 'FF', 'SF'] as const).map((k) => (
                <SelectItem key={k} value={k}>
                  {k}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type='number'
            aria-label={t('schedule.lag')}
            className='h-8 w-20'
            value={lag}
            onChange={(e) => setLag(e.target.value)}
          />
          <Button size='sm' type='submit' disabled={!pred || add.isPending}>
            <Link2 /> {t('schedule.link')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

export function ActivitySheet({
  activity,
  activities,
  dependencies,
  projectId,
  editable,
  onClose,
}: {
  activity: Activity
  activities: Activity[]
  dependencies: Dependency[]
  projectId: number
  editable: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const update = useUpdateActivity(projectId)
  const remove = useDeleteActivity(projectId)
  const [initial] = useState(() => draftOf(activity))
  const [draft, setDraft] = useState(initial)
  const set = (f: Field) => (value: string) =>
    setDraft({ ...draft, [f]: value })
  const summary = activity.type === 'summary'

  const input = (f: Field, label: string, type = 'text', disabled = false) => (
    <div className='grid gap-1'>
      <Label htmlFor={`act-${f}`}>{label}</Label>
      <Input
        id={`act-${f}`}
        type={type}
        className='h-8'
        value={draft[f]}
        disabled={!editable || disabled}
        onChange={(e) => set(f)(e.target.value)}
      />
    </div>
  )
  const select = (f: Field, label: string, options: [string, string][]) => (
    <div className='grid gap-1'>
      <Label>{label}</Label>
      <Select
        value={draft[f]}
        onValueChange={set(f)}
        disabled={!editable || summary}
      >
        <SelectTrigger size='sm' className='h-8 w-full'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )

  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={`${activity.wbs_code} · ${activity.name}`}
      subtitle={`${activity.code} · ${activity.early_start ?? '–'} → ${activity.early_finish ?? '–'}`}
      badges={
        <>
          <StatusBadge status={activity.status} />
          {isCritical(activity) ? (
            <Badge className='bg-red-600 text-white'>
              {t('schedule.critical')}
            </Badge>
          ) : null}
          <Badge variant='outline'>
            {t('schedule.float')} {activity.total_float ?? '–'}d
          </Badge>
          {activity.p6_float_days != null ? (
            <Badge variant='outline'>
              {t('schedule.float_p6')} {activity.p6_float_days}d
            </Badge>
          ) : null}
          {activity.baseline_variance ? (
            <Badge variant='outline'>
              {t('schedule.vs_baseline')}{' '}
              {activity.baseline_variance > 0 ? '+' : ''}
              {activity.baseline_variance}d
            </Badge>
          ) : null}
        </>
      }
      record={{
        projectId,
        entityType: 'schedule_activity',
        entityId: activity.id,
      }}
      tabs={{
        [t('schedule.links')]: (
          <Links
            activity={activity}
            activities={activities}
            dependencies={dependencies}
            projectId={projectId}
            editable={editable}
          />
        ),
        [t('schedule.history')]: <History id={activity.id} />,
      }}
    >
      <form
        className='grid gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          const patch = changes(initial, draft)
          if (Object.keys(patch).length === 0) return onClose()
          update.mutate({ id: activity.id, patch }, { onSuccess: onClose })
        }}
      >
        {input('name', t('schedule.col.name'))}
        <div className='grid grid-cols-3 gap-3'>
          {select('type', t('schedule.type'), [
            ['task', t('schedule.types.task')],
            ['milestone', t('schedule.types.milestone')],
            ['summary', t('schedule.types.summary')],
          ])}
          {select('status', t('schedule.status'), [
            ['pending', t('schedule.statuses.pending')],
            ['in_progress', t('schedule.statuses.in_progress')],
            ['completed', t('schedule.statuses.completed')],
          ])}
          {input(
            'percent_complete',
            t('schedule.col.percent'),
            'number',
            summary
          )}
        </div>
        <div className='grid grid-cols-3 gap-3'>
          {input('duration', t('schedule.col.duration'), 'number', summary)}
          {input('actual_start', t('schedule.actual_start'), 'date', summary)}
          {input('actual_finish', t('schedule.actual_finish'), 'date', summary)}
        </div>
        <div className='grid grid-cols-3 gap-3'>
          {select('constraint_type', t('schedule.constraint'), [
            ['asap', t('schedule.constraints.asap')],
            ['snet', t('schedule.constraints.snet')],
            ['fnlt', t('schedule.constraints.fnlt')],
            ['mso', t('schedule.constraints.mso')],
          ])}
          {input(
            'constraint_date',
            t('schedule.constraint_date'),
            'date',
            summary
          )}
          {input('resource', t('schedule.resource'))}
        </div>
        <div className='grid grid-cols-2 gap-3'>
          {input('budget_hours', t('schedule.budget_hours'), 'number')}
          {input('budget_cost', t('schedule.budget_cost'), 'number')}
        </div>
        <div className='grid grid-cols-3 gap-3'>
          {input(
            'optimistic_duration',
            t('schedule.optimistic'),
            'number',
            summary
          )}
          {input(
            'most_likely_duration',
            t('schedule.most_likely'),
            'number',
            summary
          )}
          {input(
            'pessimistic_duration',
            t('schedule.pessimistic'),
            'number',
            summary
          )}
        </div>
        <div className='grid gap-1'>
          <Label htmlFor='act-notes'>{t('schedule.notes')}</Label>
          <Textarea
            id='act-notes'
            rows={3}
            value={draft.notes}
            disabled={!editable}
            onChange={(e) => set('notes')(e.target.value)}
          />
        </div>
        <dl className='grid grid-cols-4 gap-x-3 gap-y-1 rounded-md border p-3 text-xs'>
          <dt className='text-muted-foreground'>{t('schedule.planned')}</dt>
          <dd>
            {activity.planned_start ?? '–'} → {activity.planned_finish ?? '–'}
          </dd>
          <dt className='text-muted-foreground'>{t('schedule.baseline')}</dt>
          <dd>
            {activity.baseline_start ?? '–'} → {activity.baseline_finish ?? '–'}
          </dd>
          <dt className='text-muted-foreground'>{t('schedule.early')}</dt>
          <dd>
            {activity.early_start ?? '–'} → {activity.early_finish ?? '–'}
          </dd>
          <dt className='text-muted-foreground'>{t('schedule.late')}</dt>
          <dd>
            {activity.late_start ?? '–'} → {activity.late_finish ?? '–'}
          </dd>
          <dt className='text-muted-foreground'>{t('schedule.free_float')}</dt>
          <dd>{activity.free_float ?? '–'}d</dd>
          <dt className='text-muted-foreground'>
            {t('schedule.finish_variance')}
          </dt>
          <dd>{activity.finish_variance ?? '–'}d</dd>
        </dl>
        {editable ? (
          <div className='flex justify-between'>
            <Button
              type='button'
              variant='outline'
              className='text-red-600'
              onClick={() => remove.mutate(activity.id, { onSuccess: onClose })}
            >
              <Trash2 /> {t('schedule.delete')}
            </Button>
            <Button type='submit' disabled={update.isPending}>
              {t('common.save')}
            </Button>
          </div>
        ) : null}
      </form>
    </RecordSheet>
  )
}
