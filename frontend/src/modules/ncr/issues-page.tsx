import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Camera, Download, FileText, Plus, Settings2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { useSavedViews } from '@/hooks/use-saved-views'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { Kpi } from '@/components/records/fields'
import { StatusBadge } from '@/components/records/status-badge'
import { SavedViewsMenu } from '@/components/saved-views'
import {
  type Filters,
  type Issue,
  MDR_EFFECTS,
  NO_FILTERS,
  PUNCH_CATEGORIES,
  useCategories,
  useIssues,
  useSummary,
} from './api'
import { IssueSheet } from './issue-sheet'
import { QuickPunch, RaiseIssue } from './raise-dialogs'
import { type IssueType, LIFECYCLES } from './workflow'

function initial() {
  const params = new URLSearchParams(window.location.search)
  const id = Number(params.get('id'))
  return {
    id: Number.isFinite(id) && id > 0 ? id : null,
    type: (window.location.pathname.startsWith('/ncr') ||
    params.get('type') === 'ncr'
      ? 'ncr'
      : 'punch') as IssueType,
  }
}

function useLevels(projectId: number) {
  return useQuery({
    queryKey: ['asset-tree', projectId, 'levels'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/asset-tree/levels', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

function SummaryStrip({
  projectId,
  type,
}: {
  projectId: number
  type: IssueType
}) {
  const { t } = useTranslation()
  const { data: levels = [] } = useLevels(projectId)
  const [level, setLevel] = useState('')
  const { data } = useSummary(projectId, type, level)
  if (!data) return null
  const totals = data.totals
  return (
    <div className='grid gap-3'>
      <div className='grid grid-cols-2 gap-3 md:grid-cols-4'>
        <Kpi label={t('issues.kpi.open')} value={totals.open} />
        {type === 'punch' ? (
          <Kpi
            label={t('issues.kpi.cat_a')}
            value={totals.cat_a_open}
            tone={totals.cat_a_open ? 'bad' : 'good'}
          />
        ) : null}
        <Kpi
          label={t('issues.kpi.blocks_mdr')}
          value={totals.blocks_mdr}
          tone={totals.blocks_mdr ? 'warn' : 'good'}
        />
        <Kpi label={t('issues.kpi.closed')} value={totals.closed} />
      </div>
      {type === 'punch' && levels.length ? (
        <details className='rounded-md border p-3 text-sm'>
          <summary className='cursor-pointer font-medium'>
            {t('issues.by_area')}
          </summary>
          <div className='mt-2 flex items-center gap-2'>
            <NativeSelect
              className='h-8 w-48'
              aria-label={t('issues.group_by')}
              placeholder={t('issues.group_by')}
              options={levels.map((l) => ({ value: l.key, label: l.label }))}
              value={level}
              onChange={(e) => setLevel(e.target.value)}
            />
          </div>
          <table className='mt-2 w-full text-left'>
            <thead className='text-xs text-muted-foreground'>
              <tr>
                <th className='py-1'>{t('issues.area')}</th>
                <th>{t('issues.kpi.open')}</th>
                <th>Cat A</th>
                <th>Cat B</th>
                <th>Cat C</th>
              </tr>
            </thead>
            <tbody>
              {(level ? data.by_area : data.by_category).map((row) => {
                const name =
                  'label' in row
                    ? row.label
                    : (row as { category: string }).category
                return (
                  <tr key={name} className='border-t'>
                    <td className='py-1'>{name}</td>
                    <td>{row.open}</td>
                    <td
                      className={
                        row.cat_a_open ? 'font-semibold text-red-600' : ''
                      }
                    >
                      {row.cat_a_open}
                    </td>
                    <td>{row.cat_b_open}</td>
                    <td>{row.cat_c_open}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </details>
      ) : null}
    </div>
  )
}

function Register({
  projectId,
  type,
  onOpen,
}: {
  projectId: number
  type: IssueType
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const { data: rows = [] } = useIssues(projectId, type, filters)
  const { data: categories = [] } = useCategories(projectId)
  const [dialog, setDialog] = useState<'quick' | 'raise' | null>(null)
  const views = useSavedViews<Issue>(`issues.${type}`, projectId)
  const columns = useMemo<ColDef<Issue>[]>(
    () => [
      {
        field: 'code',
        headerName: t('issues.code'),
        width: 100,
        cellClass: 'font-mono',
      },
      {
        field: 'title',
        headerName: t('issues.title_field'),
        flex: 1,
        minWidth: 200,
      },
      type === 'punch'
        ? {
            field: 'punch_category',
            headerName: 'Cat',
            width: 70,
            cellClass: (p) =>
              p.value === 'A' ? 'font-semibold text-red-600' : undefined,
          }
        : {
            field: 'severity',
            headerName: t('issues.severity'),
            width: 100,
            cellRenderer: (p: ICellRendererParams<Issue>) => (
              <StatusBadge status={p.value} />
            ),
          },
      {
        field: 'status',
        headerName: t('issues.status_field'),
        width: 150,
        cellRenderer: (p: ICellRendererParams<Issue>) => (
          <StatusBadge status={p.value} />
        ),
      },
      { field: 'category', headerName: t('issues.category'), width: 120 },
      {
        headerName: t('issues.anchor'),
        width: 180,
        valueGetter: (p) =>
          p.data?.anchor_label ??
          p.data?.location_label ??
          t('issues.project_level'),
      },
      {
        headerName: t('issues.responsible'),
        width: 150,
        valueGetter: (p) =>
          p.data?.responsible_user_name ??
          p.data?.responsible_contact_name ??
          p.data?.responsible_company_name,
      },
      { field: 'due_date', headerName: t('issues.due'), width: 110 },
      {
        field: 'visibility',
        headerName: t('issues.flag.visibility'),
        width: 100,
      },
      {
        field: 'mdr_effect',
        headerName: t('issues.flag.mdr_effect'),
        width: 120,
      },
      ...(type === 'ncr'
        ? ([
            {
              field: 'disposition',
              headerName: t('issues.disposition'),
              width: 120,
            },
            {
              field: 'concession_reference',
              headerName: t('issues.concession'),
              width: 120,
            },
          ] as ColDef<Issue>[])
        : []),
    ],
    [t, type]
  )
  const exportUrl = (format: string) =>
    `/api/v1/issues/export?project_id=${projectId}&register=${type}&format=${format}`
  return (
    <div className='grid gap-3'>
      <SummaryStrip projectId={projectId} type={type} />
      <div className='flex flex-wrap items-center gap-2'>
        <SavedViewsMenu views={views} />
        <Input
          className='h-8 w-52'
          placeholder={t('issues.search')}
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-44'
          aria-label={t('issues.status_field')}
          placeholder={t('issues.all_statuses')}
          values={[...LIFECYCLES[type], 'void', 'upgraded', 'escalated']}
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        />
        <NativeSelect
          className='h-8 w-40'
          aria-label={t('issues.category')}
          placeholder={t('issues.all_categories')}
          options={categories.map((c) => ({ value: c.key, label: c.label }))}
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        />
        {type === 'punch' ? (
          <NativeSelect
            className='h-8 w-28'
            aria-label={t('issues.punch_category')}
            placeholder='Cat'
            options={PUNCH_CATEGORIES.map((c) => ({
              value: c,
              label: `Cat ${c}`,
            }))}
            value={filters.punch_category}
            onChange={(e) =>
              setFilters({ ...filters, punch_category: e.target.value })
            }
          />
        ) : (
          <NativeSelect
            className='h-8 w-36'
            aria-label={t('issues.flag.mdr_effect')}
            placeholder={t('issues.flag.mdr_effect')}
            values={MDR_EFFECTS}
            value={filters.mdr_effect}
            onChange={(e) =>
              setFilters({ ...filters, mdr_effect: e.target.value })
            }
          />
        )}
        <label className='flex items-center gap-1.5 text-sm'>
          <Checkbox
            checked={filters.open_only}
            onCheckedChange={(v) =>
              setFilters({ ...filters, open_only: v === true })
            }
          />
          {t('issues.open_only')}
        </label>
        <div className='ms-auto flex flex-wrap gap-2'>
          {can(session, 'ncr.export') ? (
            <>
              <Button size='sm' variant='outline' asChild>
                <a href={exportUrl('xlsx')}>
                  <Download /> Excel
                </a>
              </Button>
              <Button size='sm' variant='outline' asChild>
                <a href={exportUrl('pdf')}>
                  <FileText /> PDF
                </a>
              </Button>
            </>
          ) : null}
          {can(session, 'ncr.create') ? (
            <>
              {type === 'punch' ? (
                <Button size='sm' onClick={() => setDialog('quick')}>
                  <Camera /> {t('issues.quick_punch')}
                </Button>
              ) : null}
              <Button
                size='sm'
                variant={type === 'punch' ? 'outline' : 'default'}
                onClick={() => setDialog('raise')}
              >
                <Plus />{' '}
                {t(type === 'ncr' ? 'issues.raise_ncr' : 'issues.raise_punch')}
              </Button>
            </>
          ) : null}
        </div>
      </div>
      <div className='h-[520px]'>
        <DataGrid<Issue>
          key={type}
          onGridReady={views.onGridReady}
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && onOpen(e.data.id)}
        />
      </div>
      {dialog === 'quick' ? (
        <QuickPunch
          projectId={projectId}
          onClose={() => setDialog(null)}
          onCreated={onOpen}
        />
      ) : null}
      {dialog === 'raise' ? (
        <RaiseIssue
          projectId={projectId}
          type={type}
          onClose={() => setDialog(null)}
          onCreated={onOpen}
        />
      ) : null}
    </div>
  )
}

export default function IssuesPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const [start] = useState(initial)
  const [type, setType] = useState<IssueType>(start.type)
  const [openId, setOpenId] = useState<number | null>(start.id)
  return (
    <Page
      title={t('issues.page_title')}
      description={t('issues.description_page')}
      projectScoped
      actions={
        can(session, 'ncr.read') && session.account_type === 'staff' ? (
          <Button size='sm' variant='outline' asChild>
            <a href='/issues/templates'>
              <Settings2 /> {t('issues.templates')}
            </a>
          </Button>
        ) : null
      }
    >
      {project ? (
        <>
          <Tabs value={type} onValueChange={(v) => setType(v as IssueType)}>
            <TabsList>
              <TabsTrigger value='punch'>{t('issues.tab.punch')}</TabsTrigger>
              <TabsTrigger value='ncr'>{t('issues.tab.ncr')}</TabsTrigger>
            </TabsList>
          </Tabs>
          <Register
            key={`${project.id}-${type}`}
            projectId={project.id}
            type={type}
            onOpen={setOpenId}
          />
          <IssueSheet
            id={openId}
            onClose={() => setOpenId(null)}
            onOpen={setOpenId}
          />
        </>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('issues.no_project')}
        </p>
      )}
    </Page>
  )
}
