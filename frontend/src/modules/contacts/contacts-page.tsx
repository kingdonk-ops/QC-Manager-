import { useMemo, useState } from 'react'
import { useProjects } from '@/modules/projects/api'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Plus,
  Search,
  Upload,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { statusLabel } from '@/components/records/status'
import {
  CONTACT_TYPES,
  type Company,
  type Contact,
  type ContactFilters,
  PAGE_SIZE,
  exportUrl,
  useCompanies,
  useContacts,
} from './api'
import { CompanyDialog } from './company-dialog'
import { ContactSheet } from './contact-sheet'
import { ImportWizard } from './import-wizard'

const ALL = 'all'

const NO_FILTERS: ContactFilters = {
  search: '',
  type: ALL,
  company_id: null,
  project_id: null,
  tag: '',
}

function Directory({
  filters,
  setFilters,
}: {
  filters: ContactFilters
  setFilters: (f: ContactFilters) => void
}) {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<number | null>(null)
  const { data } = useContacts(filters, page)
  const { data: companies = [] } = useCompanies()
  const { data: projects = [] } = useProjects()
  const rows = useMemo(() => data?.data ?? [], [data])
  const total = data?.total_count ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const open = rows.find((c) => c.id === openId) ?? null
  const set = (patch: Partial<ContactFilters>) => {
    setPage(1)
    setFilters({ ...filters, ...patch })
  }

  const columns = useMemo<ColDef<Contact>[]>(
    () => [
      {
        field: 'full_name',
        headerName: t('contacts.name'),
        pinned: 'left',
        width: 200,
        cellClass: 'font-medium',
      },
      { field: 'company_name', headerName: t('contacts.company'), width: 200 },
      {
        field: 'type',
        headerName: t('contacts.type'),
        width: 140,
        valueFormatter: (p) => (p.value ? statusLabel(p.value) : ''),
      },
      { field: 'job_title', headerName: t('contacts.job_title'), width: 170 },
      { field: 'email', headerName: t('contacts.email'), width: 220 },
      { field: 'phone', headerName: t('contacts.phone'), width: 140 },
      { field: 'mobile', headerName: t('contacts.mobile'), width: 140 },
      {
        field: 'tags',
        headerName: t('contacts.tags'),
        width: 180,
        sortable: false,
        cellRenderer: (p: ICellRendererParams<Contact>) => (
          <span className='flex gap-1'>
            {(p.value as string[] | undefined)?.map((tag) => (
              <Badge key={tag} variant='outline'>
                {tag}
              </Badge>
            ))}
          </span>
        ),
      },
      {
        headerName: t('contacts.projects'),
        flex: 1,
        minWidth: 160,
        valueGetter: (p) =>
          p.data?.projects
            ?.map((r) => r.project_code + (r.role ? ` (${r.role})` : ''))
            .join(', '),
      },
    ],
    [t]
  )

  return (
    <div className='grid gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='relative'>
          <Search className='absolute start-2 top-2 size-4 text-muted-foreground' />
          <Input
            className='h-8 w-56 ps-8'
            placeholder={t('contacts.search')}
            value={filters.search}
            onChange={(e) => set({ search: e.target.value })}
          />
        </div>
        <Select value={filters.type} onValueChange={(type) => set({ type })}>
          <SelectTrigger size='sm' aria-label={t('contacts.type')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('contacts.all_types')}</SelectItem>
            {CONTACT_TYPES.map((v) => (
              <SelectItem key={v} value={v}>
                {statusLabel(v)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.company_id ? String(filters.company_id) : ALL}
          onValueChange={(v) =>
            set({ company_id: v === ALL ? null : Number(v) })
          }
        >
          <SelectTrigger size='sm' aria-label={t('contacts.company')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('contacts.all_companies')}</SelectItem>
            {companies.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.project_id ? String(filters.project_id) : ALL}
          onValueChange={(v) =>
            set({ project_id: v === ALL ? null : Number(v) })
          }
        >
          <SelectTrigger size='sm' aria-label={t('contacts.project')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('contacts.all_projects')}</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>
                {p.code} {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className='h-8 w-32'
          placeholder={t('contacts.tag')}
          value={filters.tag}
          onChange={(e) => set({ tag: e.target.value })}
        />
        <div className='ms-auto flex items-center gap-1 text-sm text-muted-foreground'>
          <span className='tabular-nums'>
            {t('contacts.count', { count: total })}
          </span>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label={t('contacts.previous_page')}
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft />
          </Button>
          <span className='tabular-nums'>
            {page} / {pages}
          </span>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label={t('contacts.next_page')}
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
      <div className='h-[560px]'>
        <DataGrid<Contact>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
          rowClass='cursor-pointer'
        />
      </div>
      {open ? (
        <ContactSheet
          key={open.id}
          open
          contact={open}
          onClose={() => setOpenId(null)}
        />
      ) : null}
    </div>
  )
}

function Companies() {
  const { t } = useTranslation()
  const session = useSession()
  const [search, setSearch] = useState('')
  const { data: companies = [] } = useCompanies(search)
  const [editing, setEditing] = useState<Company | null | 'new'>(null)
  const columns = useMemo<ColDef<Company>[]>(
    () => [
      {
        field: 'name',
        headerName: t('contacts.company_name'),
        flex: 1,
        minWidth: 200,
        cellClass: 'font-medium',
      },
      {
        field: 'type',
        headerName: t('contacts.type'),
        width: 140,
        valueFormatter: (p) => (p.value ? statusLabel(p.value) : ''),
      },
      { field: 'phone', headerName: t('contacts.phone'), width: 150 },
      { field: 'email', headerName: t('contacts.email'), width: 220 },
      { field: 'tax_id', headerName: t('contacts.tax_id'), width: 140 },
      {
        field: 'contact_count',
        headerName: t('contacts.contacts'),
        width: 110,
        type: 'rightAligned',
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-3'>
      <div className='flex items-center gap-2'>
        <div className='relative'>
          <Search className='absolute start-2 top-2 size-4 text-muted-foreground' />
          <Input
            className='h-8 w-56 ps-8'
            placeholder={t('contacts.search_companies')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {can(session, 'contacts.create') ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setEditing('new')}
          >
            <Plus /> {t('contacts.new_company')}
          </Button>
        ) : null}
      </div>
      <div className='h-[520px]'>
        <DataGrid<Company>
          rowData={companies}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          onRowClicked={(e) => e.data && setEditing(e.data)}
          rowClass='cursor-pointer'
        />
      </div>
      {editing ? (
        <CompanyDialog
          company={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  )
}

export default function ContactsPage() {
  const { t } = useTranslation()
  const session = useSession()
  const [filters, setFilters] = useState<ContactFilters>(NO_FILTERS)
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)

  return (
    <Page
      title={t('contacts.title')}
      description={t('contacts.description')}
      actions={
        <>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size='sm' variant='outline'>
                <Download /> {t('contacts.export')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end'>
              <DropdownMenuItem asChild>
                <a href={exportUrl(filters, 'xlsx')} download>
                  {t('contacts.export_xlsx')}
                </a>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a href={exportUrl(filters, 'csv')} download>
                  {t('contacts.export_csv')}
                </a>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {can(session, 'contacts.import') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setImporting(true)}
            >
              <Upload /> {t('contacts.import.button')}
            </Button>
          ) : null}
          {can(session, 'contacts.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> {t('contacts.new')}
            </Button>
          ) : null}
        </>
      }
    >
      <Tabs defaultValue='directory'>
        <TabsList>
          <TabsTrigger value='directory'>{t('contacts.directory')}</TabsTrigger>
          <TabsTrigger value='companies'>{t('contacts.companies')}</TabsTrigger>
        </TabsList>
        <TabsContent value='directory'>
          <Directory filters={filters} setFilters={setFilters} />
        </TabsContent>
        <TabsContent value='companies'>
          <Companies />
        </TabsContent>
      </Tabs>
      {creating ? (
        <ContactSheet open contact={null} onClose={() => setCreating(false)} />
      ) : null}
      {importing ? <ImportWizard onClose={() => setImporting(false)} /> : null}
    </Page>
  )
}
