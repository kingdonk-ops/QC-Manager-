import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { ArrowDown, ArrowUp, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Dossier,
  useCatalogue,
  useCreateDossier,
  useDossier,
  useDossiers,
  useHistory,
  useUpdateDossier,
} from './api'
import { Readiness } from './dossier-gate-panel'
import { Revisions } from './dossier-revisions'
import { type Section, moveSection } from './lib'
import { ScopePicker } from './scope-picker'

function initialId() {
  const id = Number(new URLSearchParams(window.location.search).get('id'))
  return Number.isFinite(id) && id > 0 ? id : null
}

function NewDossier({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateDossier()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('mdr.new')}</DialogTitle>
          <DialogDescription>{t('mdr.new_hint')}</DialogDescription>
        </DialogHeader>
        <form
          id='new-dossier'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                title,
                description: description || null,
                scope_node_ids: [],
                scope_collection_ids: [],
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
          <div className='grid gap-1.5'>
            <Label htmlFor='dossier-title'>{t('mdr.title_field')}</Label>
            <Input
              id='dossier-title'
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='dossier-desc'>{t('mdr.description_field')}</Label>
            <Textarea
              id='dossier-desc'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </form>
        <DialogFooter>
          <Button type='submit' form='new-dossier' disabled={create.isPending}>
            {t('mdr.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Outline({ dossier }: { dossier: Dossier }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: catalogue = [] } = useCatalogue(dossier.project_id)
  const update = useUpdateDossier(dossier.id)
  const [nodes, setNodes] = useState<number[]>(dossier.scope_node_ids)
  const [collections, setCollections] = useState<number[]>(
    dossier.scope_collection_ids
  )
  const [sections, setSections] = useState<Section[]>(dossier.sections)
  const editable = can(session, 'mdr.update') && dossier.status !== 'final'
  const providers = Object.fromEntries(
    catalogue.map((c) => [c.key, c.generated ? ['index'] : c.providers])
  )
  const dirty =
    JSON.stringify([nodes, collections, sections]) !==
    JSON.stringify([
      dossier.scope_node_ids,
      dossier.scope_collection_ids,
      dossier.sections,
    ])
  return (
    <div className='grid gap-4'>
      <section className='grid gap-2'>
        <h4 className='text-sm font-medium'>{t('mdr.scope')}</h4>
        <p className='text-xs text-muted-foreground'>
          {dossier.scope_labels.length
            ? dossier.scope_labels.join(', ')
            : t('mdr.whole_project')}
        </p>
        {editable ? (
          <ScopePicker
            projectId={dossier.project_id}
            nodeIds={nodes}
            collectionIds={collections}
            onChange={(n, c) => {
              setNodes(n)
              setCollections(c)
            }}
          />
        ) : null}
      </section>
      <section className='grid gap-2'>
        <h4 className='text-sm font-medium'>{t('mdr.sections')}</h4>
        <ol className='grid gap-1'>
          {sections.map((s, i) => (
            <li
              key={s.key}
              className='flex items-center gap-2 rounded-md border px-2 py-1 text-sm'
            >
              <Checkbox
                aria-label={s.title}
                checked={s.enabled}
                disabled={!editable}
                onCheckedChange={(on) =>
                  setSections(
                    sections.map((x, j) =>
                      j === i ? { ...x, enabled: Boolean(on) } : x
                    )
                  )
                }
              />
              <span className={s.enabled ? '' : 'text-muted-foreground'}>
                {s.title}
              </span>
              {(providers[s.key] ?? []).length ? (
                <span className='text-xs text-muted-foreground'>
                  {(providers[s.key] ?? []).join(', ')}
                </span>
              ) : (
                <Badge variant='outline' className='text-xs'>
                  {t('mdr.not_available')}
                </Badge>
              )}
              {editable ? (
                <span className='ms-auto flex gap-1'>
                  <Button
                    size='icon'
                    variant='ghost'
                    className='size-6'
                    aria-label={t('mdr.up')}
                    onClick={() => setSections(moveSection(sections, i, -1))}
                  >
                    <ArrowUp />
                  </Button>
                  <Button
                    size='icon'
                    variant='ghost'
                    className='size-6'
                    aria-label={t('mdr.down')}
                    onClick={() => setSections(moveSection(sections, i, 1))}
                  >
                    <ArrowDown />
                  </Button>
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      </section>
      {editable ? (
        <div>
          <Button
            size='sm'
            disabled={!dirty || update.isPending}
            onClick={() =>
              update.mutate({
                scope_node_ids: nodes,
                scope_collection_ids: collections,
                sections,
              })
            }
          >
            {t('mdr.save_outline')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHistory(id)
  return (
    <ul className='grid gap-1 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='flex gap-2'>
          <span className='text-muted-foreground'>
            {h.changed_at ? new Date(h.changed_at).toLocaleString() : ''}
          </span>
          <StatusBadge status={h.from_status} /> →{' '}
          <StatusBadge status={h.to_status} />
          {h.note ? <span>{h.note}</span> : null}
        </li>
      ))}
    </ul>
  )
}

function DossierSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { data: dossier } = useDossier(id)
  return (
    <RecordSheet
      open={Boolean(id)}
      onClose={onClose}
      wide
      title={dossier ? `${dossier.code} ${dossier.title}` : ''}
      subtitle={dossier?.description ?? undefined}
      badges={
        dossier ? (
          <>
            <StatusBadge status={dossier.status} />
            {dossier.current_revision ? (
              <Badge variant='outline'>Rev {dossier.current_revision}</Badge>
            ) : null}
          </>
        ) : null
      }
      record={
        dossier
          ? {
              projectId: dossier.project_id,
              entityType: 'mdr_dossier',
              entityId: dossier.id,
            }
          : undefined
      }
      tabs={
        dossier
          ? {
              [t('mdr.revisions')]: <Revisions dossier={dossier} />,
              [t('mdr.history')]: <History id={dossier.id} />,
            }
          : undefined
      }
    >
      {dossier ? (
        <div className='grid gap-6'>
          <Outline key={dossier.updated_at ?? dossier.id} dossier={dossier} />
          <Readiness dossier={dossier} />
        </div>
      ) : null}
    </RecordSheet>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: rows = [] } = useDossiers(projectId)
  const [openId, setOpenId] = useState<number | null>(initialId)
  const [creating, setCreating] = useState(false)
  const columns = useMemo<ColDef<Dossier>[]>(
    () => [
      {
        field: 'code',
        headerName: t('mdr.code'),
        width: 180,
        cellClass: 'font-mono',
      },
      { field: 'title', headerName: t('mdr.title_field'), flex: 1 },
      {
        headerName: t('mdr.scope'),
        width: 220,
        valueGetter: (p) =>
          p.data?.scope_labels.length
            ? p.data.scope_labels.join(', ')
            : t('mdr.whole_project'),
      },
      {
        field: 'status',
        headerName: t('mdr.status'),
        width: 130,
        cellRenderer: (p: ICellRendererParams<Dossier>) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'current_revision', headerName: 'Rev', width: 80 },
    ],
    [t]
  )
  return (
    <>
      <div className='flex'>
        {can(session, 'mdr.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('mdr.new')}
          </Button>
        ) : null}
      </div>
      <div className='h-[520px]'>
        <DataGrid<Dossier>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {creating ? (
        <NewDossier
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={setOpenId}
        />
      ) : null}
      <DossierSheet id={openId} onClose={() => setOpenId(null)} />
    </>
  )
}

export default function MdrPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('mdr.title')}
      description={t('mdr.description')}
      projectScoped
    >
      {project ? (
        <Register key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('mdr.no_project')}</p>
      )}
    </Page>
  )
}
