import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Download, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import {
  type DatasetInfo,
  exportUrl,
  saveExport,
  useExportDatasets,
  useImporters,
} from './api'
import { ImportWizard } from './import-wizard'

type Filter = { field: string; op: string; value: string }
const OPS = ['eq', 'ne', 'contains', 'gt', 'gte', 'lt', 'lte', 'in']

function filterObject(rows: Filter[]) {
  const out: Record<string, Record<string, unknown>> = {}
  for (const f of rows) {
    if (!f.field || f.value === '') continue
    const value =
      f.op === 'in'
        ? f.value.split(',').map((v) => v.trim())
        : f.value === 'true' || f.value === 'false'
          ? f.value === 'true'
          : f.value
    out[f.field] = { ...(out[f.field] ?? {}), [f.op]: value }
  }
  return out
}

function Exporter({
  datasets,
  projectId,
}: {
  datasets: DatasetInfo[]
  projectId?: number
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(datasets[0]?.name ?? '')
  const dataset = datasets.find((d) => d.name === name)
  const [columns, setColumns] = useState<string[]>([])
  const [filters, setFilters] = useState<Filter[]>([])
  const [format, setFormat] = useState<'xlsx' | 'csv' | 'pdf'>('xlsx')
  const run = useMutation({
    mutationFn: () =>
      saveExport(
        exportUrl(name, {
          projectId,
          format,
          columns: (dataset?.columns ?? [])
            .map((c) => c.key)
            .filter((k) => columns.includes(k)),
          filters: filterObject(filters),
        })
      ),
    onError: handleServerError,
  })
  if (!datasets.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('data.no_datasets')}</p>
    )
  const needsProject = dataset?.project_scoped && !projectId

  return (
    <div className='grid gap-4 lg:grid-cols-[16rem_1fr]'>
      <Card className='self-start py-2'>
        <CardContent className='flex flex-col gap-0.5 px-2'>
          {datasets.map((d) => (
            <button
              key={d.name}
              type='button'
              onClick={() => {
                setName(d.name)
                setColumns([])
                setFilters([])
              }}
              className={cn(
                'rounded-md px-2 py-1.5 text-start text-sm hover:bg-muted',
                d.name === name && 'bg-muted font-medium'
              )}
            >
              {d.title}
              {!d.project_scoped ? (
                <span className='ms-1 text-xs text-muted-foreground'>
                  · {t('data.all_projects')}
                </span>
              ) : null}
            </button>
          ))}
        </CardContent>
      </Card>
      {dataset ? (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{dataset.title}</CardTitle>
            <p className='text-sm text-muted-foreground'>
              {dataset.description}
            </p>
          </CardHeader>
          <CardContent className='flex flex-col gap-4'>
            <div className='grid gap-1'>
              <Label className='text-xs'>{t('data.columns')}</Label>
              <div className='flex flex-wrap gap-x-4 gap-y-1'>
                {dataset.columns.map((c) => (
                  <label
                    key={c.key}
                    className='flex items-center gap-1 text-sm'
                  >
                    <Checkbox
                      checked={columns.includes(c.key)}
                      onCheckedChange={(on) =>
                        setColumns(
                          on
                            ? [...columns, c.key]
                            : columns.filter((k) => k !== c.key)
                        )
                      }
                    />
                    {c.label}
                  </label>
                ))}
              </div>
            </div>
            <div className='grid gap-2'>
              <Label className='text-xs'>{t('data.filters')}</Label>
              {filters.map((f, i) => {
                const patch = (p: Partial<Filter>) =>
                  setFilters(
                    filters.map((x, j) => (j === i ? { ...x, ...p } : x))
                  )
                return (
                  <div key={i} className='flex flex-wrap items-center gap-2'>
                    <Select
                      value={f.field}
                      onValueChange={(field) => patch({ field })}
                    >
                      <SelectTrigger size='sm' className='h-8 w-44'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {dataset.columns.map((c) => (
                          <SelectItem key={c.key} value={c.key}>
                            {c.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={f.op} onValueChange={(op) => patch({ op })}>
                      <SelectTrigger size='sm' className='h-8 w-24'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {OPS.map((op) => (
                          <SelectItem key={op} value={op}>
                            {t(`data.op.${op}`)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      className='h-8 w-48'
                      value={f.value}
                      onChange={(e) => patch({ value: e.target.value })}
                    />
                    <Button
                      size='icon'
                      variant='ghost'
                      className='size-8'
                      aria-label={t('data.remove_filter')}
                      onClick={() =>
                        setFilters(filters.filter((_, j) => j !== i))
                      }
                    >
                      <X />
                    </Button>
                  </div>
                )
              })}
              <Button
                size='sm'
                variant='ghost'
                className='self-start'
                onClick={() =>
                  setFilters([
                    ...filters,
                    {
                      field: dataset.columns[0]?.key ?? '',
                      op: 'eq',
                      value: '',
                    },
                  ])
                }
              >
                <Plus /> {t('data.add_filter')}
              </Button>
            </div>
            <div className='flex flex-wrap items-center gap-2'>
              <Select
                value={format}
                onValueChange={(v) => setFormat(v as 'xlsx')}
              >
                <SelectTrigger
                  size='sm'
                  className='h-8 w-28'
                  aria-label='Format'
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='xlsx'>Excel</SelectItem>
                  <SelectItem value='csv'>CSV</SelectItem>
                  <SelectItem value='pdf'>PDF</SelectItem>
                </SelectContent>
              </Select>
              <Button
                size='sm'
                disabled={needsProject || run.isPending}
                onClick={() => run.mutate()}
              >
                <Download /> {t('data.export')}
              </Button>
              {needsProject ? (
                <span className='text-sm text-amber-600'>
                  {t('data.needs_project')}
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

export default function DataPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const mayExport = can(session, 'data_exchange.export')
  const mayImport = can(session, 'data_exchange.import')
  const { data: datasets } = useExportDatasets(project?.id)
  const { data: importers } = useImporters(project?.id, mayImport)
  return (
    <Page
      title={t('data.title')}
      description={t('data.description')}
      projectScoped
    >
      <Tabs defaultValue={mayExport ? 'export' : 'import'}>
        <TabsList>
          {mayExport ? (
            <TabsTrigger value='export'>{t('data.export')}</TabsTrigger>
          ) : null}
          {mayImport ? (
            <TabsTrigger value='import'>{t('data.import')}</TabsTrigger>
          ) : null}
        </TabsList>
        {mayExport ? (
          <TabsContent value='export' className='mt-3'>
            {datasets ? (
              <Exporter
                key={project?.id ?? 0}
                datasets={datasets}
                projectId={project?.id}
              />
            ) : null}
          </TabsContent>
        ) : null}
        {mayImport ? (
          <TabsContent value='import' className='mt-3'>
            {importers ? (
              <ImportWizard importers={importers} projectId={project?.id} />
            ) : null}
          </TabsContent>
        ) : null}
      </Tabs>
    </Page>
  )
}
