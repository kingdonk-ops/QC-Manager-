import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Ban, Hash, Pencil, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import {
  type Allocation,
  type Scheme,
  useAllocate,
  useAllocations,
  usePreview,
  useSaveScheme,
  useSchemes,
  useVoid,
} from './api'
import {
  AUTO_TOKENS,
  CODE_TOKENS,
  codeTokens,
  formatCodeList,
  parseCodeList,
  segments,
} from './pattern'

const KINDS = [
  'document',
  'itp',
  'transmittal',
  'mdr',
  'rfi',
  'ncr',
  'inspection',
  'scope_change',
  'work_plan',
]

type Draft = {
  record_kind: string
  name: string
  pattern: string
  counter_scope: string[]
  codes: Record<string, string>
  start_value: number
  active: boolean
  values: Record<string, string>
}

function draftOf(s: Scheme | null): Draft {
  return {
    record_kind: s?.record_kind ?? 'document',
    name: s?.name ?? '',
    pattern: s?.pattern ?? '{project}-{discipline}-{type}-{seq:4}',
    counter_scope: s?.counter_scope ?? [],
    codes: Object.fromEntries(
      Object.entries(s?.code_lists ?? {}).map(([k, v]) => [
        k,
        formatCodeList(v),
      ])
    ),
    start_value: s?.start_value ?? 1,
    active: s?.active ?? true,
    values: {},
  }
}

function PatternView({ pattern }: { pattern: string }) {
  return (
    <div className='flex flex-wrap items-center gap-0.5 font-mono text-xs'>
      {segments(pattern).map((s, i) =>
        s.kind === 'literal' ? (
          <span key={i}>{s.text}</span>
        ) : (
          <span
            key={i}
            className={cn(
              'rounded px-1',
              s.known
                ? 'bg-blue-500/15 text-blue-700 dark:text-blue-400'
                : 'bg-red-500/15 text-red-700 dark:text-red-400'
            )}
          >
            {s.name}
            {s.width ? `:${s.width}` : ''}
          </span>
        )
      )}
    </div>
  )
}

