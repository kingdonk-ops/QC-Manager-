import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Clock, Eye, FileText, ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useCurrentProject } from '@/stores/use-current-project'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { statusLabel } from '@/components/records/status'
import { type Dashboard, useDashboard } from './api'
import { RiskMatrix } from './parts'

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string | number
  hint?: string
  tone?: 'good' | 'bad'
}) {
  return (
    <Card className='gap-1 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-xs font-medium text-muted-foreground'>
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-xl font-semibold tabular-nums',
            tone === 'good' && 'text-green-600',
            tone === 'bad' && 'text-red-600'
          )}
        >
          {value}
        </p>
        {hint ? <p className='text-xs text-muted-foreground'>{hint}</p> : null}
      </CardContent>
    </Card>
  )
}

const fmt = (v?: number | null, digits = 2) =>
  v === null || v === undefined ? '—' : v.toFixed(digits)

function MonthlyChart({ data }: { data: Dashboard['monthly'] }) {
  const { t } = useTranslation()
  if (!data.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('safety.no_data')}</p>
    )
  return (
    <ResponsiveContainer width='100%' height={260}>
      <ComposedChart
        data={data}
        margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
      >
        <CartesianGrid strokeDasharray='3 3' className='stroke-border' />
        <XAxis dataKey='month' fontSize={12} />
        <YAxis yAxisId='count' allowDecimals={false} fontSize={12} width={32} />
        <YAxis yAxisId='rate' orientation='right' fontSize={12} width={40} />
        <Tooltip />
        <Legend />
        <Bar
          yAxisId='count'
          dataKey='recordables'
          name={t('safety.recordables')}
          stackId='i'
          fill='#dc2626'
        />
        <Bar
          yAxisId='count'
          dataKey='near_misses'
          name={t('safety.near_misses')}
          stackId='i'
          fill='#f59e0b'
        />
        <Bar
          yAxisId='count'
          dataKey='positive_observations'
          name={t('safety.positive_obs')}
          fill='#16a34a'
        />
        <Line
          yAxisId='rate'
          dataKey='trir'
          name='TRIR'
          stroke='#2563eb'
          strokeWidth={2}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function Board({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const [base, setBase] = useState<number | null>(null)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [show, setShow] = useState<'incidents' | 'observations'>('incidents')
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const { data } = useDashboard(projectId, base, from, to)
  const types = useMemo(
    () => Object.entries(data?.by_type ?? {}),
    [data?.by_type]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          type='date'
          className='h-8 w-40'
          aria-label={t('safety.from')}
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <span className='text-sm text-muted-foreground'>–</span>
        <Input
          type='date'
          className='h-8 w-40'
          aria-label={t('safety.to')}
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
        <NativeSelect
          className='h-8 w-64'
          aria-label={t('safety.rate_base')}
          options={[
            { value: '', label: t('safety.base_conventional') },
            { value: '200000', label: t('safety.base_200k') },
            { value: '1000000', label: t('safety.base_1m') },
          ]}
          value={base ? String(base) : ''}
          onChange={(e) =>
            setBase(e.target.value ? Number(e.target.value) : null)
          }
        />
        <div className='ms-auto flex items-center gap-2'>
          <Input
            type='month'
            className='h-8 w-40'
            aria-label={t('safety.summary_month')}
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          />
          <Button size='sm' variant='outline' asChild>
            <a
              href={`/api/v1/safety/summary.pdf?project_id=${projectId}&month=${month}`}
              target='_blank'
              rel='noreferrer'
            >
              <FileText /> {t('safety.summary_pdf')}
            </a>
          </Button>
        </div>
      </div>

      <div className='grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8'>
        <Kpi
          label={`TRIR (/${(data?.trir_base ?? 200000).toLocaleString()} h)`}
          value={fmt(data?.trir)}
          tone={data?.trir ? 'bad' : 'good'}
        />
        <Kpi
          label={`LTIFR (/${(data?.ltifr_base ?? 1000000).toLocaleString()} h)`}
          value={fmt(data?.ltifr)}
          tone={data?.ltifr ? 'bad' : 'good'}
        />
        <Kpi
          label={t('safety.hours_worked')}
          value={(data?.hours_worked ?? 0).toLocaleString()}
        />
        <Kpi
          label={t('safety.recordables')}
          value={data?.lagging.recordables ?? 0}
        />
        <Kpi
          label={t('safety.ltis')}
          value={data?.lagging.lost_time_injuries ?? 0}
          hint={`${data?.lagging.days_lost ?? 0} ${t('safety.days_lost')}`}
        />
        <Kpi
          label={t('safety.near_miss_ratio')}
          value={fmt(data?.near_miss_ratio)}
          hint={`${data?.lagging.near_misses ?? 0} ${t('safety.near_misses').toLowerCase()}`}
        />
        <Kpi
          label={t('safety.observations')}
          value={data?.leading.observations ?? 0}
          hint={
            data?.leading.positive_ratio !== null &&
            data?.leading.positive_ratio !== undefined
              ? `${Math.round(data.leading.positive_ratio * 100)}% ${t('safety.positive')}`
              : undefined
          }
        />
        <Kpi
          label={t('safety.open_actions')}
          value={data?.open_actions ?? 0}
          hint={`${data?.overdue_actions ?? 0} ${t('safety.overdue')}`}
          tone={data?.overdue_actions ? 'bad' : undefined}
        />
      </div>

      <div className='grid gap-4 lg:grid-cols-[3fr_2fr]'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('safety.monthly')}</CardTitle>
          </CardHeader>
          <CardContent>
            <MonthlyChart data={data?.monthly ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className='flex flex-row items-center justify-between'>
            <CardTitle className='text-base'>
              {t('safety.risk_matrix')}
            </CardTitle>
            <NativeSelect
              className='h-8 w-36'
              aria-label={t('safety.matrix_show')}
              options={[
                { value: 'incidents', label: t('safety.incidents') },
                { value: 'observations', label: t('safety.observations') },
              ]}
              value={show}
              onChange={(e) =>
                setShow(e.target.value as 'incidents' | 'observations')
              }
            />
          </CardHeader>
          <CardContent>
            <RiskMatrix cells={data?.risk_matrix ?? []} show={show} />
          </CardContent>
        </Card>
      </div>

      <div className='grid gap-4 md:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('safety.lagging')}</CardTitle>
          </CardHeader>
          <CardContent className='grid gap-1 text-sm'>
            {types.map(([type, count]) => (
              <div key={type} className='flex justify-between'>
                <span>{statusLabel(type)}</span>
                <span className='tabular-nums'>{count}</span>
              </div>
            ))}
            <p className='pt-2 text-xs text-muted-foreground'>
              {t('safety.formulas')}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('safety.leading')}</CardTitle>
          </CardHeader>
          <CardContent className='grid gap-1 text-sm'>
            <div className='flex justify-between'>
              <span>{t('safety.positive_obs')}</span>
              <span className='tabular-nums'>
                {data?.leading.positive_observations ?? 0}
              </span>
            </div>
            <div className='flex justify-between'>
              <span>{t('safety.negative_obs')}</span>
              <span className='tabular-nums'>
                {data?.leading.negative_observations ?? 0}
              </span>
            </div>
            <div className='flex justify-between'>
              <span>{t('safety.closed_on_time')}</span>
              <span className='tabular-nums'>
                {data?.leading.actions_closed_on_time_pct ?? '—'}
                {data?.leading.actions_closed_on_time_pct !== null &&
                data?.leading.actions_closed_on_time_pct !== undefined
                  ? '%'
                  : ''}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  )
}

export function SafetyNav() {
  const { t } = useTranslation()
  const links = [
    { to: 'safety/incidents', label: t('safety.incidents'), icon: ShieldAlert },
    { to: 'safety/observations', label: t('safety.observations'), icon: Eye },
    { to: 'safety/hours', label: t('safety.hours'), icon: Clock },
  ]
  return (
    <>
      {links.map((l) => (
        <Button key={l.to} size='sm' variant='outline' asChild>
          <Link to='/$' params={{ _splat: l.to }}>
            <l.icon /> {l.label}
          </Link>
        </Button>
      ))}
    </>
  )
}

export default function SafetyDashboardPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('safety.dashboard')}
      description={t('safety.dashboard_description')}
      projectScoped
      actions={<SafetyNav />}
    >
      {project ? (
        <Board key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('safety.no_project')}
        </p>
      )}
    </Page>
  )
}
