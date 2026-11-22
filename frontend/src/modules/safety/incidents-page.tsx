import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  INCIDENT_NEXT,
  INCIDENT_STATUSES,
  INCIDENT_TYPES,
  type Incident,
  localDateTime,
  useIncident,
  useIncidentHistory,
  useIncidentStatus,
  useIncidents,
  useReportIncident,
  useUpdateIncident,
} from './api'
import { SafetyNav } from './dashboard-page'
import { ActionList, RiskBadge, RiskPicker } from './parts'

type Draft = {
  title: string
  type: string
  occurred_at: string
  severity: number
  likelihood: number
  location: string
  people: string
  description: string
  immediate_actions: string
  root_cause: string
  recordable: boolean
  lost_time: boolean
  days_lost: number
}

const fromIncident = (i?: Incident): Draft => ({
  title: i?.title ?? '',
  type: i?.type ?? 'near_miss',
  occurred_at: localDateTime(i?.occurred_at),
  severity: i?.severity ?? 1,
  likelihood: i?.likelihood ?? 1,
  location: i?.location ?? '',
  people: (i?.people_involved ?? []).join('\n'),
  description: i?.description ?? '',
  immediate_actions: i?.immediate_actions ?? '',
  root_cause: i?.root_cause ?? '',
  recordable: i?.recordable ?? false,
  lost_time: i?.lost_time ?? false,
  days_lost: i?.days_lost ?? 0,
})

const toBody = (d: Draft) => ({
  title: d.title,
  type: d.type as Incident['type'] as never,
  occurred_at: new Date(d.occurred_at).toISOString(),
  severity: d.severity,
  likelihood: d.likelihood,
  location: d.location || null,
  people_involved: d.people
    .split('\n')
    .map((p) => p.trim())
    .filter(Boolean),
  description: d.description || null,
  immediate_actions: d.immediate_actions || null,
  root_cause: d.root_cause || null,
  recordable: d.recordable,
  lost_time: d.lost_time,
  days_lost: d.lost_time ? d.days_lost : 0,
})

function IncidentForm({
  draft,
  setDraft,
  disabled,
}: {
  draft: Draft
  setDraft: (d: Draft) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const text = (key: keyof Draft) => ({
    value: draft[key] as string,
    disabled,
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >
    ) => setDraft({ ...draft, [key]: e.target.value }),
  })
  return (
    <div className='grid gap-3'>
      <div className='grid gap-1.5'>
        <Label htmlFor='inc-title'>{t('safety.incident_title')}</Label>
        <Input id='inc-title' required {...text('title')} />
      </div>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='grid gap-1.5'>
          <Label htmlFor='inc-type'>{t('safety.type')}</Label>
          <NativeSelect
            id='inc-type'
            values={INCIDENT_TYPES}
            {...text('type')}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='inc-when'>{t('safety.occurred_at')}</Label>
          <Input
            id='inc-when'
            type='datetime-local'
            required
            {...text('occurred_at')}
          />
        </div>
        <div className='grid gap-1.5 sm:col-span-2'>
          <Label htmlFor='inc-loc'>{t('safety.location')}</Label>
          <Input id='inc-loc' {...text('location')} />
        </div>
      </div>
      <RiskPicker
        severity={draft.severity}
        likelihood={draft.likelihood}
        disabled={disabled}
        onChange={(v) => setDraft({ ...draft, ...v })}
      />
      <div className='grid gap-1.5'>
        <Label htmlFor='inc-people'>{t('safety.people_involved')}</Label>
        <Textarea
          id='inc-people'
          placeholder={t('safety.one_per_line')}
          {...text('people')}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='inc-desc'>{t('safety.what_happened')}</Label>
        <Textarea id='inc-desc' {...text('description')} />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='inc-imm'>{t('safety.immediate_actions')}</Label>
        <Textarea id='inc-imm' {...text('immediate_actions')} />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='inc-root'>{t('safety.root_cause')}</Label>
        <Textarea id='inc-root' {...text('root_cause')} />
      </div>
      <div className='flex flex-wrap items-center gap-4'>
        <label className='flex items-center gap-2 text-sm'>
          <Checkbox
            checked={draft.recordable}
            disabled={disabled}
            onCheckedChange={(v) =>
              setDraft({ ...draft, recordable: v === true })
            }
          />
          {t('safety.recordable')}
        </label>
        <label className='flex items-center gap-2 text-sm'>
          <Checkbox
            checked={draft.lost_time}
            disabled={disabled}
            onCheckedChange={(v) =>
              setDraft({ ...draft, lost_time: v === true })
            }
          />
          {t('safety.lost_time')}
        </label>
        {draft.lost_time ? (
          <label className='flex items-center gap-2 text-sm'>
            {t('safety.days_lost')}
            <Input
              type='number'
              min={0}
              className='h-8 w-20'
              value={draft.days_lost}
              disabled={disabled}
              onChange={(e) =>
                setDraft({ ...draft, days_lost: Number(e.target.value) || 0 })
              }
            />
          </label>
        ) : null}
      </div>
    </div>
  )
}

function ReportDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const report = useReportIncident()
  const [draft, setDraft] = useState<Draft>(fromIncident())
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('safety.report_incident')}</DialogTitle>
        </DialogHeader>
        <form
          id='report-incident'
          onSubmit={(e) => {
            e.preventDefault()
            report.mutate(
              { project_id: projectId, ...toBody(draft) },
              {
                onSuccess: (made) => {
                  toast.success(t('safety.reported', { code: made.code }))
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <IncidentForm draft={draft} setDraft={setDraft} />
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='report-incident'
            className='h-11 w-full sm:w-auto'
            disabled={report.isPending}
          >
            {t('safety.submit_report')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useIncidentHistory(id)
  return (
    <ol className='grid gap-2 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex flex-wrap items-center gap-2'>
          <span className='text-xs text-muted-foreground tabular-nums'>
            {h.changed_at?.slice(0, 16).replace('T', ' ')}
          </span>
          <StatusBadge status={h.to_status} />
          <span className='text-muted-foreground'>{h.changed_by_name}</span>
          {h.note ? <span>· {h.note}</span> : null}
        </li>
      ))}
    </ol>
  )
}

function IncidentDetails({ incident }: { incident: Incident }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'safety.update')
  const update = useUpdateIncident(incident.id)
  const move = useIncidentStatus(incident.id)
  const [draft, setDraft] = useState<Draft>(fromIncident(incident))
  return (
    <div className='grid gap-4'>
      {can(session, 'safety.transition') ? (
        <div className='flex flex-wrap gap-2'>
          {(INCIDENT_NEXT[incident.status] ?? []).map((target) => (
            <Button
              key={target}
              size='sm'
              variant='outline'
              disabled={move.isPending}
              onClick={() => move.mutate({ status: target })}
            >
              → {statusLabel(target)}
            </Button>
          ))}
        </div>
      ) : null}
      <form
        className='grid gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          update.mutate(toBody(draft), {
            onSuccess: () => toast.success(t('safety.saved')),
          })
        }}
      >
        <IncidentForm draft={draft} setDraft={setDraft} disabled={!editable} />
        {editable ? (
          <Button type='submit' className='w-fit' disabled={update.isPending}>
            {t('safety.save')}
          </Button>
        ) : null}
      </form>
    </div>
  )
}

function IncidentSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { data: incident } = useIncident(id)
  return (
    <RecordSheet
      open={Boolean(id)}
      onClose={onClose}
      wide
      title={incident ? `${incident.code} · ${incident.title}` : '…'}
      subtitle={
        incident
          ? `${statusLabel(incident.type)} · ${new Date(incident.occurred_at).toLocaleString()}`
          : null
      }
      badges={
        incident ? (
          <>
            <StatusBadge status={incident.status} />
            <RiskBadge
              score={incident.risk_score}
              riskBand={incident.risk_band}
            />
            {incident.recordable ? <StatusBadge status='recordable' /> : null}
            {incident.lost_time ? <StatusBadge status='lost_time' /> : null}
          </>
        ) : null
      }
      record={
        incident
          ? {
              projectId: incident.project_id,
              entityType: 'safety_incident',
              entityId: incident.id,
            }
          : undefined
      }
      tabs={
        incident
          ? {
              [`${t('safety.actions')} (${incident.open_actions})`]: (
                <ActionList
                  projectId={incident.project_id}
                  parentType='incident'
                  parentId={incident.id}
                />
              ),
              [t('safety.history')]: <History id={incident.id} />,
            }
          : undefined
      }
    >
      {incident ? (
        <IncidentDetails
          key={`${incident.id}-${incident.status}`}
          incident={incident}
        />
      ) : null}
    </RecordSheet>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [openId, setOpenId] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get('id'))
    return id > 0 ? id : null
  })
  const [reporting, setReporting] = useState(false)
  const { data: rows = [] } = useIncidents(projectId, type, status)

  const columns = useMemo<ColDef<Incident>[]>(
    () => [
      {
        field: 'code',
        headerName: t('safety.ref'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'occurred_at',
        headerName: t('safety.occurred_at'),
        width: 150,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleString() : '',
      },
      {
        field: 'type',
        headerName: t('safety.type'),
        width: 160,
        valueFormatter: (p) => statusLabel(p.value ?? ''),
      },
      {
        field: 'title',
        headerName: t('safety.incident_title'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'location', headerName: t('safety.location'), width: 140 },
      {
        field: 'risk_score',
        headerName: t('safety.risk'),
        width: 120,
        cellRenderer: (p: ICellRendererParams<Incident>) =>
          p.data ? (
            <RiskBadge score={p.data.risk_score} riskBand={p.data.risk_band} />
          ) : null,
      },
      {
        field: 'recordable',
        headerName: t('safety.recordable_short'),
        width: 100,
        valueFormatter: (p) => (p.value ? '✓' : ''),
      },
      {
        field: 'days_lost',
        headerName: t('safety.days_lost'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) => (p.data?.lost_time ? String(p.value) : ''),
      },
      {
        field: 'status',
        headerName: t('safety.status'),
        width: 140,
        cellRenderer: (p: ICellRendererParams<Incident>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'open_actions',
        headerName: t('safety.open_actions'),
        width: 110,
        type: 'rightAligned',
      },
    ],
    [t]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-52'
          aria-label={t('safety.type')}
          placeholder={t('safety.all_types')}
          values={INCIDENT_TYPES}
          value={type}
          onChange={(e) => setType(e.target.value)}
        />
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('safety.status')}
          placeholder={t('safety.all_statuses')}
          values={INCIDENT_STATUSES}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
        {can(session, 'safety.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setReporting(true)}
          >
            <Plus /> {t('safety.report_incident')}
          </Button>
        ) : null}
      </div>
      <div className='h-[560px]'>
        <DataGrid<Incident>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {reporting ? (
        <ReportDialog
          projectId={projectId}
          onClose={() => setReporting(false)}
          onCreated={setOpenId}
        />
      ) : null}
      <IncidentSheet id={openId} onClose={() => setOpenId(null)} />
    </>
  )
}

export default function IncidentsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('safety.incidents')}
      description={t('safety.incidents_description')}
      projectScoped
      actions={<SafetyNav />}
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('safety.no_project')}
        </p>
      )}
    </Page>
  )
}