function SchemeEditor({
  projectId,
  scheme,
  onClose,
}: {
  projectId: number
  scheme: Scheme | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Draft>(() => draftOf(scheme))
  const save = useSaveScheme(scheme?.id ?? null)
  const tokens = codeTokens(draft.pattern)
  const codeLists = Object.fromEntries(
    tokens
      .filter((tk) => (draft.codes[tk] ?? '').trim())
      .map((tk) => [tk, parseCodeList(draft.codes[tk])])
  )
  const scope = draft.counter_scope.filter((tk) => tokens.includes(tk))
  const preview = usePreview({
    project_id: projectId,
    pattern: draft.pattern,
    counter_scope: scope,
    code_lists: codeLists,
    start_value: draft.start_value,
    values: draft.values,
    scheme_id: scheme?.id ?? null,
  })
  const insert = (token: string) =>
    setDraft({
      ...draft,
      pattern: `${draft.pattern}${token === 'seq' ? '{seq:4}' : `{${token}}`}`,
    })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {scheme ? t('numbering.edit') : t('numbering.new')}
          </DialogTitle>
        </DialogHeader>
        <form
          id='scheme-form'
          className='grid max-h-[70vh] gap-3 overflow-y-auto pe-1'
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(
              {
                project_id: projectId,
                record_kind: draft.record_kind,
                name: draft.name || null,
                pattern: draft.pattern,
                counter_scope: scope,
                code_lists: codeLists,
                start_value: draft.start_value,
                active: draft.active,
              },
              { onSuccess: onClose }
            )
          }}
        >
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='scheme-kind'>{t('numbering.kind')}</Label>
              <NativeSelect
                id='scheme-kind'
                disabled={Boolean(scheme)}
                values={KINDS}
                value={draft.record_kind}
                onChange={(e) =>
                  setDraft({ ...draft, record_kind: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='scheme-name'>{t('numbering.name')}</Label>
              <Input
                id='scheme-name'
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='scheme-pattern'>{t('numbering.pattern')}</Label>
            <Input
              id='scheme-pattern'
              className='font-mono'
              required
              value={draft.pattern}
              onChange={(e) => setDraft({ ...draft, pattern: e.target.value })}
            />
            <div className='flex flex-wrap gap-1'>
              {[...AUTO_TOKENS, ...CODE_TOKENS].map((tk) => (
                <Button
                  key={tk}
                  type='button'
                  size='sm'
                  variant='outline'
                  className='h-6 px-2 font-mono text-xs'
                  onClick={() => insert(tk)}
                >
                  {tk === 'seq' ? '{seq:N}' : `{${tk}}`}
                </Button>
              ))}
            </div>
            <PatternView pattern={draft.pattern} />
          </div>
          {tokens.length ? (
            <div className='grid gap-2'>
              <Label>{t('numbering.code_lists')}</Label>
              <p className='text-xs text-muted-foreground'>
                {t('numbering.code_lists_hint')}
              </p>
              <div className='grid gap-3 sm:grid-cols-2'>
                {tokens.map((tk) => (
                  <div key={tk} className='grid gap-1 rounded-md border p-2'>
                    <div className='flex items-center justify-between'>
                      <span className='font-mono text-xs'>{`{${tk}}`}</span>
                      <label className='flex items-center gap-1 text-xs'>
                        <Checkbox
                          checked={draft.counter_scope.includes(tk)}
                          onCheckedChange={(on) =>
                            setDraft({
                              ...draft,
                              counter_scope: on
                                ? [...draft.counter_scope, tk]
                                : draft.counter_scope.filter((x) => x !== tk),
                            })
                          }
                        />
                        {t('numbering.counter_per')}
                      </label>
                    </div>
                    <Textarea
                      aria-label={`${tk} codes`}
                      className='min-h-20 font-mono text-xs'
                      placeholder={'ME Mechanical\nEL Electrical'}
                      value={draft.codes[tk] ?? ''}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          codes: { ...draft.codes, [tk]: e.target.value },
                        })
                      }
                    />
                    <Input
                      aria-label={`${tk} preview value`}
                      className='h-7 text-xs'
                      placeholder={t('numbering.preview_value')}
                      value={draft.values[tk] ?? ''}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          values: { ...draft.values, [tk]: e.target.value },
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className='grid grid-cols-2 items-end gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='scheme-start'>{t('numbering.start_value')}</Label>
              <Input
                id='scheme-start'
                type='number'
                min={1}
                value={draft.start_value}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    start_value: Math.max(1, Number(e.target.value) || 1),
                  })
                }
              />
            </div>
            <label className='flex items-center gap-2 text-sm'>
              <Switch
                checked={draft.active}
                onCheckedChange={(active) => setDraft({ ...draft, active })}
              />
              {t('numbering.active')}
            </label>
          </div>
          <div className='rounded-md border bg-muted/40 p-3' aria-live='polite'>
            <div className='text-xs text-muted-foreground'>
              {t('numbering.next_number')}
            </div>
            <div className='font-mono text-lg'>
              {preview.data?.number ?? '—'}
            </div>
            {preview.data?.errors.length ? (
              <ul className='mt-1 list-disc ps-5 text-xs text-red-600'>
                {preview.data.errors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            ) : null}
          </div>
          <p className='text-xs text-muted-foreground'>
            {t('numbering.rules')}
          </p>
        </form>
        <DialogFooter>
          <Button type='submit' form='scheme-form' disabled={save.isPending}>
            {t('numbering.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AllocateButton({ scheme }: { scheme: Scheme }) {
  const { t } = useTranslation()
  const allocate = useAllocate(scheme.id)
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<string | null>(null)
  const tokens = codeTokens(scheme.pattern)
  return (
    <>
      <Button
        size='sm'
        variant='outline'
        onClick={() => {
          setResult(null)
          setOpen(true)
        }}
        disabled={!scheme.active}
      >
        <Hash /> {t('numbering.allocate')}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>{t('numbering.allocate')}</DialogTitle>
          </DialogHeader>
          <div className='grid gap-2'>
            {tokens.map((tk) => (
              <div key={tk} className='grid gap-1'>
                <Label htmlFor={`alloc-${tk}`}>{tk}</Label>
                {scheme.code_lists[tk]?.length ? (
                  <NativeSelect
                    id={`alloc-${tk}`}
                    placeholder='—'
                    options={scheme.code_lists[tk].map((c) => ({
                      value: c.code,
                      label: `${c.code} ${c.label ?? ''}`.trim(),
                    }))}
                    value={values[tk] ?? ''}
                    onChange={(e) =>
                      setValues({ ...values, [tk]: e.target.value })
                    }
                  />
                ) : (
                  <Input
                    id={`alloc-${tk}`}
                    value={values[tk] ?? ''}
                    onChange={(e) =>
                      setValues({ ...values, [tk]: e.target.value })
                    }
                  />
                )}
              </div>
            ))}
            {result ? (
              <div className='rounded-md border bg-muted/40 p-2 font-mono'>
                {result}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              disabled={allocate.isPending}
              onClick={() =>
                allocate.mutate(values, {
                  onSuccess: (row) => setResult(row.number),
                })
              }
            >
              {t('numbering.allocate')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Register({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const [kind, setKind] = useState('')
  const { data: rows = [] } = useAllocations(projectId, kind)
  const voiding = useVoid()
  const canAssign = can(session, 'numbering.assign')
  const columns = useMemo<ColDef<Allocation>[]>(
    () => [
      {
        field: 'number',
        headerName: t('numbering.number'),
        flex: 1,
        cellClass: 'font-mono',
      },
      { field: 'record_kind', headerName: t('numbering.kind'), width: 130 },
      {
        field: 'entity_type',
        headerName: t('numbering.record'),
        width: 160,
        valueGetter: (p) =>
          p.data?.entity_type
            ? `${p.data.entity_type} #${p.data.entity_id}`
            : '',
      },
      {
        field: 'allocated_at',
        headerName: t('numbering.allocated_at'),
        width: 170,
        valueFormatter: (p) =>
          p.value ? new Date(p.value as string).toLocaleString() : '',
      },
      {
        field: 'voided',
        headerName: t('numbering.voided'),
        width: 200,
        cellRenderer: (p: ICellRendererParams<Allocation>) =>
          p.data?.voided ? (
            <span className='text-red-600'>{p.data.void_reason}</span>
          ) : canAssign ? (
            <Button
              size='sm'
              variant='ghost'
              className='h-6'
              onClick={() => {
                const reason = window.prompt(t('numbering.void_reason'))
                if (reason && p.data) voiding.mutate({ id: p.data.id, reason })
              }}
            >
              <Ban /> {t('numbering.void')}
            </Button>
          ) : null,
      },
    ],
    [t, canAssign, voiding]
  )
  return (
    <div className='grid gap-2'>
      <div className='flex items-center gap-2'>
        <h3 className='font-medium'>{t('numbering.register')}</h3>
        <NativeSelect
          className='ms-auto h-8 w-44'
          aria-label={t('numbering.kind')}
          placeholder={t('numbering.all_kinds')}
          values={KINDS}
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        />
      </div>
      <div className='h-[360px]'>
        <DataGrid<Allocation>
          rowData={rows}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
        />
      </div>
    </div>
  )
}

function Schemes({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: schemes = [] } = useSchemes(projectId)
  const [editing, setEditing] = useState<Scheme | null | 'new'>(null)
  const canManage = can(session, 'numbering.manage')
  return (
    <div className='grid gap-4'>
      <div className='flex items-center'>
        <h3 className='font-medium'>{t('numbering.schemes')}</h3>
        {canManage ? (
          <Button
            size='sm'
            className='ms-auto'
            onClick={() => setEditing('new')}
          >
            <Plus /> {t('numbering.new')}
          </Button>
        ) : null}
      </div>
      {schemes.length === 0 ? (
        <p className='text-sm text-muted-foreground'>{t('numbering.empty')}</p>
      ) : (
        <div className='grid gap-2 md:grid-cols-2'>
          {schemes.map((s) => (
            <div key={s.id} className='grid gap-2 rounded-lg border p-3'>
              <div className='flex items-center gap-2'>
                <span className='font-medium'>{s.name || s.record_kind}</span>
                <Badge variant='outline'>{s.record_kind}</Badge>
                {!s.active ? (
                  <Badge variant='secondary'>{t('numbering.off')}</Badge>
                ) : null}
                <span className='ms-auto text-xs text-muted-foreground'>
                  {t('numbering.allocated_count', { count: s.allocated })}
                </span>
              </div>
              <PatternView pattern={s.pattern} />
              {s.counter_scope.length ? (
                <div className='text-xs text-muted-foreground'>
                  {t('numbering.counter_per')}: {s.counter_scope.join(', ')}
                </div>
              ) : null}
              <div className='flex gap-2'>
                {canManage ? (
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => setEditing(s)}
                  >
                    <Pencil /> {t('numbering.edit')}
                  </Button>
                ) : null}
                {can(session, 'numbering.assign') ? (
                  <AllocateButton scheme={s} />
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
      {editing ? (
        <SchemeEditor
          projectId={projectId}
          scheme={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
      <Register projectId={projectId} />
    </div>
  )
}

export default function NumberingPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('numbering.title')}
      description={t('numbering.description')}
      projectScoped
    >
      {project ? (
        <Schemes key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('numbering.no_project')}
        </p>
      )}
    </Page>
  )
}
