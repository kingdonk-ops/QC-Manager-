import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Download, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { money } from '@/lib/format'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { Kpi, SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  exportUrl,
  type Risk,
  type RiskFilter,
  useMatrix,
  useRisks,
} from './api'
import { HeatMap } from './heat-map'
import { RiskSheet } from './risk-sheet'

const STATUSES = ['identified', 'assessed', 'mitigating', 'occurred', 'closed']

function initialRiskId() {
  const id = Number(new URLSearchParams(window.location.search).get('risk'))
  return Number.isFinite(id) && id > 0 ? id : undefined
}

function Register({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [filter, setFilter] = useState<RiskFilter>({ open_only: true })
  const [openId, setOpenId] = useState<number | 'new' | undefined>(
    initialRiskId
  )
  const { data: risks = [] } = useRisks(projectId, filter)
  const { data: matrix } = useMatrix(projectId)
  const fmt = useMemo(() => money(currency), [currency])
  const format = (v?: string | number | null) => fmt({ value: v })
  const selected =
    filter.band && filter.impact
      ? { band: filter.band, impact: filter.impact }
      : undefined
  const open = openId === 'new' ? undefined : risks.find((r) => r.id === openId)

  const columns = useMemo<ColDef<Risk>[]>(
    () => [
      {
        field: 'code',
        headerName: t('risk.code'),
        width: 90,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('risk.title_field'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'category',
        headerName: t('risk.category'),
        width: 130,
        valueFormatter: (p) => (p.value ? t(`risk.cat.${p.value}`) : ''),
      },
      {
        field: 'status',
        headerName: t('risk.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'probability',
        headerName: t('risk.probability_short'),
        width: 80,
        type: 'rightAligned',
      },
      {
        field: 'impact',
        headerName: t('risk.impact'),
        width: 110,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'cost_impact',
        headerName: t('risk.cost_impact'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums',
      },
      {
        field: 'exposure',
        headerName: t('risk.exposure'),
        width: 130,
        type: 'rightAligned',
        valueFormatter: fmt,
        cellClass: 'tabular-nums font-medium',
        sort: 'desc',
        comparator: (a, b) => Number(a) - Number(b),
      },
      {
        field: 'schedule_impact_days',
        headerName: t('risk.days'),
        width: 80,
        type: 'rightAligned',
      },
      { field: 'owner_name', headerName: t('risk.owner'), width: 150 },
      {
        field: 'review_date',
        headerName: t('risk.review_date'),
        width: 120,
        cellClass: (p) => (p.data?.review_due ? 'text-red-600' : ''),
      },
    ],
    [fmt, t]
  )

  return (
    <>
      <div className='grid grid-cols-2 gap-3 lg:grid-cols-4'>
        <Kpi
          label={t('risk.total_exposure')}
          value={format(matrix?.total_exposure)}
          tone='warn'
        />
        <Kpi
          label={t('risk.residual_exposure')}
          value={format(matrix?.total_residual_exposure)}
        />
        <Kpi label={t('risk.open')} value={matrix?.open_count ?? '–'} />
        <Kpi
          label={t('risk.high_critical')}
          value={matrix?.high_critical_count ?? '–'}
          tone={matrix?.high_critical_count ? 'bad' : undefined}
        />
      </div>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('risk.heat_map')}</CardTitle>
          </CardHeader>
          <CardContent>
            {matrix ? (
              <HeatMap
                matrix={matrix}
                selected={selected}
                format={(v) => format(v)}
                onSelect={(cell) =>
                  setFilter((f) => ({
                    ...f,
                    band: cell?.band,
                    impact: cell?.impact,
                  }))
                }
              />
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('risk.by_category')}</CardTitle>
          </CardHeader>
          <CardContent className='space-y-2 text-sm'>
            {matrix?.by_category.map((c) => {
              const share = Number(matrix.total_exposure)
                ? (Number(c.exposure) / Number(matrix.total_exposure)) * 100
                : 0
              return (
                <div key={c.category}>
                  <div className='flex justify-between'>
                    <span>
                      {t(`risk.cat.${c.category}`)} ({c.count})
                    </span>
                    <span className='tabular-nums'>{format(c.exposure)}</span>
                  </div>
                  <div className='h-1.5 rounded bg-muted'>
                    <div
                      className='h-1.5 rounded bg-primary'
                      style={{ width: `${share}%` }}
                    />
                  </div>
                </div>
              )
            })}
            {matrix && !matrix.by_category.length ? (
              <p className='text-muted-foreground'>{t('risk.none')}</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-56'
          placeholder={t('risk.search')}
          value={filter.search ?? ''}
          onChange={(e) => setFilter({ ...filter, search: e.target.value })}
        />
        <div className='w-40'>
          <SelectField
            value={filter.status}
            onChange={(v) => setFilter({ ...filter, status: v ?? undefined })}
            options={STATUSES.map((s) => ({
              value: s,
              label: t(`risk.st.${s}`),
            }))}
            allowNone
            placeholder={t('risk.status')}
          />
        </div>
        <label className='flex items-center gap-1.5 text-sm'>
          <input
            type='checkbox'
            checked={!!filter.open_only}
            onChange={(e) =>
              setFilter({ ...filter, open_only: e.target.checked })
            }
          />
          {t('risk.open_only')}
        </label>
        {selected ? (
          <Button
            size='sm'
            variant='secondary'
            onClick={() =>
              setFilter({ ...filter, band: undefined, impact: undefined })
            }
          >
            {matrix?.bands.find((b) => b.key === selected.band)?.label} ×{' '}
            {t(`risk.imp.${selected.impact}`)} <X />
          </Button>
        ) : null}
        <div className='ms-auto flex gap-2'>
          {can(session, 'risk.export') ? (
            <Button size='sm' variant='outline' asChild>
              <a href={exportUrl(projectId)}>
                <Download /> {t('risk.export')}
              </a>
            </Button>
          ) : null}
          {can(session, 'risk.create') ? (
            <Button size='sm' onClick={() => setOpenId('new')}>
              <Plus /> {t('risk.new')}
            </Button>
          ) : null}
        </div>
      </div>

      <div className='h-[480px]'>
        <DataGrid<Risk>
          rowData={risks}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>

      {openId !== undefined && (openId === 'new' || open) ? (
        <RiskSheet
          key={openId}
          projectId={projectId}
          risk={open}
          open
          onClose={() => setOpenId(undefined)}
          format={format}
        />
      ) : null}
    </>
  )
}

export default function RiskPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()

  return (
    <Page
      title={t('risk.title')}
      description={t('risk.description')}
      projectScoped
    >
      {project ? (
        <Register
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('risk.no_project')}</p>
      )}
    </Page>
  )
}
