import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  METHODS,
  type NdeRequest,
  type NdeResult,
  useAct,
  usePendingResults,
  useRepairRates,
  useRequests,
  useSampling,
  weldingApi,
} from './api'

const today = () => new Date().toISOString().slice(0, 10)

function Sampling({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [method, setMethod] = useState('rt')
  const { data } = useSampling(projectId, method)
  const create = useAct(() =>
    weldingApi.createRequest({
      project_id: projectId,
      method: method as never,
      weld_ids: data?.proposed_weld_ids ?? [],
      reason: 'random',
      include_pending: true,
    })
  )
  const count =
    (data?.proposed_weld_ids.length ?? 0) + (data?.pending_weld_ids.length ?? 0)
  return (
    <Card>
      <CardHeader className='flex flex-row items-center gap-2'>
        <CardTitle className='text-base'>{t('welding.sampling')}</CardTitle>
        <NativeSelect
          className='ms-auto w-28'
          options={METHODS.map((m) => ({ value: m, label: m.toUpperCase() }))}
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        />
        {can(session, 'welding.create') ? (
          <Button
            size='sm'
            disabled={!count || create.isPending}
            onClick={() =>
              create.mutate(undefined, {
                onSuccess: () => toast.success(t('welding.request_created')),
              })
            }
          >
            {t('welding.create_request', { count })}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <table className='w-full text-sm'>
          <thead className='text-left text-xs text-muted-foreground'>
            <tr>
              <th>{t('welding.welder')}</th>
              <th>%</th>
              <th>{t('welding.welds')}</th>
              <th>{t('welding.required')}</th>
              <th>{t('welding.selected')}</th>
              <th>{t('welding.shortfall')}</th>
            </tr>
          </thead>
          <tbody>
            {data?.lots.map((l) => (
              <tr key={`${l.welder_id}-${l.percent}`} className='border-t'>
                <td className='py-1'>{l.stamp}</td>
                <td>{l.percent}</td>
                <td>{l.welds}</td>
                <td>{l.required}</td>
                <td>{l.selected}</td>
                <td
                  className={l.shortfall ? 'font-semibold text-amber-600' : ''}
                >
                  {l.shortfall}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && !data.lots.length ? (
          <p className='text-sm text-muted-foreground'>
            {t('welding.no_sampling')}
          </p>
        ) : null}
        {data?.pending_weld_ids.length ? (
          <p className='pt-2 text-sm text-muted-foreground'>
            {t('welding.pending_extra', {
              count: data.pending_weld_ids.length,
            })}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function ResultButtons({ result }: { result: NdeResult }) {
  const { t } = useTranslation()
  const [report, setReport] = useState('')
  const act = useAct((value: 'accepted' | 'rejected') =>
    weldingApi.recordResult(result.id, {
      result: value,
      examined_on: today(),
      report_ref: report || null,
    })
  )
  const go = (value: 'accepted' | 'rejected') =>
    act.mutate(value, {
      onSuccess: (out) => {
        const message = (out as { message?: string | null }).message
        if (message) toast.warning(message)
      },
    })
  return (
    <div className='flex items-center gap-1'>
      <Input
        className='h-7 w-24'
        placeholder={t('welding.report')}
        value={report}
        onChange={(e) => setReport(e.target.value)}
      />
      <Button size='sm' variant='outline' onClick={() => go('accepted')}>
        {t('welding.accept_short')}
      </Button>
      <Button size='sm' variant='outline' onClick={() => go('rejected')}>
        {t('welding.reject_short')}
      </Button>
    </div>
  )
}

function Rates({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data } = useRepairRates(projectId)
  const rows = (
    list?: {
      key: string
      label: string
      examined: number
      rejected: number
      rate?: number | null
    }[]
  ) =>
    list?.map((r) => (
      <tr key={r.key} className='border-t'>
        <td className='py-1'>{r.label}</td>
        <td>{r.examined}</td>
        <td>{r.rejected}</td>
        <td className={(r.rate ?? 0) > 5 ? 'font-semibold text-red-600' : ''}>
          {r.rate == null ? '–' : `${r.rate}%`}
        </td>
      </tr>
    ))
  const head = (
    <thead className='text-left text-xs text-muted-foreground'>
      <tr>
        <th />
        <th>{t('welding.examined')}</th>
        <th>{t('welding.rejected')}</th>
        <th>{t('welding.rate')}</th>
      </tr>
    </thead>
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>
          {t('welding.repair_rates')}{' '}
          {data?.overall.rate != null ? `· ${data.overall.rate}%` : ''}
        </CardTitle>
      </CardHeader>
      <CardContent className='grid gap-4 text-sm md:grid-cols-2'>
        <table className='w-full'>
          {head}
          <tbody>{rows(data?.by_welder)}</tbody>
        </table>
        <table className='w-full'>
          {head}
          <tbody>{rows(data?.by_method)}</tbody>
        </table>
      </CardContent>
    </Card>
  )
}

export function NdeTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: requests = [] } = useRequests(projectId)
  const { data: pending = [] } = usePendingResults(projectId)
  const reqColumns = useMemo<ColDef<NdeRequest>[]>(
    () => [
      { field: 'code', headerName: t('welding.request'), width: 110 },
      {
        field: 'method',
        headerName: t('welding.method'),
        width: 90,
        valueFormatter: (p) => String(p.value).toUpperCase(),
      },
      { field: 'requested_on', headerName: t('welding.requested'), width: 120 },
      { field: 'total', headerName: t('welding.welds'), width: 90 },
      { field: 'pending', headerName: t('welding.pending'), width: 90 },
      { field: 'rejected', headerName: t('welding.rejected'), width: 100 },
      {
        field: 'status',
        headerName: t('welding.status'),
        flex: 1,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-4'>
      <div className='grid gap-4 xl:grid-cols-2'>
        <Sampling projectId={projectId} />
        <Rates projectId={projectId} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>{t('welding.awaiting')}</CardTitle>
        </CardHeader>
        <CardContent>
          <table className='w-full text-sm'>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id} className='border-t'>
                  <td className='py-1 font-mono'>{r.weld_number}</td>
                  <td className='uppercase'>{r.method}</td>
                  <td>
                    {t(`welding.reason.${r.reason}`)}
                    {r.repair_seq ? ` R${r.repair_seq}` : ''}
                  </td>
                  <td>{r.request_code ?? '–'}</td>
                  <td>
                    {can(session, 'welding.review') ? (
                      <ResultButtons result={r} />
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!pending.length ? (
            <p className='text-sm text-muted-foreground'>
              {t('welding.nothing_pending')}
            </p>
          ) : null}
        </CardContent>
      </Card>
      <div className='h-[300px]'>
        <DataGrid<NdeRequest>
          rowData={requests}
          columnDefs={reqColumns}
          getRowId={(p) => String(p.data.id)}
        />
      </div>
    </div>
  )
}
