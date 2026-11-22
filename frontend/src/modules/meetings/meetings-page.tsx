import { useMemo, useState } from 'react'
import { useRecordParam } from '@/modules/tasks/deep-link'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus, Repeat } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Meeting,
  type Series,
  useMeeting,
  useMeetings,
  useSeries,
} from './api'
import { formatWhen } from './format'
import { NewMeetingDialog, SeriesDialog } from './meeting-dialogs'
import { MeetingEditor } from './meeting-editor'

function MeetingsGrid({
  projectId,
  onOpen,
}: {
  projectId: number
  onOpen: (m: Meeting) => void
}) {
  const { t } = useTranslation()
  const { data: meetings = [] } = useMeetings(projectId)
  const columns = useMemo<ColDef<Meeting>[]>(
    () => [
      {
        field: 'code',
        headerName: t('meetings.code'),
        width: 110,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('meetings.title_field'),
        flex: 1,
        minWidth: 220,
        cellClass: 'font-medium',
      },
      {
        field: 'starts_at',
        headerName: t('meetings.when'),
        width: 210,
        valueFormatter: (p) => (p.value ? formatWhen(p.value) : ''),
      },
      { field: 'series_name', headerName: t('meetings.series'), width: 200 },
      { field: 'location', headerName: t('meetings.location'), width: 160 },
      {
        field: 'status',
        headerName: t('meetings.status'),
        width: 150,
        cellRenderer: (p: ICellRendererParams<Meeting>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'attendee_count',
        headerName: t('meetings.attendees'),
        width: 110,
        type: 'rightAligned',
      },
      {
        field: 'open_actions',
        headerName: t('meetings.open_actions_short'),
        width: 120,
        type: 'rightAligned',
      },
    ],
    [t]
  )
  return (
    <div className='h-[560px]'>
      <DataGrid<Meeting>
        rowData={meetings}
        columnDefs={columns}
        getRowId={(p) => String(p.data.id)}
        onRowClicked={(e) => e.data && onOpen(e.data)}
        rowClass='cursor-pointer'
      />
    </div>
  )
}

function SeriesList({
  projectId,
  onEdit,
}: {
  projectId: number
  onEdit: (s: Series) => void
}) {
  const { t } = useTranslation()
  const { data: series = [] } = useSeries(projectId)
  if (!series.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('meetings.no_series')}</p>
    )
  return (
    <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-3'>
      {series.map((s) => (
        <button
          key={s.id}
          type='button'
          onClick={() => onEdit(s)}
          className='grid gap-1 rounded-lg border p-3 text-start text-sm hover:border-primary/50'
        >
          <span className='flex items-center gap-2 font-medium'>
            <Repeat className='size-4 text-muted-foreground' />
            {s.name}
            {!s.active ? (
              <Badge variant='outline'>{t('meetings.inactive')}</Badge>
            ) : null}
          </span>
          <span className='text-muted-foreground'>
            {statusLabel(s.cadence)} · {s.duration_minutes} min
            {s.location ? ` · ${s.location}` : ''}
          </span>
          <span className='text-xs text-muted-foreground'>
            {t('meetings.series_stats', {
              count: s.meeting_count,
              items: s.agenda_template.length,
            })}
            {s.next_date
              ? ` · ${t('meetings.next', { date: s.next_date })}`
              : ''}
          </span>
        </button>
      ))}
    </div>
  )
}

function Workspace({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [openId, setOpenId] = useRecordParam('meeting')
  const { data: open } = useMeeting(openId)
  const [creating, setCreating] = useState(false)
  const [series, setSeries] = useState<Series | null | 'new'>(null)
  const canCreate = can(session, 'meetings.create')

  return (
    <>
      <Tabs defaultValue='meetings'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <TabsList>
            <TabsTrigger value='meetings'>{t('meetings.meetings')}</TabsTrigger>
            <TabsTrigger value='series'>{t('meetings.series_tab')}</TabsTrigger>
          </TabsList>
          {canCreate ? (
            <div className='flex gap-2'>
              <Button
                size='sm'
                variant='outline'
                onClick={() => setSeries('new')}
              >
                <Repeat /> {t('meetings.new_series')}
              </Button>
              <Button size='sm' onClick={() => setCreating(true)}>
                <Plus /> {t('meetings.new')}
              </Button>
            </div>
          ) : null}
        </div>
        <TabsContent value='meetings'>
          <MeetingsGrid projectId={projectId} onOpen={(m) => setOpenId(m.id)} />
        </TabsContent>
        <TabsContent value='series'>
          <SeriesList projectId={projectId} onEdit={setSeries} />
        </TabsContent>
      </Tabs>
      {open && open.project_id === projectId ? (
        <MeetingEditor
          key={open.id}
          meeting={open}
          onClose={() => setOpenId(null)}
        />
      ) : null}
      {creating ? (
        <NewMeetingDialog
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={(m) => {
            setCreating(false)
            setOpenId(m.id)
          }}
        />
      ) : null}
      {series ? (
        <SeriesDialog
          projectId={projectId}
          series={series === 'new' ? null : series}
          onClose={() => setSeries(null)}
        />
      ) : null}
    </>
  )
}

export default function MeetingsPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('meetings.title')}
      description={t('meetings.description')}
      projectScoped
    >
      {project ? (
        <Workspace key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('meetings.no_project')}
        </p>
      )}
    </Page>
  )
}
