import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { AlertTriangle, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { SelectField } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Heat,
  HEAT_STATUSES,
  materialsApi,
  type Receipt,
  useAct,
  useHeats,
  useHolds,
  useNodeTrace,
  useReceipts,
  useWarnings,
} from './api'
import { HeatSheet } from './heat-sheet'
import { NodePicker } from './node-picker'

const today = () => new Date().toISOString().slice(0, 10)

function HeatsTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState<string>()
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<number | 'new'>()
  const { data: heats = [] } = useHeats(projectId, { status, search })
  const columns = useMemo<ColDef<Heat>[]>(
    () => [
      {
        field: 'heat_number',
        headerName: t('materials.heat'),
        width: 130,
        cellClass: 'font-mono',
      },
      { field: 'material_grade', headerName: t('materials.grade'), width: 150 },
      { field: 'product_form', headerName: t('materials.form'), width: 110 },
      {
        field: 'description',
        headerName: t('materials.description_field'),
        flex: 1,
        minWidth: 150,
      },
      { field: 'receipt_code', headerName: 'MRIR', width: 110 },
      { field: 'received_on', headerName: t('materials.received'), width: 115 },
      {
        field: 'supplied_by',
        headerName: t('materials.supplied_by'),
        width: 110,
      },
      {
        field: 'certificate_status',
        headerName: t('materials.certificate'),
        width: 170,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'status',
        headerName: t('materials.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <Input
          className='h-8 w-56'
          placeholder={t('materials.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className='w-44'>
          <SelectField
            value={status}
            onChange={(v) => setStatus(v ?? undefined)}
            options={HEAT_STATUSES.map((s) => ({
              value: s,
              label: t(`materials.st.${s}`),
            }))}
            allowNone
            placeholder={t('materials.status')}
          />
        </div>
        {can(session, 'materials.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setOpenId('new')}
          >
            <Plus /> {t('materials.new_heat')}
          </Button>
        ) : null}
      </div>
      <div className='h-[500px]'>
        <DataGrid<Heat>
          rowData={heats}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          getRowClass={(p) =>
            `cursor-pointer ${p.data?.status === 'quarantined' || p.data?.status === 'rejected' ? 'bg-red-500/10' : ''}`
          }
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {openId !== undefined ? (
        <HeatSheet
          key={openId}
          projectId={projectId}
          heatId={openId === 'new' ? undefined : openId}
          onClose={() => setOpenId(undefined)}
        />
      ) : null}
    </div>
  )
}

function ReceiptsTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: receipts = [] } = useReceipts(projectId)
  const [supplier, setSupplier] = useState('')
  const create = useAct(() =>
    materialsApi.createReceipt({
      project_id: projectId,
      received_on: today(),
      supplier: supplier || null,
    })
  )
  const columns = useMemo<ColDef<Receipt>[]>(
    () => [
      { field: 'code', headerName: 'MRIR', width: 110 },
      { field: 'received_on', headerName: t('materials.received'), width: 120 },
      { field: 'supplier', headerName: t('materials.supplier'), flex: 1 },
      { field: 'purchase_order_code', headerName: 'PO', width: 110 },
      {
        field: 'delivery_note',
        headerName: t('materials.delivery_note'),
        width: 140,
      },
      { field: 'heats', headerName: t('materials.heats'), width: 90 },
      {
        field: 'status',
        headerName: t('materials.status'),
        width: 120,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-2'>
      {can(session, 'materials.create') ? (
        <div className='flex gap-2'>
          <Input
            className='h-8 w-64'
            placeholder={t('materials.supplier')}
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
          />
          <Button
            size='sm'
            onClick={() =>
              create.mutate(undefined, { onSuccess: () => setSupplier('') })
            }
          >
            <Plus /> {t('materials.receive')}
          </Button>
        </div>
      ) : null}
      <div className='h-[460px]'>
        <DataGrid<Receipt>
          rowData={receipts}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
        />
      </div>
    </div>
  )
}

/** Node subtree → heats → certificates and where each went, as a nested list. */
function TraceTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const [node, setNode] = useState<{ id: number; label: string }>()
  const { data } = useNodeTrace(node?.id)
  return (
    <div className='grid max-w-3xl gap-3'>
      <NodePicker projectId={projectId} value={node} onChange={setNode} />
      {data ? (
        <ul className='grid gap-3 text-sm'>
          <li className='font-semibold'>{data.node_path}</li>
          {data.heats.map((h) => (
            <li key={h.heat.id} className='ms-4 border-s ps-3'>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='font-mono font-medium'>
                  {h.heat.heat_number}
                </span>
                <span>{h.heat.material_grade}</span>
                <StatusBadge status={h.heat.status} />
              </div>
              <ul className='ms-4 grid gap-0.5'>
                {h.certificates.map((c) => (
                  <li key={c.id}>
                    📄 {c.certificate_number} ({c.certificate_type}){' '}
                    <StatusBadge status={c.status} />
                  </li>
                ))}
                {!h.certificates.length ? (
                  <li className='text-red-600'>
                    {t('materials.no_certificate')}
                  </li>
                ) : null}
                {h.pmi.map((p) => (
                  <li key={p.id}>
                    PMI {p.tested_on} <StatusBadge status={p.result} />
                  </li>
                ))}
                {h.issues.map((i) => (
                  <li key={i.id} className='text-muted-foreground'>
                    → {i.node_path}
                    {i.item_tag ? ` / ${i.item_tag}` : ''} ({i.issued_on})
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {!data.heats.length ? (
            <li className='text-muted-foreground'>{t('materials.no_trace')}</li>
          ) : null}
        </ul>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('materials.trace_help')}
        </p>
      )}
    </div>
  )
}

function HoldsAndWarnings({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data: holds = [] } = useHolds(projectId)
  const { data: warnings = [] } = useWarnings(projectId)
  return (
    <div className='grid gap-4 text-sm lg:grid-cols-2'>
      <section className='grid content-start gap-2'>
        <h4 className='font-semibold'>{t('materials.open_holds')}</h4>
        {holds.map((h) => (
          <p key={h.id}>
            <span className='font-mono'>{h.code}</span> · {h.heat_number} ·{' '}
            {h.reason}
          </p>
        ))}
        {!holds.length ? (
          <p className='text-muted-foreground'>{t('materials.no_holds')}</p>
        ) : null}
      </section>
      <section className='grid content-start gap-2'>
        <h4 className='font-semibold'>{t('materials.warnings')}</h4>
        {warnings.map((w) => (
          <p key={w.heat_id} className='flex gap-2 text-amber-700'>
            <AlertTriangle className='size-4 shrink-0' /> {w.message}
          </p>
        ))}
        {!warnings.length ? (
          <p className='text-muted-foreground'>{t('materials.no_warnings')}</p>
        ) : null}
      </section>
    </div>
  )
}

export default function MaterialsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('materials.title')}
      description={t('materials.description')}
      projectScoped
    >
      {project ? (
        <Tabs defaultValue='heats' key={project.id}>
          <TabsList>
            <TabsTrigger value='heats'>{t('materials.tab.heats')}</TabsTrigger>
            <TabsTrigger value='receipts'>
              {t('materials.tab.receipts')}
            </TabsTrigger>
            <TabsTrigger value='trace'>{t('materials.tab.trace')}</TabsTrigger>
            <TabsTrigger value='holds'>{t('materials.tab.holds')}</TabsTrigger>
          </TabsList>
          <TabsContent value='heats'>
            <HeatsTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='receipts'>
            <ReceiptsTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='trace'>
            <TraceTab projectId={project.id} />
          </TabsContent>
          <TabsContent value='holds'>
            <HoldsAndWarnings projectId={project.id} />
          </TabsContent>
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('materials.no_project')}
        </p>
      )}
    </Page>
  )
}
