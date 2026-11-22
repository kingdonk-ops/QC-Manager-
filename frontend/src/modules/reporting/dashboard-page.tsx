import { useState } from 'react'
import { FileDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Page } from '@/components/layout/page'
import {
  type PivotRequest,
  useDatasets,
  useDownload,
  usePivot,
  useProjectKpis,
  useTemplates,
} from './api'
import { ChartView, KpiCard } from './charts'
import { type ChartType, chartSeries, formatValue } from './lib'

function PivotChart({
  title,
  request,
  type,
  labels,
}: {
  title: string
  request: PivotRequest
  type: ChartType
  labels: Record<string, string>
}) {
  const { data, isLoading } = usePivot(request)
  const chart = data
    ? chartSeries(data, (f, agg) =>
        f === '*'
          ? 'Rows'
          : `${labels[f] ?? f}${agg === 'sum' ? '' : ` (${agg})`}`
      )
    : null
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {chart ? (
          <ChartView type={type} data={chart.data} series={chart.series} />
        ) : (
          <p className='py-10 text-center text-sm text-muted-foreground'>
            {isLoading ? '…' : '–'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export function GenerateReport({ projectId }: { projectId?: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: templates = [] } = useTemplates()
  const [templateId, setTemplateId] = useState<string>('')
  const [format, setFormat] = useState<'pdf' | 'xlsx'>('pdf')
  const download = useDownload()
  if (!can(session, 'reporting.export')) return null
  const chosen = templateId || (templates[0] ? String(templates[0].id) : '')
  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Select value={chosen} onValueChange={setTemplateId}>
        <SelectTrigger size='sm' className='h-8 w-56'>
          <SelectValue placeholder={t('reporting.template')} />
        </SelectTrigger>
        <SelectContent>
          {templates.map((tpl) => (
            <SelectItem key={tpl.id} value={String(tpl.id)}>
              {tpl.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={format} onValueChange={(v) => setFormat(v as 'pdf')}>
        <SelectTrigger size='sm' className='h-8 w-24'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value='pdf'>PDF</SelectItem>
          <SelectItem value='xlsx'>Excel</SelectItem>
        </SelectContent>
      </Select>
      <Button
        size='sm'
        disabled={!chosen || download.isPending}
        onClick={() =>
          download.mutate({
            url: '/api/v1/reporting/generate',
            body: {
              template_id: Number(chosen),
              project_id: projectId,
              format,
            },
          })
        }
      >
        <FileDown /> {t('reporting.generate')}
      </Button>
    </div>
  )
}

function Dashboard({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const { data: kpis = [], isLoading } = useProjectKpis(projectId)
  const { data: datasets = [] } = useDatasets(projectId)
  const names = new Set(datasets.map((d) => d.name))
  const labelsOf = (name: string) =>
    Object.fromEntries(
      (datasets.find((d) => d.name === name)?.columns ?? []).map((c) => [
        c.key,
        c.label,
      ])
    )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5'>
        {kpis.map((k) => (
          <KpiCard
            key={k.key}
            label={k.label}
            value={formatValue(k.value, k.unit, currency)}
            status={k.status}
            hint={k.description}
          />
        ))}
        {!isLoading && kpis.length === 0 ? (
          <p className='col-span-full text-sm text-muted-foreground'>
            {t('reporting.no_kpis')}
          </p>
        ) : null}
      </div>
      <div className='grid gap-4 lg:grid-cols-2'>
        {names.has('cvr_cost_heads') ? (
          <PivotChart
            title={t('reporting.chart.budget_forecast')}
            type='bar'
            labels={labelsOf('cvr_cost_heads')}
            request={{
              dataset: 'cvr_cost_heads',
              project_id: projectId,
              rows: ['code'],
              columns: [],
              values: [
                { field: 'budget', agg: 'sum' },
                { field: 'forecast_cost', agg: 'sum' },
                { field: 'cost_to_date', agg: 'sum' },
              ],
              filters: {},
            }}
          />
        ) : null}
        {names.has('tasks') ? (
          <PivotChart
            title={t('reporting.chart.tasks')}
            type='stacked'
            labels={labelsOf('tasks')}
            request={{
              dataset: 'tasks',
              project_id: projectId,
              rows: ['status'],
              columns: ['priority'],
              values: [{ field: '*', agg: 'count' }],
              filters: {},
            }}
          />
        ) : null}
        {names.has('cvr_cashflow') ? (
          <PivotChart
            title={t('reporting.chart.cashflow')}
            type='line'
            labels={labelsOf('cvr_cashflow')}
            request={{
              dataset: 'cvr_cashflow',
              project_id: projectId,
              rows: ['period'],
              columns: [],
              values: [
                { field: 'planned_cost', agg: 'sum' },
                { field: 'actual_cost', agg: 'sum' },
              ],
              filters: {},
            }}
          />
        ) : null}
        {names.has('documents') ? (
          <PivotChart
            title={t('reporting.chart.documents')}
            type='pie'
            labels={labelsOf('documents')}
            request={{
              dataset: 'documents',
              project_id: projectId,
              rows: ['category'],
              columns: [],
              values: [{ field: '*', agg: 'count' }],
              filters: { latest: true },
            }}
          />
        ) : null}
      </div>
    </>
  )
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('reporting.dashboard')}
      description={t('reporting.dashboard_description')}
      projectScoped
      actions={project ? <GenerateReport projectId={project.id} /> : null}
    >
      {project ? (
        <Dashboard
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('reporting.no_project')}
        </p>
      )}
    </Page>
  )
}
