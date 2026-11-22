import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Download, Eye, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import {
  fileUrl,
  formatSize,
  uploadFile,
  type StoredFile,
} from '@/components/records/files'

const CATEGORIES = [
  'drawing',
  'contract',
  'specification',
  'photo',
  'correspondence',
  'report',
  'model',
  'other',
]

function Preview({
  file,
  onClose,
}: {
  file: StoredFile | null
  onClose: () => void
}) {
  if (!file) return null
  const url = fileUrl(file.id, true)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-w-5xl'>
        <DialogHeader>
          <DialogTitle className='truncate'>
            {file.name}{' '}
            <span className='text-sm font-normal text-muted-foreground'>
              rev {file.revision}
            </span>
          </DialogTitle>
        </DialogHeader>
        {file.content_type.startsWith('image/') ? (
          <img
            src={url}
            alt={file.name}
            className='max-h-[75vh] w-full object-contain'
          />
        ) : file.content_type === 'application/pdf' ||
          file.content_type.startsWith('text/') ? (
          <iframe
            title={file.name}
            src={url}
            className='h-[75vh] w-full rounded-md border'
          />
        ) : (
          <p className='text-sm text-muted-foreground'>
            No preview for this file type.{' '}
            <a className='underline' href={fileUrl(file.id)}>
              Download it
            </a>
            .
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Documents({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [category, setCategory] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [preview, setPreview] = useState<StoredFile | null>(null)
  const { data } = useQuery({
    queryKey: ['files', projectId, 'documents', category, search],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/files/', {
          params: {
            query: {
              project_id: projectId,
              category: category === 'all' ? undefined : (category as never),
              search: search || undefined,
              items_per_page: 100,
            },
          },
        })
      ),
  })
  const files = useMemo(() => data?.data ?? [], [data])

  const upload = useMutation({
    mutationFn: async (list: FileList) => {
      for (const file of Array.from(list)) {
        const form = new FormData()
        form.set('file', file)
        const existing = files.find(
          (f) => f.name === file.name && !f.entity_type
        )
        if (existing) form.set('supersedes_id', String(existing.id))
        else form.set('project_id', String(projectId))
        await uploadFile(form)
      }
    },
    onSuccess: () => {
      toast.success('Uploaded')
      void queryClient.invalidateQueries({ queryKey: ['files', projectId] })
    },
    onError: handleServerError,
  })
  const retag = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: { category?: string; tags?: string[] }
    }) =>
      unwrap(
        api.PATCH('/api/v1/files/{file_id}', {
          params: { path: { file_id: id } },
          body: body as never,
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['files', projectId] }),
    onError: handleServerError,
  })

  const editable = can(session, 'files.upload')
  const columns = useMemo<ColDef<StoredFile>[]>(
    () => [
      { field: 'name', headerName: 'Name', flex: 2, minWidth: 240 },
      {
        field: 'category',
        headerName: 'Category',
        width: 150,
        editable,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: CATEGORIES },
      },
      {
        field: 'tags',
        headerName: 'Tags',
        flex: 1,
        editable,
        valueFormatter: (p) => (p.value ?? []).join(', '),
        valueParser: (p) =>
          String(p.newValue ?? '')
            .split(',')
            .map((s: string) => s.trim())
            .filter(Boolean),
        cellRenderer: (p: ICellRendererParams<StoredFile>) => (
          <span className='flex gap-1'>
            {(p.data?.tags ?? []).map((tag) => (
              <Badge key={tag} variant='secondary' className='h-5 text-[11px]'>
                {tag}
              </Badge>
            ))}
          </span>
        ),
      },
      { field: 'revision', headerName: 'Rev', width: 70, type: 'rightAligned' },
      {
        field: 'size',
        headerName: 'Size',
        width: 100,
        type: 'rightAligned',
        valueFormatter: (p) => formatSize(p.value),
      },
      { field: 'uploaded_by_name', headerName: 'Uploaded by', width: 160 },
      {
        field: 'created_at',
        headerName: 'Uploaded',
        width: 170,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleString() : '',
        sort: 'desc',
      },
      {
        headerName: '',
        width: 80,
        sortable: false,
        filter: false,
        cellRenderer: (p: ICellRendererParams<StoredFile>) =>
          p.data ? (
            <span className='flex h-full items-center gap-3'>
              <button aria-label='Preview' onClick={() => setPreview(p.data!)}>
                <Eye className='size-4' />
              </button>
              <a aria-label='Download' href={fileUrl(p.data.id)}>
                <Download className='size-4' />
              </a>
            </span>
          ) : null,
      },
    ],
    [editable]
  )

  return (
    <>
      <div className='flex flex-wrap items-center gap-2'>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger size='sm' className='h-8 w-44'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='all'>All categories</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c[0].toUpperCase() + c.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className='h-8 w-64'
          placeholder='Search name or tag'
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {editable ? (
          <>
            <input
              ref={input}
              type='file'
              multiple
              hidden
              onChange={(e) =>
                e.target.files?.length && upload.mutate(e.target.files)
              }
            />
            <Button
              size='sm'
              className='ms-auto'
              onClick={() => input.current?.click()}
              disabled={upload.isPending}
            >
              <Upload /> Upload
            </Button>
          </>
        ) : null}
      </div>
      <div
        className='h-[560px]'
        onDragOver={(e) => editable && e.preventDefault()}
        onDrop={(e) => {
          if (!editable) return
          e.preventDefault()
          if (e.dataTransfer.files.length) upload.mutate(e.dataTransfer.files)
        }}
      >
        <DataGrid
          rowData={files}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          singleClickEdit
          onCellValueChanged={(e) => {
            if (!e.data || !e.colDef.field) return
            retag.mutate({
              id: e.data.id,
              body: { [e.colDef.field]: e.newValue },
            })
          }}
          onRowDoubleClicked={(e) => e.data && setPreview(e.data)}
          overlayNoRowsTemplate={t('documents.description')}
        />
      </div>
      <Preview file={preview} onClose={() => setPreview(null)} />
    </>
  )
}

export default function DocumentsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('documents.title')}
      description={t('documents.description')}
      projectScoped
    >
      {project ? (
        <Documents key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>Choose a project.</p>
      )}
    </Page>
  )
}
