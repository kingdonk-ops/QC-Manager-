import { useMemo, useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { ColDef } from 'ag-grid-community'
import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import {
  type Criterion,
  errorText,
  useCriteria,
  useDeleteCriterion,
  useInspectionSettings,
  useSaveCriterion,
  useUpdateInspectionSettings,
} from './criteria-api'
import { CriterionForm } from './criterion-form'
import { toleranceDisplay } from './tolerance'

function CriterionDialog({
  projectId,
  criterion,
  onClose,
}: {
  projectId: number
  criterion: Criterion | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const save = useSaveCriterion(projectId)
  const remove = useDeleteCriterion(projectId)
  const [error, setError] = useState<string | null>(null)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {criterion
              ? `${t('inspections.criteria.edit')}: ${criterion.code}`
              : t('inspections.criteria.new')}
          </DialogTitle>
        </DialogHeader>
        <CriterionForm
          initial={criterion}
          pending={save.isPending}
          serverError={error}
          onSubmit={(body) => {
            setError(null)
            save.mutate(
              { id: criterion?.id, body },
              {
                onSuccess: () => {
                  toast.success(t('inspections.criteria.saved'))
                  onClose()
                },
                onError: (e) => setError(errorText(e)),
              }
            )
          }}
        />
        {criterion && can(session, 'inspections.delete') ? (
          <Button
            type='button'
            variant='outline'
            className='w-fit text-red-600'
            disabled={remove.isPending}
            onClick={() => {
              setError(null)
              remove.mutate(criterion.id, {
                onSuccess: () => {
                  toast.success(t('inspections.criteria.deleted'))
                  onClose()
                },
                onError: (e) => setError(errorText(e)),
              })
            }}
          >
            <Trash2 /> {t('inspections.criteria.delete')}
          </Button>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

function AutoReportSetting({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data } = useInspectionSettings(projectId)
  const update = useUpdateInspectionSettings(projectId)
  if (!data) return null
  return (
    <Card className='gap-2 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm'>
          {t('inspections.criteria.auto_report')}
        </CardTitle>
      </CardHeader>
      <CardContent className='grid gap-1 px-4'>
        <label className='flex items-center gap-2 text-sm'>
          <Checkbox
            checked={data.auto_report_on_failure}
            disabled={!can(session, 'inspections.manage') || update.isPending}
            onCheckedChange={(v) =>
              update.mutate({ auto_report_on_failure: v === true })
            }
          />
          {t('inspections.criteria.auto_report_label')}
        </label>
        <p className='text-xs text-muted-foreground'>
          {t('inspections.criteria.auto_report_help')}
        </p>
      </CardContent>
    </Card>
  )
}

function Library({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [category, setCategory] = useState('')
  const [active, setActive] = useState('')
  const [open, setOpen] = useState<Criterion | 'new' | null>(null)
  const { data: rows = [] } = useCriteria(projectId, { category, active })
  // The category list comes from the unfiltered library so a chosen filter never empties its own menu.
  const { data: all = [] } = useCriteria(projectId)
  const categories = useMemo(
    () =>
      [...new Set(all.map((c) => c.category).filter((c): c is string => !!c))].sort(),
    [all]
  )
  const editable = can(session, 'inspections.update')

  const columns = useMemo<ColDef<Criterion>[]>(
    () => [
      {
        field: 'code',
        headerName: t('inspections.criteria.code'),
        width: 120,
        cellClass: 'font-mono',
        sort: 'asc',
      },
      {
        field: 'title',
        headerName: t('inspections.criteria.title'),
        flex: 1,
        minWidth: 220,
      },
      {
        field: 'category',
        headerName: t('inspections.criteria.category'),
        width: 140,
      },
      {
        field: 'rule_type',
        headerName: t('inspections.criteria.rule_type'),
        width: 120,
        valueFormatter: (p) => t(`inspections.criteria.rule.${p.value}`),
      },
      {
        headerName: t('inspections.criteria.tolerance'),
        width: 260,
        valueGetter: (p) =>
          p.data
            ? toleranceDisplay(p.data, {
                nominal: t('inspections.criteria.nominal_short'),
                lower: '≥',
                upper: '≤',
              })
            : '',
      },
      {
        field: 'standards_ref',
        headerName: t('inspections.criteria.standards_ref'),
        width: 170,
      },
      {
        field: 'active',
        headerName: t('inspections.criteria.active'),
        width: 110,
        cellRenderer: (p: { value?: boolean }) => (
          <Badge variant={p.value ? 'secondary' : 'outline'}>
            {p.value
              ? t('inspections.criteria.active')
              : t('inspections.criteria.inactive')}
          </Badge>
        ),
      },
    ],
    [t]
  )

  return (
    <>
      <AutoReportSetting projectId={projectId} />
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-48'
          aria-label={t('inspections.criteria.category')}
          placeholder={t('inspections.criteria.all_categories')}
          options={categories.map((c) => ({ value: c, label: c }))}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <NativeSelect
          className='h-8 w-48'
          aria-label={t('inspections.criteria.active')}
          options={[
            { value: '', label: t('inspections.criteria.any_status') },
            { value: 'true', label: t('inspections.criteria.active_only') },
            { value: 'false', label: t('inspections.criteria.inactive_only') },
          ]}
          value={active}
          onChange={(e) => setActive(e.target.value)}
        />
        {editable ? (
          <Button size='sm' className='ms-auto' onClick={() => setOpen('new')}>
            <Plus /> {t('inspections.criteria.new')}
          </Button>
        ) : null}
      </div>
      <div className='h-[480px]'>
        <DataGrid<Criterion>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && editable && setOpen(e.data)}
        />
      </div>
      {open ? (
        <CriterionDialog
          key={open === 'new' ? 'new' : open.id}
          projectId={projectId}
          criterion={open === 'new' ? null : open}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </>
  )
}

export default function CriteriaPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.criteria.page_title')}
      description={t('inspections.criteria.description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      {project ? (
        <Library key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.criteria.no_project')}
        </p>
      )}
    </Page>
  )
}
