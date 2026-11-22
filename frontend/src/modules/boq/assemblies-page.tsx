import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
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
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { type Assembly, useAssemblies, useAssemblyActions } from './api'
import { fmt } from './format'
import { ResourcePicker } from './resource-lines'
import { compositeRate, parseNumber } from './tree'

type DraftLine = {
  resource_id: number
  code: string
  name: string
  unit: string
  rate: string
  factor: string
  waste_pct: string
}

type Draft = {
  id?: number
  code: string
  name: string
  unit: string
  classification: string
  description: string
  lines: DraftLine[]
}

const EMPTY: Draft = {
  code: '',
  name: '',
  unit: '',
  classification: '',
  description: '',
  lines: [],
}

function AssemblyDialog({
  draft,
  setDraft,
  onClose,
}: {
  draft: Draft
  setDraft: (d: Draft) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { save } = useAssemblyActions()
  const setLine = (i: number, change: Partial<DraftLine>) =>
    setDraft({
      ...draft,
      lines: draft.lines.map((l, j) => (j === i ? { ...l, ...change } : l)),
    })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {draft.id ? t('boq.asm.edit') : t('boq.asm.add')}
          </DialogTitle>
        </DialogHeader>
        <form
          id='assembly-form'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(
              {
                id: draft.id,
                code: draft.code,
                name: draft.name,
                unit: draft.unit,
                classification: draft.classification || null,
                description: draft.description || null,
                project_id: null,
                lines: draft.lines.map((l) => ({
                  resource_id: l.resource_id,
                  factor: parseNumber(l.factor) ?? '0',
                  waste_pct: parseNumber(l.waste_pct) ?? '0',
                })),
              },
              { onSuccess: onClose }
            )
          }}
        >
          <div className='grid grid-cols-[8rem_1fr_6rem_8rem] gap-2'>
            <div className='grid gap-1'>
              <Label>{t('boq.col.code')}</Label>
              <Input
                required
                maxLength={40}
                value={draft.code}
                onChange={(e) => setDraft({ ...draft, code: e.target.value })}
              />
            </div>
            <div className='grid gap-1'>
              <Label>{t('boq.field.name')}</Label>
              <Input
                required
                maxLength={300}
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className='grid gap-1'>
              <Label>{t('boq.col.unit')}</Label>
              <Input
                maxLength={20}
                value={draft.unit}
                onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
              />
            </div>
            <div className='grid gap-1'>
              <Label>{t('boq.col.classification')}</Label>
              <Input
                maxLength={30}
                value={draft.classification}
                onChange={(e) =>
                  setDraft({ ...draft, classification: e.target.value })
                }
              />
            </div>
          </div>
          <div className='grid gap-1'>
            <Label>{t('boq.asm.description_field')}</Label>
            <Textarea
              rows={2}
              value={draft.description}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value })
              }
            />
          </div>
          <div className='flex items-center justify-between'>
            <Label>{t('boq.asm.lines')}</Label>
            <ResourcePicker
              projectId={null}
              placeholder={t('boq.add_resource')}
              icon={<Plus />}
              onPick={(r) =>
                setDraft({
                  ...draft,
                  lines: [
                    ...draft.lines,
                    {
                      resource_id: r.id,
                      code: r.code,
                      name: r.name,
                      unit: r.unit,
                      rate: r.rate,
                      factor: '1',
                      waste_pct: '0',
                    },
                  ],
                })
              }
            />
          </div>
          <table className='w-full text-sm'>
            <thead className='text-xs text-muted-foreground'>
              <tr>
                <th className='text-start font-medium'>{t('boq.col.code')}</th>
                <th className='text-start font-medium'>
                  {t('boq.field.name')}
                </th>
                <th className='text-end font-medium'>{t('boq.field.rate')}</th>
                <th className='w-28 text-end font-medium'>{t('boq.factor')}</th>
                <th className='w-24 text-end font-medium'>{t('boq.waste')}</th>
                <th className='w-8' />
              </tr>
            </thead>
            <tbody>
              {draft.lines.map((l, i) => (
                <tr key={`${l.resource_id}-${i}`}>
                  <td className='font-mono'>{l.code}</td>
                  <td>
                    {l.name}{' '}
                    <span className='text-muted-foreground'>/{l.unit}</span>
                  </td>
                  <td className='text-end tabular-nums'>{fmt(l.rate)}</td>
                  <td>
                    <Input
                      className='h-7 text-end'
                      value={l.factor}
                      onChange={(e) => setLine(i, { factor: e.target.value })}
                    />
                  </td>
                  <td>
                    <Input
                      className='h-7 text-end'
                      value={l.waste_pct}
                      onChange={(e) =>
                        setLine(i, { waste_pct: e.target.value })
                      }
                    />
                  </td>
                  <td className='text-end'>
                    <button
                      type='button'
                      aria-label={t('boq.delete')}
                      className='text-muted-foreground hover:text-red-600'
                      onClick={() =>
                        setDraft({
                          ...draft,
                          lines: draft.lines.filter((_, j) => j !== i),
                        })
                      }
                    >
                      <Trash2 className='size-4' />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className='text-end text-sm font-semibold tabular-nums'>
            {t('boq.asm.unit_rate')}: {fmt(compositeRate(draft.lines))} /{' '}
            {draft.unit || '—'}
          </p>
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type='submit' form='assembly-form' disabled={save.isPending}>
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function AssembliesPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const editable = can(session, 'boq.update')
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [deleting, setDeleting] = useState<Assembly | null>(null)
  const { data } = useAssemblies({ search, projectId: project?.id ?? null })
  const { remove } = useAssemblyActions()

  const columns = useMemo<ColDef<Assembly>[]>(
    () => [
      {
        field: 'code',
        headerName: t('boq.col.code'),
        width: 120,
        cellClass: 'font-mono',
      },
      {
        field: 'name',
        headerName: t('boq.field.name'),
        flex: 1,
        minWidth: 260,
      },
      { field: 'unit', headerName: t('boq.col.unit'), width: 80 },
      {
        field: 'classification',
        headerName: t('boq.col.classification'),
        width: 140,
      },
      {
        headerName: t('boq.asm.lines'),
        width: 120,
        valueGetter: (p) => p.data?.lines.length ?? 0,
        type: 'rightAligned',
      },
      {
        field: 'unit_rate',
        headerName: t('boq.asm.unit_rate'),
        width: 130,
        type: 'rightAligned',
        cellClass: 'tabular-nums',
        valueFormatter: (p) => fmt(p.value as string),
      },
      ...(editable
        ? [
            {
              headerName: '',
              width: 80,
              sortable: false,
              filter: false,
              cellRenderer: (p: ICellRendererParams<Assembly>) =>
                p.data ? (
                  <div className='flex h-full items-center gap-2'>
                    <button
                      type='button'
                      aria-label={t('boq.asm.edit')}
                      className='text-muted-foreground hover:text-foreground'
                      onClick={() => {
                        const a = p.data!
                        setDraft({
                          id: a.id,
                          code: a.code,
                          name: a.name,
                          unit: a.unit,
                          classification: a.classification ?? '',
                          description: a.description ?? '',
                          lines: a.lines.map((l) => ({
                            resource_id: l.resource_id,
                            code: l.code,
                            name: l.name,
                            unit: l.unit,
                            rate: l.rate,
                            factor: l.factor,
                            waste_pct: l.waste_pct,
                          })),
                        })
                      }}
                    >
                      <Pencil className='size-4' />
                    </button>
                    {can(session, 'boq.delete') ? (
                      <button
                        type='button'
                        aria-label={t('boq.delete')}
                        className='text-muted-foreground hover:text-red-600'
                        onClick={() => setDeleting(p.data!)}
                      >
                        <Trash2 className='size-4' />
                      </button>
                    ) : null}
                  </div>
                ) : null,
            } satisfies ColDef<Assembly>,
          ]
        : []),
    ],
    [editable, session, t]
  )

  return (
    <Page
      title={t('boq.asm.title')}
      description={t('boq.asm.description')}
      actions={
        editable ? (
          <Button size='sm' onClick={() => setDraft(EMPTY)}>
            <Plus /> {t('boq.asm.add')}
          </Button>
        ) : null
      }
    >
      <Input
        className='h-8 w-60'
        placeholder={t('boq.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className='min-h-[420px] flex-1'>
        <DataGrid<Assembly>
          rowData={data?.data ?? []}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
        />
      </div>
      {draft ? (
        <AssemblyDialog
          draft={draft}
          setDraft={setDraft}
          onClose={() => setDraft(null)}
        />
      ) : null}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('boq.asm.delete')}
        desc={t('boq.asm.delete_desc')}
        destructive
        confirmText={t('boq.delete')}
        handleConfirm={() => {
          if (deleting) remove.mutate(deleting.id)
          setDeleting(null)
        }}
      />
    </Page>
  )
}
