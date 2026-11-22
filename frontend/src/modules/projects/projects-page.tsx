import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { ColDef } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useProjectStore } from '@/stores/project-store'
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
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { projectKeys, useProjects, type Project } from './api'

function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: (body: Record<string, string>) =>
      unwrap(api.POST('/api/v1/projects/', { body: body as never })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all })
      toast.success('Project created')
      onOpenChange(false)
    },
    onError: handleServerError,
  })

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const body: Record<string, string> = {}
    for (const [key, value] of form.entries())
      if (String(value).trim()) body[key] = String(value).trim()
    create.mutate(body)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('projects.new')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-project'
          className='grid grid-cols-2 gap-3'
          onSubmit={onSubmit}
        >
          {(['code', 'name', 'client_name', 'location'] as const).map(
            (field) => (
              <div key={field} className='grid gap-1.5'>
                <Label htmlFor={field}>
                  {t(`projects.${field === 'client_name' ? 'client' : field}`)}
                </Label>
                <Input
                  id={field}
                  name={field}
                  required={field === 'code' || field === 'name'}
                />
              </div>
            )
          )}
          <div className='grid gap-1.5'>
            <Label htmlFor='currency'>{t('projects.currency')}</Label>
            <Input
              id='currency'
              name='currency'
              defaultValue='AUD'
              maxLength={3}
            />
          </div>
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type='submit' form='new-project' disabled={create.isPending}>
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
      { field: 'currency', headerName: t('projects.currency'), width: 100 },
    ],
    [t]
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
    </Page>
  )
}
