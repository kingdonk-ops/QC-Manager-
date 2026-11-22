import { useState } from 'react'
import { CalendarCheck, FileDown, FileSpreadsheet } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import {
  type Basis,
  type EacMethod,
  type GroupBy,
  type Interval,
  exportUrl,
  reportUrl,
  useCashflow,
  useMetrics,
  useSCurve,
  useSetSettings,
  useSettings,
} from './api'
import { CashflowChart } from './cashflow-chart'
import { ImportDialog } from './import-dialog'
import { KpiCards } from './kpi-cards'
import { MetricsGrid } from './metrics-grid'
import { PackagesGrid } from './packages-grid'
import { ProgressGrid } from './progress-grid'
import { PeriodChart, SCurveChart } from './s-curve-chart'
import { SnapshotsPanel } from './snapshots-panel'

const today = () => new Date().toISOString().slice(0, 10)

function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string; disabled?: boolean }[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div
      role='radiogroup'
      aria-label={label}
      className='inline-flex rounded-md border p-0.5'
    >
      {options.map((o) => (
        <button
          key={o.value}
          type='button'
          role='radio'
          aria-checked={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded px-3 py-1 text-sm transition-colors disabled:opacity-40',
            value === o.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {o.label}
        </button>
      ))}
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
  const session = useSession()
  const { data: settings } = useSettings(projectId)
  const setSettings = useSetSettings(projectId)
  const [picked, setPicked] = useState('')
  const [basis, setBasis] = useState<Basis>('hours')
  const [groupBy, setGroupBy] = useState<GroupBy>('package')
  const [interval, setPeriod] = useState<Interval>('month')
  const date = picked || settings?.data_date || ''
  const { data: metrics } = useMetrics(projectId, date, basis, groupBy)
  const { data: curve } = useSCurve(projectId, date, basis, interval)
  const { data: cashflow } = useCashflow(projectId)
  const costAvailable = settings?.cost_available ?? false
  const activeBasis: Basis = costAvailable ? basis : 'hours'
  const effectiveDate = date || metrics?.data_date || today()
  const eacMethod = (settings?.eac_method ?? 'cpi') as EacMethod

  const groupLabels: Record<GroupBy, string> = {
    package: t('evm.group_package'),
    account: t('evm.group_account'),
    discipline: t('evm.group_discipline'),
    project: t('evm.group_project'),
  }

  return (
    <>
      <div className='flex flex-wrap items-end gap-3'>
        <div className='grid gap-1'>
          <Label htmlFor='evm-date' className='text-xs'>
            {t('evm.data_date')}
          </Label>
          <Input
            id='evm-date'
            type='date'
            className='h-8 w-40'
            value={effectiveDate}
            onChange={(e) => setPicked(e.target.value)}
          />
        </div>
        {can(session, 'evm.update') && effectiveDate !== settings?.data_date ? (
          <Button
            size='sm'
            variant='outline'
            onClick={() =>
              setSettings.mutate({
                data_date: effectiveDate,
                eac_method: eacMethod,
              })
            }
          >
            <CalendarCheck /> {t('evm.set_data_date')}
          </Button>
        ) : null}
        <div className='grid gap-1'>
          <span className='text-xs font-medium'>{t('evm.basis')}</span>
          <Segmented<Basis>
            label={t('evm.basis')}
            value={activeBasis}
            onChange={setBasis}
            options={[
              { value: 'hours', label: t('evm.hours') },
              {
                value: 'cost',
                label: t('evm.cost'),
                disabled: !costAvailable,
              },
            ]}
          />
        </div>
        <div className='grid gap-1'>
          <span className='text-xs font-medium'>{t('evm.eac_method')}</span>
          <Select
            value={eacMethod}
            disabled={!can(session, 'evm.update')}
            onValueChange={(v) =>
              setSettings.mutate({
                data_date: settings?.data_date ?? null,
                eac_method: v as EacMethod,
              })
            }
          >
            <SelectTrigger size='sm' className='w-56'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='cpi'>{t('evm.eac_cpi')}</SelectItem>
              <SelectItem value='budget_rate'>
                {t('evm.eac_budget_rate')}
              </SelectItem>
              <SelectItem value='cpi_spi'>{t('evm.eac_cpi_spi')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className='ms-auto flex flex-wrap gap-2'>
          {can(session, 'evm.import') ? (
            <ImportDialog projectId={projectId} dataDate={effectiveDate} />
          ) : null}
          {can(session, 'evm.export') ? (
            <>
              <Button size='sm' variant='outline' asChild>
                <a href={exportUrl(projectId, effectiveDate, activeBasis)}>
                  <FileSpreadsheet /> {t('evm.export_xlsx')}
                </a>
              </Button>
              <Button size='sm' variant='outline' asChild>
                <a
                  href={reportUrl(projectId, effectiveDate, activeBasis)}
                  target='_blank'
                  rel='noreferrer'
                >
                  <FileDown /> {t('evm.report_pdf')}
                </a>
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <Tabs defaultValue='dashboard'>
        <TabsList>
          <TabsTrigger value='dashboard'>{t('evm.tab_dashboard')}</TabsTrigger>
          <TabsTrigger value='progress'>{t('evm.tab_progress')}</TabsTrigger>
          <TabsTrigger value='packages'>{t('evm.tab_packages')}</TabsTrigger>
          <TabsTrigger value='baselines'>{t('evm.tab_baselines')}</TabsTrigger>
          <TabsTrigger value='cashflow'>{t('evm.tab_cashflow')}</TabsTrigger>
        </TabsList>

        <TabsContent value='dashboard' className='flex flex-col gap-4'>
          {metrics ? (
            <KpiCards
              total={metrics.total}
              basis={activeBasis}
              currency={currency}
            />
          ) : null}
          <Card>
            <CardHeader className='flex flex-row flex-wrap items-center justify-between gap-2'>
              <CardTitle className='text-base'>{t('evm.s_curve')}</CardTitle>
              <Segmented<Interval>
                label={t('evm.interval')}
                value={interval}
                onChange={setPeriod}
                options={[
                  { value: 'week', label: t('evm.weekly') },
                  { value: 'month', label: t('evm.monthly') },
                ]}
              />
            </CardHeader>
            <CardContent className='flex flex-col gap-4'>
              {curve ? (
                <>
                  <SCurveChart
                    curve={curve}
                    basis={activeBasis}
                    currency={currency}
                  />
                  {curve.points.length ? (
                    <PeriodChart
                      curve={curve}
                      basis={activeBasis}
                      currency={currency}
                    />
                  ) : null}
                  {curve.forecast_finish ? (
                    <p className='text-xs text-muted-foreground'>
                      {t('evm.forecast_finish', {
                        date: curve.forecast_finish,
                      })}
                    </p>
                  ) : null}
                </>
              ) : null}
            </CardContent>
          </Card>
          <div className='flex flex-wrap items-center gap-2'>
            <span className='text-sm font-medium'>{t('evm.group_by')}</span>
            <Segmented<GroupBy>
              label={t('evm.group_by')}
              value={groupBy}
              onChange={setGroupBy}
              options={(Object.keys(groupLabels) as GroupBy[]).map((g) => ({
                value: g,
                label: groupLabels[g],
              }))}
            />
          </div>
          {metrics ? (
            <MetricsGrid
              rows={metrics.rows}
              total={metrics.total}
              basis={activeBasis}
              currency={currency}
              groupLabel={groupLabels[groupBy]}
            />
          ) : null}
        </TabsContent>

        <TabsContent value='progress'>
          <ProgressGrid
            projectId={projectId}
            dataDate={effectiveDate}
            costAvailable={costAvailable}
          />
        </TabsContent>

        <TabsContent value='packages'>
          <PackagesGrid projectId={projectId} />
        </TabsContent>

        <TabsContent value='baselines'>
          <SnapshotsPanel projectId={projectId} dataDate={effectiveDate} />
        </TabsContent>

        <TabsContent value='cashflow'>
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>{t('evm.cashflow')}</CardTitle>
            </CardHeader>
            <CardContent>
              {cashflow ? <CashflowChart cashflow={cashflow} /> : null}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  )
}

export default function EvmPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()

  return (
    <Page
      title={t('evm.title')}
      description={t('evm.description')}
      projectScoped
    >
      {project ? (
        <Dashboard
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('evm.no_project')}</p>
      )}
    </Page>
  )
}
