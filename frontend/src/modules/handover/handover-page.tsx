import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NodeSelect } from '@/components/asset-node-picker'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Filter,
  type Handover,
  handoverApi,
  useHandoverMutation,
  useHandovers,
} from './api'
import { HandoverSheet } from './handover-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

export default function HandoverPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('handover.title')}
      description={t('handover.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('handover.no_project')}
        </p>
      )}
    </Page>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [filter, setFilter] = useState<Filter>('all')
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [creating, setCreating] = useState(false)
  const { data: rows = [] } = useHandovers(projectId, filter)
  const { data: waiting = [] } = useHandovers(projectId, 'to')
  const pending = waiting.filter((h) => h.status === 'submitted')

  const columns = useMemo<ColDef<Handover>[]>(
    () => [
      { field: 'code', headerName: t('handover.code'), width: 90 },
      { field: 'shift_date', headerName: t('handover.date'), width: 110 },
      {
        headerName: t('handover.shift'),
        width: 120,
        valueGetter: (p) => `${p.data?.from_shift} → ${p.data?.to_shift}`,
      },
      {
        field: 'area_name',
        headerName: t('handover.area'),
        flex: 1,
        minWidth: 160,
      },
      { field: 'author_name', headerName: t('handover.from'), width: 150 },
      { field: 'recipient_name', headerName: t('handover.to'), width: 150 },
      {
        field: 'status',
        headerName: t('handover.status'),
        width: 130,
        cellRenderer: (p: ICellRendererParams<Handover>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'open_count',
        headerName: t('handover.open'),
        width: 90,
        type: 'rightAligned',
      },
      {
        field: 'waiting_hours',
        headerName: t('handover.waiting'),
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) => (p.value == null ? '' : `${p.value} h`),
      },
    ],
    [t]
  )

  return (
    <>
      {pending.length ? (
        <div className='rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm'>
          <div className='font-medium'>{t('handover.for_you')}</div>
          <ul className='mt-1 grid gap-1'>
            {pending.map((h) => (
              <li key={h.id}>
                <button
                  type='button'
                  className='text-primary hover:underline'
                  onClick={() => setOpenId(h.id)}
                >
                  {h.code} · {h.shift_date} · {h.area_name ?? '—'} ·{' '}
                  {h.author_name}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-52'
          aria-label={t('handover.filter')}
          options={[
            { value: 'all', label: t('handover.all') },
            { value: 'to', label: t('handover.to_me') },
            { value: 'from', label: t('handover.from_me') },
            { value: 'waiting', label: t('handover.unacknowledged') },
          ]}
          value={filter}
          onChange={(e) => setFilter(e.target.value as Filter)}
        />
        {can(session, 'handover.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('handover.new')}
          </Button>
        ) : null}
      </div>
      <div className='h-[560px]'>
        <DataGrid<Handover>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {creating ? (
        <NewHandover
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={setOpenId}
        />
      ) : null}
      <HandoverSheet id={openId} onClose={() => setOpenId(null)} />
    </>
  )
}

function NewHandover({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useHandoverMutation(handoverApi.create)
  const [draft, setDraft] = useState({
    shift_date: new Date().toLocaleDateString('en-CA'),
    from_shift: 'day',
    to_shift: 'night',
    area_node_id: null as number | null,
    area_label: null as string | null,
    recipient_id: null as number | null,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('handover.new')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-handover'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                shift_date: draft.shift_date,
                from_shift: draft.from_shift as never,
                to_shift: draft.to_shift as never,
                area_node_id: draft.area_node_id,
                recipient_id: draft.recipient_id,
                carry_forward: true,
                items: [],
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <div className='grid grid-cols-3 gap-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='ho-date'>{t('handover.date')}</Label>
              <Input
                id='ho-date'
                type='date'
                required
                value={draft.shift_date}
                onChange={(e) =>
                  setDraft({ ...draft, shift_date: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='ho-from'>{t('handover.from_shift')}</Label>
              <NativeSelect
                id='ho-from'
                values={['day', 'night']}
                value={draft.from_shift}
                onChange={(e) =>
                  setDraft({ ...draft, from_shift: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='ho-to'>{t('handover.to_shift')}</Label>
              <NativeSelect
                id='ho-to'
                values={['day', 'night']}
                value={draft.to_shift}
                onChange={(e) =>
                  setDraft({ ...draft, to_shift: e.target.value })
                }
              />
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label>{t('handover.area')}</Label>
            <NodeSelect
              projectId={projectId}
              value={draft.area_node_id}
              label={draft.area_label}
              placeholder={t('handover.whole_project')}
              onChange={(id, n) =>
                setDraft({
                  ...draft,
                  area_node_id: id,
                  area_label: n ? n.display_path : null,
                })
              }
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>{t('handover.incoming')}</Label>
            <UserSelect
              value={draft.recipient_id}
              onChange={(id) => setDraft({ ...draft, recipient_id: id })}
            />
          </div>
          <p className='text-xs text-muted-foreground'>
            {t('handover.carry_help')}
          </p>
        </form>
        <DialogFooter>
          <Button type='submit' form='new-handover' disabled={create.isPending}>
            {t('handover.start')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
