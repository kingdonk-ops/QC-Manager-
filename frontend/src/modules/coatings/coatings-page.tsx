import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus, Trash2 } from 'lucide-react'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { NodeSelect } from '@/components/node-select'
import { Field } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Job,
  useCreateJob,
  useCreateSystem,
  useJobs,
  useSystems,
} from './api'
import { type DftRule, RULES } from './calc'
import { JobSheet } from './job-sheet'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

type Coat = { name: string; product: string; min: string; max: string }

function NewSystem({
  projectId,
  onClose,
}: {
  projectId: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreateSystem()
  const [draft, setDraft] = useState({
    code: '',
    name: '',
    surface_prep_standard: 'ISO 8501-1 Sa 2½',
    profile_min_um: '50',
    profile_max_um: '85',
    dft_rule: '80/20' as DftRule,
  })
  const [coats, setCoats] = useState<Coat[]>([
    { name: 'Primer', product: '', min: '', max: '' },
  ])
  const set = (key: keyof typeof draft) => ({
    value: draft[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setDraft({ ...draft, [key]: e.target.value }),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>{t('coatings.new_system')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-system'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                code: draft.code,
                name: draft.name,
                surface_prep_standard: draft.surface_prep_standard || null,
                profile_min_um: draft.profile_min_um
                  ? Number(draft.profile_min_um)
                  : null,
                profile_max_um: draft.profile_max_um
                  ? Number(draft.profile_max_um)
                  : null,
                dft_rule: draft.dft_rule,
                dew_point_margin_c: 3,
                max_rh_pct: 85,
                coats: coats.map((c) => ({
                  name: c.name,
                  product: c.product || null,
                  dft_min_um: Number(c.min),
                  dft_max_um: c.max ? Number(c.max) : null,
                })),
              },
              { onSuccess: onClose }
            )
          }}
        >
          <div className='grid grid-cols-3 gap-2'>
            <Field label={t('coatings.code')}>
              <Input required {...set('code')} />
            </Field>
            <Field label={t('coatings.name')} className='col-span-2'>
              <Input required {...set('name')} />
            </Field>
            <Field label={t('coatings.surface_prep')}>
              <Input {...set('surface_prep_standard')} />
            </Field>
            <Field label={t('coatings.profile_min')}>
              <Input type='number' {...set('profile_min_um')} />
            </Field>
            <Field label={t('coatings.profile_max')}>
              <Input type='number' {...set('profile_max_um')} />
            </Field>
            <Field label={t('coatings.rule')}>
              <NativeSelect
                options={RULES.map((r) => ({ value: r, label: r }))}
                {...set('dft_rule')}
              />
            </Field>
          </div>
          <h4 className='text-sm font-semibold'>{t('coatings.coats')}</h4>
          {coats.map((c, i) => {
            const edit = (key: keyof Coat) => ({
              value: c[key],
              onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
                setCoats(
                  coats.map((x, j) =>
                    j === i ? { ...x, [key]: e.target.value } : x
                  )
                ),
            })
            return (
              <div
                key={i}
                className='grid grid-cols-[1fr_1fr_5rem_5rem_auto] gap-2'
              >
                <Input
                  aria-label={t('coatings.coat')}
                  required
                  {...edit('name')}
                />
                <Input
                  aria-label={t('coatings.product')}
                  placeholder={t('coatings.product')}
                  {...edit('product')}
                />
                <Input
                  aria-label='DFT min'
                  placeholder='min µm'
                  type='number'
                  required
                  {...edit('min')}
                />
                <Input
                  aria-label='DFT max'
                  placeholder='max µm'
                  type='number'
                  {...edit('max')}
                />
                <Button
                  type='button'
                  size='icon'
                  variant='ghost'
                  aria-label={t('coatings.remove')}
                  onClick={() => setCoats(coats.filter((_, j) => j !== i))}
                >
                  <Trash2 />
                </Button>
              </div>
            )
          })}
          <Button
            type='button'
            size='sm'
            variant='outline'
            onClick={() =>
              setCoats([
                ...coats,
                {
                  name: `Coat ${coats.length + 1}`,
                  product: '',
                  min: '',
                  max: '',
                },
              ])
            }
          >
            <Plus /> {t('coatings.add_coat')}
          </Button>
        </form>
        <DialogFooter>
          <Button type='submit' form='new-system' disabled={create.isPending}>
            {t('coatings.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NewJob({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const { data: systems = [] } = useSystems(projectId)
  const create = useCreateJob()
  const [title, setTitle] = useState('')
  const [systemId, setSystemId] = useState('')
  const [nodeId, setNodeId] = useState<number | null>(null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('coatings.new_job')}</DialogTitle>
        </DialogHeader>
        <Field label={t('coatings.job_title')}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label={t('coatings.system')}>
          <NativeSelect
            placeholder='—'
            options={systems.map((s) => ({
              value: String(s.id),
              label: `${s.code} ${s.name}`,
            }))}
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
          />
        </Field>
        <Field label={t('coatings.work_anchor')}>
          <NodeSelect
            projectId={projectId}
            value={nodeId}
            onChange={setNodeId}
          />
        </Field>
        <DialogFooter>
          <Button
            disabled={!title || !systemId || !nodeId || create.isPending}
            onClick={() =>
              create.mutate(
                {
                  project_id: projectId,
                  title,
                  system_id: Number(systemId),
                  node_id: nodeId ?? 0,
                },
                {
                  onSuccess: (made) => {
                    onClose()
                    onCreated(made.id)
                  },
                }
              )
            }
          >
            {t('coatings.start')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Jobs({
  projectId,
  onOpen,
}: {
  projectId: number
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const [status, setStatus] = useState('')
  const { data: rows = [] } = useJobs(projectId, status)
  const columns = useMemo<ColDef<Job>[]>(
    () => [
      { field: 'code', headerName: t('coatings.code'), width: 100 },
      {
        field: 'title',
        headerName: t('coatings.job_title'),
        flex: 1,
        minWidth: 200,
      },
      { field: 'system_code', headerName: t('coatings.system'), width: 110 },
      { field: 'node_path', headerName: t('coatings.work_anchor'), width: 220 },
      {
        field: 'current_stage',
        headerName: t('coatings.hold_point'),
        width: 180,
      },
      {
        field: 'status',
        headerName: t('coatings.status'),
        width: 130,
        cellRenderer: (p: ICellRendererParams<Job>) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-3'>
      <NativeSelect
        className='h-8 w-44'
        aria-label={t('coatings.status')}
        placeholder={t('coatings.all_statuses')}
        values={['open', 'in_progress', 'passed', 'failed']}
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      />
      <div className='h-[520px]'>
        <DataGrid<Job>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && onOpen(e.data.id)}
        />
      </div>
    </div>
  )
}

function Systems({ projectId }: { projectId: number }) {
  const { data = [] } = useSystems(projectId)
  return (
    <div className='grid gap-2 md:grid-cols-2'>
      {data.map((s) => (
        <div key={s.id} className='rounded-md border p-3 text-sm'>
          <div className='font-semibold'>
            {s.code} · {s.name}
          </div>
          <div className='text-muted-foreground'>
            {s.surface_prep_standard} · profile {s.profile_min_um ?? '–'}–
            {s.profile_max_um ?? '–'} µm · {s.dft_rule}
          </div>
          <ol className='mt-1 list-decimal ps-5'>
            {s.coats.map((c, i) => (
              <li key={i}>
                {String(c.name)} {c.product ? `(${String(c.product)})` : ''} ·{' '}
                {String(c.dft_min_um)}–{String(c.dft_max_um ?? '∞')} µm
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

export default function CoatingsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [newJob, setNewJob] = useState(false)
  const [newSystem, setNewSystem] = useState(false)
  return (
    <Page
      title={t('coatings.title')}
      description={t('coatings.description')}
      projectScoped
      actions={
        project && can(session, 'coatings.create') ? (
          <>
            <Button
              size='sm'
              variant='outline'
              onClick={() => setNewSystem(true)}
            >
              <Plus /> {t('coatings.new_system')}
            </Button>
            <Button size='sm' onClick={() => setNewJob(true)}>
              <Plus /> {t('coatings.new_job')}
            </Button>
          </>
        ) : null
      }
    >
      {project ? (
        <Tabs defaultValue='jobs' key={project.id}>
          <TabsList>
            <TabsTrigger value='jobs'>{t('coatings.jobs')}</TabsTrigger>
            <TabsTrigger value='systems'>{t('coatings.systems')}</TabsTrigger>
          </TabsList>
          <TabsContent value='jobs'>
            <Jobs projectId={project.id} onOpen={setOpenId} />
          </TabsContent>
          <TabsContent value='systems'>
            <Systems projectId={project.id} />
          </TabsContent>
          {newSystem ? (
            <NewSystem
              projectId={project.id}
              onClose={() => setNewSystem(false)}
            />
          ) : null}
          {newJob ? (
            <NewJob
              projectId={project.id}
              onClose={() => setNewJob(false)}
              onCreated={setOpenId}
            />
          ) : null}
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('coatings.no_project')}
        </p>
      )}
      <JobSheet id={openId} onClose={() => setOpenId(null)} />
    </Page>
  )
}
