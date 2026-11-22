import { useMemo, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { type BoqSummary, useBoqs, useCreateBoq, useDeleteBoq } from './api'

function Bills({
  projectId,
  currency,
}: {
  projectId: number
  currency: string
}) {
  const { t } = useTranslation()
  const session = useSession()
  const navigate = useNavigate()
  const { data } = useBoqs(projectId)
  const create = useCreateBoq(projectId)
  const remove = useDeleteBoq(projectId)
  const [name, setName] = useState('')
  const [deleting, setDeleting] = useState<BoqSummary | null>(null)
  const open = (id: number) => void navigate({ to: `/boq/${id}` as never })

  const columns = useMemo<ColDef<BoqSummary>[]>(() => {
    const money = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    })
    return [
      {
        field: 'name',
        headerName: t('boq.name'),
        flex: 1,
        minWidth: 220,
        cellRenderer: (p: ICellRendererParams<BoqSummary>) =>
          p.data ? (
            <Link
              to='/$'
              params={{ _splat: `boq/${p.data.id}` }}
              className='font-medium hover:underline'
            >
              {p.data.name}
            </Link>
          ) : null,
      },
      {
        field: 'status',
        headerName: t('boq.status'),
        width: 120,
        cellRenderer: (p: ICellRendererParams<BoqSummary>) => (
          <StatusBadge status={p.value as string} />
        ),
      },
      {
        field: 'net_total',
        headerName: t('boq.net_total'),
        width: 160,
        type: 'rightAligned',
        valueFormatter: (p) => money.format(Number(p.value)),
      },
      {
        field: 'grand_total',
        headerName: t('boq.grand_total'),
        width: 160,
        type: 'rightAligned',
        valueFormatter: (p) => money.format(Number(p.value)),
      },
      {
        field: 'updated_at',
        headerName: t('boq.updated'),
        width: 170,
        valueFormatter: (p) =>
          p.value ? new Date(p.value as string).toLocaleString() : '',
      },
      ...(can(session, 'boq.delete')
        ? [
            {
              headerName: '',
              width: 48,
              sortable: false,
              filter: false,
              cellRenderer: (p: ICellRendererParams<BoqSummary>) =>
                p.data && p.data.status !== 'locked' ? (
                  <button
                    type='button'
                    aria-label={t('boq.delete')}
                    className='text-muted-foreground hover:text-red-600'
                    onClick={() => setDeleting(p.data!)}
                  >
                    <Trash2 className='size-4' />
                  </button>
                ) : null,
            } satisfies ColDef<BoqSummary>,
          ]
        : []),
    ]
  }, [currency, session, t])

  return (
    <>
      {can(session, 'boq.create') ? (
        <form
          className='flex flex-wrap items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { name },
              {
                onSuccess: (bill) => {
                  setName('')
                  open(bill.id)
                },
              }
            )
          }}
        >
          <Input
            className='h-8 w-72'
            placeholder={t('boq.name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
          />
          <Button size='sm' type='submit' disabled={create.isPending}>
            <Plus /> {t('boq.new')}
          </Button>
        </form>
      ) : null}
      {data && data.data.length === 0 ? (
        <p className='text-sm text-muted-foreground'>{t('boq.none')}</p>
      ) : (
        <div className='h-[480px]'>
          <DataGrid<BoqSummary>
            rowData={data?.data ?? []}
            columnDefs={columns}
            getRowId={(p) => String(p.data.id)}
            onRowDoubleClicked={(e) => e.data && open(e.data.id)}
          />
        </div>
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('boq.delete_bill')}
        desc={t('boq.delete_bill_desc')}
        destructive
        confirmText={t('boq.delete')}
        handleConfirm={() => {
          if (deleting) remove.mutate(deleting.id)
          setDeleting(null)
        }}
      />
    </>
  )
}

export default function BoqListPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('boq.title')}
      description={t('boq.description')}
      projectScoped
    >
      {project ? (
        <Bills
          key={project.id}
          projectId={project.id}
          currency={project.currency}
        />
      ) : (
        <p className='text-sm text-muted-foreground'>{t('boq.no_project')}</p>
      )}
    </Page>
  )
}
