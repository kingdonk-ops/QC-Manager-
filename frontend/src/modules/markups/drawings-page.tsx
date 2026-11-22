import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import type { ColDef } from 'ag-grid-community'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import type { StoredFile } from '@/components/records/files'

const isPdf = (f: StoredFile) =>
  f.content_type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')

function Drawings({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const { data } = useQuery({
    queryKey: ['files', projectId, 'pdfs', search],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/files/', {
          params: {
            query: {
              project_id: projectId,
              search: search || undefined,
              items_per_page: 100,
            },
          },
        })
      ),
  })
  const pdfs = useMemo(() => (data?.data ?? []).filter(isPdf), [data])
  const columns = useMemo<ColDef<StoredFile>[]>(
    () => [
      { field: 'name', headerName: 'Drawing', flex: 2, minWidth: 260 },
      { field: 'category', headerName: 'Category', width: 140 },
      { field: 'revision', headerName: 'Rev', width: 80, type: 'rightAligned' },
      { field: 'uploaded_by_name', headerName: 'Uploaded by', width: 170 },
      {
        field: 'created_at',
        headerName: 'Uploaded',
        width: 180,
        sort: 'desc',
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleString() : '',
      },
    ],
    []
  )
  return (
    <>
      <Input
        className='h-8 w-64'
        placeholder='Search drawings'
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className='h-[560px]'>
        <DataGrid
          rowData={pdfs}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) =>
            e.data &&
            void navigate({
              to: '/$',
              params: { _splat: `markups/${e.data.id}` },
            })
          }
          overlayNoRowsTemplate={t('markups.none')}
        />
      </div>
    </>
  )
}

export default function DrawingsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('markups.title')}
      description={t('markups.description')}
      projectScoped
    >
      {project ? (
        <Drawings key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>Choose a project.</p>
      )}
    </Page>
  )
}
