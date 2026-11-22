import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Blocks, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useProjectStore } from '@/stores/project-store'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { useProjects, type Project } from './api'
import { CLASSIFICATIONS } from './constants'
import { ProjectForm } from './project-form'
import { ProjectModulesDialog } from './project-modules-dialog'

function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-w-xl'>
        <DialogHeader>
          <DialogTitle>{t('projects.new')}</DialogTitle>
        </DialogHeader>
        {open ? (
          <ProjectForm
            formId='new-project'
            onCreated={() => {
              toast.success('Project created')
              onOpenChange(false)
            }}
          />
        ) : null}
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type='submit' form='new-project'>
            {t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ProjectsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const { data: projects = [] } = useProjects()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const [creating, setCreating] = useState(false)
  const [overriding, setOverriding] = useState<Project | null>(null)

  const columns = useMemo<ColDef<Project>[]>(
    () => [
      {
        field: 'code',
        headerName: t('projects.code'),
        width: 120,
        pinned: 'left',
        cellClass: 'font-mono',
      },
      { field: 'name', headerName: t('projects.name'), flex: 2, minWidth: 200 },
      { field: 'client_name', headerName: t('projects.client'), flex: 1 },
      { field: 'location', headerName: t('projects.location'), flex: 1 },
      { field: 'status', headerName: t('projects.status'), width: 120 },
      { field: 'region', headerName: 'Region', width: 90 },
      {
        field: 'classification_standard',
        headerName: 'Classification',
        width: 140,
        valueFormatter: (p) =>
          CLASSIFICATIONS.find(([v]) => v === p.value)?.[1] ?? p.value ?? '',
      },
      { field: 'currency', headerName: t('projects.currency'), width: 100 },
      ...(can(session, 'projects.update')
        ? [
            {
              headerName: '',
              width: 56,
              sortable: false,
              filter: false,
              cellRenderer: (p: ICellRendererParams<Project>) =>
                p.data ? (
                  <button
                    aria-label='Project modules'
                    title='Modules for this project'
                    onClick={() => setOverriding(p.data!)}
                  >
                    <Blocks className='size-4 text-muted-foreground hover:text-foreground' />
                  </button>
                ) : null,
            } satisfies ColDef<Project>,
          ]
        : []),
    ],
    [t, session]
  )

  return (
    <Page
      title={t('projects.title')}
      description={t('projects.description')}
      fixed
      actions={
        can(session, 'projects.create') ? (
          <Button size='sm' onClick={() => setCreating(true)}>
            <Plus /> {t('projects.new')}
          </Button>
        ) : null
      }
    >
      <div className='min-h-80 flex-1'>
        <DataGrid
          rowData={projects}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setProjectId(e.data.id)}
          rowSelection={{
            mode: 'singleRow',
            checkboxes: false,
            enableClickSelection: true,
          }}
        />
      </div>
      <NewProjectDialog open={creating} onOpenChange={setCreating} />
      <ProjectModulesDialog
        project={overriding}
        onClose={() => setOverriding(null)}
      />
    </Page>
  )
}
