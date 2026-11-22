import { useState } from 'react'
import { useCrews } from '@/modules/planner/api'
import { ArrowLeft, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import { logApi, useDaySummary, useLog, useLogMutation } from './api'
import { LogForm } from './log-form'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

export default function WorkfaceLogPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('workface_log.title')}
      description={t('workface_log.description')}
      projectScoped
    >
      {project ? (
        <Day key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('workface_log.no_project')}
        </p>
      )}
    </Page>
  )
}

function Day({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [day, setDay] = useState(() => new Date().toLocaleDateString('en-CA'))
  const [openId, setOpenId] = useState<number | null>(initialId)
  const { data: summary } = useDaySummary(projectId, day)
  const { data: crews = [] } = useCrews(projectId)
  const [crewId, setCrewId] = useState('')
  const [shift, setShift] = useState('day')
  const create = useLogMutation(logApi.create)
  const { data: open } = useLog(openId)

  if (openId && open)
    return (
      <div className='grid gap-2'>
        <Button
          variant='ghost'
          size='sm'
          className='w-fit'
          onClick={() => setOpenId(null)}
        >
          <ArrowLeft /> {t('workface_log.back')}
        </Button>
        <LogForm key={`${open.id}-${open.status}`} log={open} />
      </div>
    )

  const totals = summary?.totals
  return (
    <div className='grid gap-4'>
      <div className='flex flex-wrap items-end gap-2'>
        <Input
          type='date'
          className='h-9 w-44'
          aria-label={t('workface_log.date')}
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
        {can(session, 'workface_log.create') ? (
          <form
            className='flex flex-wrap gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              create.mutate(
                {
                  project_id: projectId,
                  crew_id: Number(crewId),
                  work_date: day,
                  shift: shift as never,
                  prefill: true,
                },
                { onSuccess: (made) => setOpenId(made.id) }
              )
            }}
          >
            <NativeSelect
              className='h-9 w-48'
              required
              aria-label={t('workface_log.crew')}
              placeholder={t('workface_log.pick_crew')}
              options={crews.map((c) => ({
                value: String(c.id),
                label: `${c.code} ${c.name}`,
              }))}
              value={crewId}
              onChange={(e) => setCrewId(e.target.value)}
            />
            <NativeSelect
              className='h-9 w-28'
              aria-label={t('workface_log.shift')}
              values={['day', 'night']}
              value={shift}
              onChange={(e) => setShift(e.target.value)}
            />
            <Button type='submit' disabled={!crewId || create.isPending}>
              <Plus /> {t('workface_log.start')}
            </Button>
          </form>
        ) : null}
      </div>

      {totals ? (
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-5'>
          <Stat label={t('workface_log.total')} value={totals.total_hours} />
          <Stat
            label={t('workface_log.productive')}
            value={totals.productive_hours}
          />
          <Stat label={t('workface_log.delays')} value={totals.delay_hours} />
          <Stat
            label={t('workface_log.overhead')}
            value={totals.overhead_hours}
          />
          <Stat
            label={t('workface_log.headcount')}
            value={totals.headcount}
            unit=''
          />
        </div>
      ) : null}

      <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-3'>
        {summary?.crews.map((c) => (
          <Card key={c.crew_id} className='py-3'>
            <CardContent className='grid gap-1 px-3 text-sm'>
              <div className='flex items-center gap-2'>
                <span className='font-medium'>{c.crew_code}</span>
                <span className='text-muted-foreground'>{c.crew_name}</span>
                <span className='ms-auto'>
                  <StatusBadge status={c.status ?? 'not_started'} />
                </span>
              </div>
              <div className='text-xs text-muted-foreground'>
                {c.planned_anchors} {t('workface_log.planned_anchors')} ·{' '}
                {Number(c.total_hours)} h ({Number(c.delay_hours)} h{' '}
                {t('workface_log.delayed')})
              </div>
              {c.log_id ? (
                <Button
                  size='sm'
                  variant='outline'
                  className='mt-1 w-fit'
                  onClick={() => setOpenId(c.log_id!)}
                >
                  {t('workface_log.open')} {c.log_code}
                </Button>
              ) : null}
            </CardContent>
          </Card>
        ))}
        {summary && summary.crews.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('workface_log.nothing')}
          </p>
        ) : null}
      </div>

      {totals && totals.by_anchor.length ? (
        <div className='overflow-x-auto rounded-md border'>
          <table className='w-full text-sm'>
            <thead className='bg-muted/50 text-xs text-muted-foreground'>
              <tr>
                <th className='p-2 text-left'>
                  {t('workface_log.work_anchor')}
                </th>
                <th className='p-2 text-right'>{t('workface_log.hours')}</th>
                <th className='p-2 text-right'>
                  {t('workface_log.installed')}
                </th>
              </tr>
            </thead>
            <tbody>
              {totals.by_anchor.map((a) => (
                <tr key={a.anchor_id} className='border-t'>
                  <td className='p-2'>{a.anchor_path || a.anchor_code}</td>
                  <td className='p-2 text-right'>{Number(a.hours)}</td>
                  <td className='p-2 text-right'>
                    {Number(a.qty)} {a.uom}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

function Stat({
  label,
  value,
  unit = 'h',
}: {
  label: string
  value: string | number
  unit?: string
}) {
  return (
    <Card className='py-3'>
      <CardContent className='px-3'>
        <div className='text-xs text-muted-foreground'>{label}</div>
        <div className='text-lg font-semibold'>
          {Number(value).toLocaleString()} {unit}
        </div>
      </CardContent>
    </Card>
  )
}
