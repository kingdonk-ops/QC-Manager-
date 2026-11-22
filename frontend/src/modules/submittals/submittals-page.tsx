import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Download, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { handleServerError } from '@/lib/handle-server-error'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  STATUSES,
  TYPES,
  typeLabel,
  cleanWorkflow,
  useRefresh,
  useRegister,
  type RegisterFilters,
  type Submittal,
  type WorkflowStep,
} from './api'
import { SubmittalSheet } from './submittal-sheet'
import { WorkflowBuilder } from './workflow-builder'

function CreateDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const refresh = useRefresh(projectId)
  const [form, setForm] = useState({
    title: '',
    type: 'shop_drawing',
    spec_section: '',
    required_by: '',
    description: '',
  })
  const [workflow, setWorkflow] = useState<WorkflowStep[]>([
    { name: '', reviewer_ids: [], parallel: false },
  ])
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/submittals/', {
          body: {
            project_id: projectId,
            title: form.title,
            type: form.type as never,
            spec_section: form.spec_section || null,
            required_by: form.required_by || null,
            description: form.description || null,
            workflow: cleanWorkflow(workflow),
          },
        })
      ),
    onSuccess: (s) => {
      toast.success(`${s.code} created`)
      refresh()
      onCreated(s.id)
    },
    onError: handleServerError,
  })
  const set = (key: keyof typeof form) => (value: string) =>
    setForm((f) => ({ ...f, [key]: value }))
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>New submittal</DialogTitle>
        </DialogHeader>
        <form
          id='new-submittal'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate()
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='sub-title'>Title</Label>
            <Input
              id='sub-title'
              required
              value={form.title}
              onChange={(e) => set('title')(e.target.value)}
            />
          </div>
          <div className='grid gap-3 sm:grid-cols-3'>
            <div className='grid gap-1.5'>
              <Label>Type</Label>
              <Select value={form.type} onValueChange={set('type')}>
                <SelectTrigger className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {typeLabel(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='sub-spec'>Spec section</Label>
              <Input
                id='sub-spec'
                placeholder='e.g. 15 10 00'
                value={form.spec_section}
                onChange={(e) => set('spec_section')(e.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='sub-due'>Required by</Label>
              <Input
                id='sub-due'
                type='date'
                value={form.required_by}
                onChange={(e) => set('required_by')(e.target.value)}
              />
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='sub-desc'>Description</Label>
            <Textarea
              id='sub-desc'
              value={form.description}
              onChange={(e) => set('description')(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label>Review workflow</Label>
            <WorkflowBuilder value={workflow} onChange={setWorkflow} />
          </div>
        </form>
        <DialogFooter>
          <Button
            form='new-submittal'
            type='submit'
            disabled={create.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function download(projectId: number, filters: RegisterFilters) {
  const query = new URLSearchParams({
    project_id: String(projectId),
    format: 'xlsx',
  })
  for (const [key, value] of Object.entries(filters))
    if (value) query.set(key, String(value))
  window.location.href = `/api/v1/submittals/export?${query}`
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [filters, setFilters] = useState<RegisterFilters>({})
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get('id'))
    return id > 0 ? id : null
  })
  const { data } = useRegister(projectId, filters)
  const rows = useMemo(() => data?.data ?? [], [data])

  const columns = useMemo<ColDef<Submittal>[]>(
    () => [
      { field: 'code', headerName: 'Code', width: 100 },
      { field: 'title', headerName: 'Title', flex: 2, minWidth: 220 },
      {
        field: 'type',
        headerName: 'Type',
        width: 140,
        valueFormatter: (p) => typeLabel(p.value ?? ''),
      },
      { field: 'spec_section', headerName: 'Spec', width: 100 },
      {
        field: 'revision_letter',
        headerName: 'Rev',
        width: 70,
        valueFormatter: (p) => p.value ?? '',
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 170,
        cellRenderer: (p: ICellRendererParams<Submittal>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'current_reviewers',
        headerName: 'With',
        flex: 1,
        minWidth: 160,
        valueFormatter: (p) => (p.value ?? []).join(', '),
      },
      { field: 'submitted_by_name', headerName: 'Submitted by', width: 150 },
      {
        field: 'required_by',
        headerName: 'Required by',
        width: 120,
        cellClass: (p) => (p.data?.overdue ? 'text-red-600 font-medium' : ''),
      },
      {
        field: 'days_outstanding',
        headerName: 'Days out',
        width: 95,
        type: 'rightAligned',
      },
    ],
    []
  )

  const patch = (next: Partial<RegisterFilters>) =>
    setFilters((f) => ({ ...f, ...next }))

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Select
          value={filters.status ?? 'all'}
          onValueChange={(v) => patch({ status: v === 'all' ? undefined : v })}
        >
          <SelectTrigger size='sm' className='h-8 w-48'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>All statuses</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {statusLabel(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className='h-8 w-36'
          placeholder='Spec section'
          value={filters.spec_section ?? ''}
          onChange={(e) => patch({ spec_section: e.target.value })}
        />
        <Input
          className='h-8 w-56'
          placeholder='Search code or title'
          value={filters.search ?? ''}
          onChange={(e) => patch({ search: e.target.value })}
        />
        <Label className='flex items-center gap-2 text-sm font-normal'>
          <Switch
            checked={filters.reviewer === 'me'}
            onCheckedChange={(on) => patch({ reviewer: on ? 'me' : undefined })}
          />
          Waiting for me
        </Label>
        <Label className='flex items-center gap-2 text-sm font-normal'>
          <Switch
            checked={Boolean(filters.overdue)}
            onCheckedChange={(on) => patch({ overdue: on || undefined })}
          />
          Overdue
        </Label>
        <div className='ms-auto flex gap-2'>
          {can(session, 'submittals.export') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => download(projectId, filters)}
            >
              <Download /> Export
            </Button>
          ) : null}
          {can(session, 'submittals.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> New submittal
            </Button>
          ) : null}
        </div>
      </div>
      <div className='h-[560px]'>
        <DataGrid
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpen(e.data.id)}
          rowClass='cursor-pointer'
          overlayNoRowsTemplate={t('submittals.empty')}
        />
      </div>
      {creating ? (
        <CreateDialog
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false)
            setOpen(id)
          }}
        />
      ) : null}
      <SubmittalSheet id={open} onClose={() => setOpen(null)} />
    </>
  )
}

export default function SubmittalsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('submittals.title')}
      description={t('submittals.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>Choose a project.</p>
      )}
    </Page>
  )
}
