import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { ColDef } from 'ag-grid-community'
import { ArrowLeft, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { CreateGateDialog } from './gate-dialogs'
import { GATE_KINDS, GATE_STATUSES, statusTone } from './gate-rules'
import { type Gate, useGates } from './gates-api'
import { GateControls, GateDecision } from './gates-panel'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[10rem_1fr] gap-2 text-sm'>
      <span className='text-muted-foreground'>{label}</span>
      <span>{value || '—'}</span>
    </div>
  )
}

function GateSheet({ gate, onClose }: { gate: Gate; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <RecordSheet
      open
      onClose={onClose}
      title={`${gate.number} · ${gate.title}`}
      badges={
        <span
          className={`rounded px-1.5 py-0.5 text-xs ${statusTone(gate.status)}`}
        >
          {t(`inspections.gates.status.${gate.status}`)}
        </span>
      }
    >
      <div className='grid gap-2'>
        <Row
          label={t('inspections.gates.kind')}
          value={t(`inspections.gates.kind.${gate.kind}`)}
        />
        <Row
          label={t('inspections.gates.authority')}
          value={t(`inspections.gates.authority.${gate.authority}`)}
        />
        <Row
          label={t('inspections.gates.blocks')}
          value={
            gate.blocks_progress
              ? t('inspections.gates.blocks_yes')
              : t('inspections.gates.blocks_no')
          }
        />
        <Row
          label={t('inspections.gates.attachment')}
          value={
            gate.attachment_kind
              ? `${t(`inspections.gates.attachment.${gate.attachment_kind}`)} #${gate.attachment_id}`
              : t('inspections.gates.none')
          }
        />
        <Row
          label={t('inspections.gates.package_ref')}
          value={gate.package_ref}
        />
        <Row
          label={t('inspections.gates.approval_ref')}
          value={gate.approval_ref}
        />
        <Row
          label={t('inspections.gates.details')}
          value={gate.description}
        />
        <GateDecision gate={gate} />
        <div className='pt-2'>
          <GateControls gate={gate} />
        </div>
      </div>
    </RecordSheet>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState('')
  const [kind, setKind] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useGates(projectId, { status, kind })
  const open = rows.find((g) => g.id === openId)

  const columns = useMemo<ColDef<Gate>[]>(
    () => [
      {
        field: 'number',
        headerName: t('inspections.gates.number'),
        width: 120,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('inspections.gates.title'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'kind',
        headerName: t('inspections.gates.kind'),
        width: 130,
        valueFormatter: (p) => t(`inspections.gates.kind.${p.value}`),
      },
      {
        field: 'authority',
        headerName: t('inspections.gates.authority'),
        width: 230,
        valueFormatter: (p) => t(`inspections.gates.authority.${p.value}`),
      },
      {
        field: 'blocks_progress',
        headerName: t('inspections.gates.blocks'),
        width: 120,
        valueFormatter: (p) =>
          p.value
            ? t('inspections.gates.blocks_yes')
            : t('inspections.gates.blocks_no'),
      },
      {
        headerName: t('inspections.gates.attachment'),
        width: 170,
        valueGetter: (p) =>
          p.data?.attachment_kind
            ? `${t(`inspections.gates.attachment.${p.data.attachment_kind}`)} #${p.data.attachment_id}`
            : '',
      },
      {
        field: 'status',
        headerName: t('inspections.gates.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) =>
          p.value ? (
            <span
              className={`rounded px-1.5 py-0.5 text-xs ${statusTone(p.value)}`}
            >
              {t(`inspections.gates.status.${p.value}`)}
            </span>
          ) : null,
      },
    ],
    [t]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('inspections.gates.status')}
          placeholder={t('inspections.gates.all_statuses')}
          options={GATE_STATUSES.map((s) => ({
            value: s,
            label: t(`inspections.gates.status.${s}`),
          }))}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('inspections.gates.kind')}
          placeholder={t('inspections.gates.all_kinds')}
          options={GATE_KINDS.map((k) => ({
            value: k,
            label: t(`inspections.gates.kind.${k}`),
          }))}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        />
        {can(session, 'inspections.update') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('inspections.gates.new')}
          </Button>
        ) : null}
      </div>
      <div className='h-[480px]'>
        <DataGrid<Gate>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {open ? (
        <GateSheet key={open.id} gate={open} onClose={() => setOpenId(null)} />
      ) : null}
      {creating ? (
        <CreateGateDialog
          projectId={projectId}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </>
  )
}

export default function GatesPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.gates.page_title')}
      description={t('inspections.gates.description')}
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
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.gates.no_project')}
        </p>
      )}
    </Page>
  )
}
