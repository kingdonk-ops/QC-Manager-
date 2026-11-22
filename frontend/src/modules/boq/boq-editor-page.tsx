import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'
import type {
  CellFocusedEvent,
  ColDef,
  ICellRendererParams,
  RowDragEndEvent,
  ValueSetterParams,
} from 'ag-grid-community'
import type { AgGridReact } from 'ag-grid-react'
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Download,
  FolderPlus,
  IndentDecrease,
  IndentIncrease,
  Layers,
  ListPlus,
  Lock,
  Plus,
  Redo2,
  ShieldCheck,
  Trash2,
  Undo2,
  Unlock,
  Upload,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { StatusBadge } from '@/components/records/status-badge'
import { useModuleParams } from '../_runtime'
import {
  type BoqDetail,
  type Position,
  type Ruleset,
  download,
  useBillActions,
  useBoq,
  useValidation,
} from './api'
import { RULESETS, detailHeight, fmt, scoreTone } from './format'
import { ImportDialog } from './import-dialog'
import { NumberCell, ResourceLines } from './resource-lines'
import {
  type EditField,
  type GridRow,
  type InsertKind,
  cellChange,
  PASTE_FIELDS,
  type PasteField,
  dropTarget,
  indentTarget,
  insertTarget,
  outdentTarget,
  parseTsv,
  pastedRows,
  visibleRows,
} from './tree'
import { ValidationPanel } from './validation-panel'

const STANDARD_LABEL: Record<string, string> = {
  din276: 'DIN 276',
  nrm: 'NRM',
  masterformat: 'MasterFormat',
  uniformat: 'UniFormat',
  uniclass: 'Uniclass',
  custom: 'Custom',
}

/** What the signed-in user may do with this bill. */
function usePermissions(locked: boolean) {
  const session = useSession()
  const mayUpdate = can(session, 'boq.update')
  return {
    mayUpdate,
    mayImport: can(session, 'boq.import'),
    approver: can(session, 'boq.approve'),
    editable: mayUpdate && !locked,
  }
}

function Editor({ bill }: { bill: BoqDetail }) {
  const { t } = useTranslation()
  const boqId = bill.id
  const grid = useRef<AgGridReact<GridRow>>(null)
  const actions = useBillActions(boqId)
  const locked = bill.status === 'locked'
  const { mayUpdate, mayImport, approver, editable } = usePermissions(locked)
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set())
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [focusedId, setFocusedId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<Position | null>(null)
  const [importing, setImporting] = useState(false)
  const [showValidation, setShowValidation] = useState(false)
  const [ruleset, setRuleset] = useState<Ruleset>(
    RULESETS.includes(bill.classification_standard as Ruleset)
      ? (bill.classification_standard as Ruleset)
      : 'boq_quality'
  )
  const [pendingFocus, setPendingFocus] = useState<number | null>(null)
  const { data: report } = useValidation(boqId, ruleset)

  const positions = bill.positions
  const byId = useMemo(
    () => new Map(positions.map((p) => [p.id, p])),
    [positions]
  )
  const rows = useMemo(
    () => visibleRows(positions, collapsed, open),
    [positions, collapsed, open]
  )
  const focused = focusedId !== null ? byId.get(focusedId) : undefined
  const money = useMemo(() => {
    const format = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: bill.currency,
      minimumFractionDigits: 2,
    })
    return (v: string | number | null | undefined) =>
      v === null || v === undefined || v === '' ? '' : format.format(Number(v))
  }, [bill.currency])
  const rate = useMemo(() => {
    const format = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: bill.currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    })
    return (v: string | number | null | undefined) =>
      v === null || v === undefined || v === '' ? '' : format.format(Number(v))
  }, [bill.currency])

  const save = useCallback(
    (position: Position, field: EditField, raw: unknown) => {
      const change = cellChange(field, raw)
      if (typeof change === 'string') return void toast.error(change)
      const current = position[field] ?? ''
      const next = Object.values(change)[0] ?? ''
      if (field !== 'quantity' && String(current) === String(next)) return
      if (
        field === 'quantity' &&
        'quantity' in change &&
        !position.quantity_formula &&
        Number(position.quantity ?? NaN) === Number(change.quantity ?? NaN)
      )
        return
      if (
        field === 'quantity' &&
        'quantity_formula' in change &&
        position.quantity_formula === change.quantity_formula
      )
        return
      actions.update.mutate({ id: position.id, ...change })
    },
    [actions.update]
  )

  const toggle = useCallback(
    (set: React.Dispatch<React.SetStateAction<Set<number>>>, id: number) =>
      set((s) => {
        const next = new Set(s)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      }),
    []
  )

  // Show a row: open its ancestors, scroll to it, focus and flash it.
  const reveal = useCallback(
    (id: number) => {
      const ancestors = new Set<number>()
      let current = byId.get(id)
      while (current?.parent_id != null) {
        ancestors.add(current.parent_id)
        current = byId.get(current.parent_id)
      }
      setCollapsed((s) => new Set([...s].filter((x) => !ancestors.has(x))))
      setPendingFocus(id)
    },
    [byId, setCollapsed]
  )

  useEffect(() => {
    if (pendingFocus === null) return
    const api = grid.current?.api
    const node = api?.getRowNode(`r${pendingFocus}`)
    if (!api || !node || node.rowIndex === null) return
    api.ensureNodeVisible(node, 'middle')
    api.setFocusedCell(node.rowIndex, 'short_text')
    api.flashCells({ rowNodes: [node] })
    setPendingFocus(null)
  }, [pendingFocus, rows])

  useEffect(() => {
    grid.current?.api?.resetRowHeights()
  }, [rows])

  const insert = (kind: InsertKind) => {
    const target = insertTarget(positions, focused, kind)
    if (!target) return
    const before = new Set(positions.map((p) => p.id))
    actions.insert.mutate(
      {
        ...target,
        kind: kind === 'section' ? 'section' : 'position',
        short_text:
          kind === 'section' ? t('boq.new_section') : t('boq.new_position'),
      },
      {
        onSuccess: (next) => {
          const added = next.positions.find((p) => !before.has(p.id))
          if (added) {
            if (target.parent_id !== null)
              setCollapsed((s) => {
                const n = new Set(s)
                n.delete(target.parent_id!)
                return n
              })
            setPendingFocus(added.id)
          }
        },
      }
    )
  }

  const move = (target: ReturnType<typeof indentTarget>) => {
    if (focused && target) actions.move.mutate({ id: focused.id, ...target })
  }

  // Ctrl+Z / Ctrl+Y (and Ctrl+Shift+Z), Delete: when no cell or input is being edited.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable=true]'))
        return
      if (grid.current?.api?.getEditingCells().length) return
      const mod = e.ctrlKey || e.metaKey
      const key = e.key.toLowerCase()
      if (!editable) return
      if (mod && key === 'z' && !e.shiftKey) {
        e.preventDefault()
        if (bill.can_undo) actions.undo.mutate()
      } else if (mod && (key === 'y' || (key === 'z' && e.shiftKey))) {
        e.preventDefault()
        if (bill.can_redo) actions.redo.mutate()
      } else if (e.key === 'Delete' && focused && target?.closest('.ag-root')) {
        e.preventDefault()
        setDeleting(focused)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [
    actions.undo,
    actions.redo,
    bill.can_undo,
    bill.can_redo,
    editable,
    focused,
  ])

  const onPaste = (e: React.ClipboardEvent) => {
    if (!editable || grid.current?.api?.getEditingCells().length) return
    const text = e.clipboardData.getData('text/plain')
    if (!text) return
    const cells = parseTsv(text)
    if (!cells.length) return
    e.preventDefault()
    const cell = grid.current?.api?.getFocusedCell()
    const colId = cell?.column.getColId() as EditField | undefined
    if (cells.length === 1 && cells[0].length === 1 && focused && colId) {
      if (
        focused.kind !== 'section' ||
        !['quantity', 'unit_rate', 'unit'].includes(colId)
      )
        save(focused, colId, cells[0][0])
      return
    }
    const start = PASTE_FIELDS.includes(colId as PasteField)
      ? (colId as PasteField)
      : 'short_text'
    const target =
      focused?.kind === 'section'
        ? { parent_id: focused.id }
        : focused
          ? { parent_id: focused.parent_id, after_id: focused.id }
          : { parent_id: null }
    actions.paste.mutate({ ...target, rows: pastedRows(cells, start) })
  }

  const onRowDragEnd = (e: RowDragEndEvent<GridRow>) => {
    const moving = e.node.data?.position
    if (!editable || !moving) return
    const overNode = e.overNode
    const over = overNode?.data?.position
    const lowerHalf =
      overNode?.rowTop != null && overNode.rowHeight != null
        ? e.y - overNode.rowTop > overNode.rowHeight / 2
        : false
    const target = dropTarget(positions, moving, over, lowerHalf)
    if (!target) return
    if (target.parent_id === moving.parent_id && target.before_id === moving.id)
      return
    actions.move.mutate({ id: moving.id, ...target })
  }

  const columns = useMemo<ColDef<GridRow>[]>(() => {
    const leafEditable = (field: EditField) => (p: { data?: GridRow }) => {
      const pos = p.data?.position
      if (!editable || !pos) return false
      if (field === 'unit_rate')
        return (
          pos.kind !== 'section' && !pos.has_children && !pos.resources.length
        )
      if (field === 'quantity')
        return pos.kind !== 'section' && !pos.has_children
      if (field === 'unit') return pos.kind !== 'section'
      return true
    }
    const setter = (field: EditField) => (p: ValueSetterParams<GridRow>) => {
      if (p.data?.position) save(p.data.position, field, p.newValue)
      return false
    }
    const text = (
      field: EditField,
      headerName: string,
      extra: ColDef<GridRow> = {}
    ): ColDef<GridRow> => ({
      colId: field,
      headerName,
      valueGetter: (p) => p.data?.position[field] ?? '',
      valueSetter: setter(field),
      editable: leafEditable(field),
      ...extra,
    })
    return [
      {
        colId: 'drag',
        headerName: '',
        width: 32,
        rowDrag: (p) => editable && p.data?.kind === 'row',
        sortable: false,
        filter: false,
        resizable: false,
        pinned: 'left',
      },
      {
        colId: 'ordinal',
        headerName: t('boq.col.ordinal'),
        width: 130,
        pinned: 'left',
        sortable: false,
        filter: false,
        valueGetter: (p) => p.data?.position.ordinal,
        cellRenderer: (p: ICellRendererParams<GridRow>) => {
          const pos = p.data?.position
          if (!pos) return null
          return (
            <div
              className='flex h-full items-center gap-1'
              style={{ paddingInlineStart: pos.depth * 16 }}
            >
              {pos.has_children ? (
                <button
                  type='button'
                  aria-label={collapsed.has(pos.id) ? 'Expand' : 'Collapse'}
                  className='text-muted-foreground hover:text-foreground'
                  onClick={() => toggle(setCollapsed, pos.id)}
                >
                  {collapsed.has(pos.id) ? (
                    <ChevronRight className='size-4' />
                  ) : (
                    <ChevronDown className='size-4' />
                  )}
                </button>
              ) : (
                <span className='inline-block w-4' />
              )}
              {pos.kind !== 'section' && !pos.has_children ? (
                <button
                  type='button'
                  aria-label={t('boq.resources')}
                  title={t('boq.resources')}
                  className={cn(
                    'hover:text-foreground',
                    pos.resources.length
                      ? 'text-blue-600 dark:text-blue-400'
                      : 'text-muted-foreground/60'
                  )}
                  onClick={() => toggle(setOpen, pos.id)}
                >
                  <Layers className='size-3.5' />
                </button>
              ) : null}
              <span className='font-mono'>{pos.ordinal}</span>
            </div>
          )
        },
      },
      text('code', t('boq.col.code'), { width: 90, cellClass: 'font-mono' }),
      text('short_text', t('boq.col.text'), { flex: 1, minWidth: 200 }),
      text('long_text', t('boq.col.long_text'), {
        width: 110,
        cellEditor: 'agLargeTextCellEditor',
        cellEditorPopup: true,
        cellEditorParams: { maxLength: 20000, rows: 10, cols: 60 },
        cellClass: 'text-muted-foreground',
      }),
      text(
        'classification',
        `${t('boq.col.classification')}${bill.classification_standard ? ` (${STANDARD_LABEL[bill.classification_standard] ?? bill.classification_standard})` : ''}`,
        { width: 120, cellClass: 'font-mono' }
      ),
      text('unit', t('boq.col.unit'), { width: 70 }),
      text('quantity', t('boq.col.quantity'), {
        width: 110,
        type: 'rightAligned',
        valueGetter: (p) => {
          const pos = p.data?.position
          if (!pos) return ''
          return pos.quantity_formula
            ? `=${pos.quantity_formula}`
            : (pos.quantity ?? '')
        },
        cellRenderer: (p: ICellRendererParams<GridRow>) => {
          const pos = p.data?.position
          if (!pos || pos.kind === 'section' || pos.has_children) return null
          return (
            <span
              className='tabular-nums'
              title={
                pos.quantity_formula
                  ? t('boq.formula_hint', { formula: pos.quantity_formula })
                  : undefined
              }
            >
              {pos.quantity_formula ? (
                <span className='me-1 text-xs text-blue-600 italic'>ƒ</span>
              ) : null}
              {fmt(pos.quantity, 0)}
            </span>
          )
        },
      }),
      text('unit_rate', t('boq.col.rate'), {
        width: 120,
        type: 'rightAligned',
        cellClass: (p) =>
          cn(
            'tabular-nums',
            p.data?.position.resources.length &&
              'text-blue-700 dark:text-blue-300'
          ),
        valueFormatter: (p) =>
          p.data?.position.kind === 'section' || p.data?.position.has_children
            ? ''
            : rate(p.data?.position.unit_rate),
      }),
      {
        colId: 'total',
        headerName: t('boq.col.total'),
        width: 130,
        type: 'rightAligned',
        cellClass: 'tabular-nums',
        valueGetter: (p) => p.data?.position.total,
        valueFormatter: (p) => money(p.value as string),
      },
    ]
  }, [
    bill.classification_standard,
    collapsed,
    editable,
    money,
    rate,
    save,
    setCollapsed,
    setOpen,
    t,
    toggle,
  ])

  const fullWidth = useCallback(
    (p: ICellRendererParams<GridRow>) =>
      p.data ? (
        <ResourceLines
          boqId={boqId}
          projectId={bill.project_id}
          position={p.data.position}
          editable={editable}
          currency={bill.currency}
        />
      ) : null,
    [bill.currency, bill.project_id, boqId, editable]
  )

  const transition = (status: 'draft' | 'priced' | 'locked') =>
    actions.transition.mutate({ status })
  const totals = bill.totals
  const markup = (
    key: 'overhead_pct' | 'profit_pct' | 'contingency_pct' | 'tax_pct',
    label: string
  ) => (
    <label className='flex items-center gap-1.5'>
      <span className='text-muted-foreground'>{label}</span>
      <NumberCell
        value={bill[key]}
        disabled={!editable}
        onSave={(v) => actions.updateBill.mutate({ [key]: v ?? '0' })}
      />
    </label>
  )

  const iconButton = (
    label: string,
    icon: React.ReactNode,
    onClick: () => void,
    disabled?: boolean
  ) => (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          size='sm'
          variant='outline'
          className='h-8 px-2'
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )

  const exportAs = (format: 'xlsx' | 'csv' | 'x83' | 'x84') =>
    void download(`/api/v1/boq/${boqId}/export?format=${format}`).catch(
      (e: Error) => toast.error(e.message)
    )

  return (
    <Page
      fixed
      projectScoped
      title={
        <span className='flex items-center gap-2'>
          {bill.name} <StatusBadge status={bill.status} />
        </span>
      }
      description={
        locked ? (
          <span className='flex items-center gap-1'>
            <Lock className='size-3.5' /> {t('boq.locked')}
          </span>
        ) : (
          t('boq.shortcuts')
        )
      }
      actions={
        <>
          <Button size='sm' variant='ghost' asChild>
            <Link to='/$' params={{ _splat: 'boq' }}>
              <ArrowLeft /> {t('boq.back')}
            </Link>
          </Button>
          {mayUpdate && bill.status === 'draft' ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => transition('priced')}
            >
              {t('boq.mark_priced')}
            </Button>
          ) : null}
          {mayUpdate && bill.status === 'priced' ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => transition('draft')}
            >
              {t('boq.back_to_draft')}
            </Button>
          ) : null}
          {approver && !locked ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => transition('locked')}
            >
              <Lock /> {t('boq.lock')}
            </Button>
          ) : null}
          {approver && locked ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => transition('priced')}
            >
              <Unlock /> {t('boq.unlock')}
            </Button>
          ) : null}
        </>
      }
    >
      <div className='flex flex-wrap items-center gap-1.5'>
        {iconButton(
          `${t('boq.undo')}${bill.undo_label ? `: ${bill.undo_label}` : ''} (Ctrl+Z)`,
          <Undo2 />,
          () => actions.undo.mutate(),
          !editable || !bill.can_undo
        )}
        {iconButton(
          `${t('boq.redo')}${bill.redo_label ? `: ${bill.redo_label}` : ''} (Ctrl+Y)`,
          <Redo2 />,
          () => actions.redo.mutate(),
          !editable || !bill.can_redo
        )}
        <span className='mx-1 h-6 border-s' />
        <Button
          size='sm'
          variant='outline'
          className='h-8'
          disabled={!editable}
          onClick={() => insert('section')}
        >
          <FolderPlus /> {t('boq.add_section')}
        </Button>
        <Button
          size='sm'
          variant='outline'
          className='h-8'
          disabled={!editable}
          onClick={() => insert('position')}
        >
          <Plus /> {t('boq.add_position')}
        </Button>
        <Button
          size='sm'
          variant='outline'
          className='h-8'
          disabled={!editable || !focused || focused.kind === 'section'}
          onClick={() => insert('sub')}
        >
          <ListPlus /> {t('boq.add_sub')}
        </Button>
        {iconButton(
          t('boq.indent'),
          <IndentIncrease />,
          () => focused && move(indentTarget(positions, focused)),
          !editable || !focused
        )}
        {iconButton(
          t('boq.outdent'),
          <IndentDecrease />,
          () => focused && move(outdentTarget(positions, focused)),
          !editable || !focused?.parent_id
        )}
        {iconButton(
          t('boq.delete'),
          <Trash2 />,
          () => focused && setDeleting(focused),
          !editable || !focused
        )}
        <span className='mx-1 h-6 border-s' />
        {iconButton(t('boq.expand_all'), <ChevronsUpDown />, () =>
          setCollapsed(new Set())
        )}
        {iconButton(t('boq.collapse_all'), <ChevronsDownUp />, () =>
          setCollapsed(
            new Set(positions.filter((p) => p.has_children).map((p) => p.id))
          )
        )}
        <div className='ms-auto flex items-center gap-1.5'>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size='sm' variant='outline' className='h-8'>
                <Download /> {t('boq.import_export')}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end'>
              {mayImport ? (
                <>
                  <DropdownMenuItem
                    disabled={!editable}
                    onSelect={() => setImporting(true)}
                  >
                    <Upload /> {t('boq.import')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              ) : null}
              <DropdownMenuItem onSelect={() => exportAs('xlsx')}>
                {t('boq.export_xlsx')}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportAs('csv')}>
                {t('boq.export_csv')}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportAs('x83')}>
                {t('boq.export_x83')}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportAs('x84')}>
                {t('boq.export_x84')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            size='sm'
            variant={showValidation ? 'secondary' : 'outline'}
            className='h-8'
            onClick={() => setShowValidation((v) => !v)}
          >
            <ShieldCheck /> {t('boq.validate')}
            {report ? (
              <span
                className={cn(
                  'font-semibold tabular-nums',
                  scoreTone(report.score)
                )}
                data-testid='boq-score-badge'
              >
                {report.score}%
              </span>
            ) : null}
          </Button>
        </div>
      </div>

      <div className='flex min-h-[420px] flex-1 gap-3'>
        <div
          className='min-w-0 flex-1'
          onPaste={onPaste}
          data-testid='boq-grid'
        >
          <DataGrid<GridRow>
            ref={grid}
            rowData={rows}
            columnDefs={columns}
            defaultColDef={{ sortable: false, filter: false }}
            getRowId={(p) => p.data.key}
            isFullWidthRow={(p) => p.rowNode.data?.kind === 'detail'}
            fullWidthCellRenderer={fullWidth}
            getRowHeight={(p) =>
              p.data?.kind === 'detail'
                ? detailHeight(p.data.position.resources.length)
                : undefined
            }
            getRowClass={(p) =>
              p.data?.kind === 'row' &&
              (p.data.position.kind === 'section' ||
                p.data.position.has_children)
                ? 'font-semibold bg-muted/50'
                : undefined
            }
            onCellFocused={(e: CellFocusedEvent<GridRow>) => {
              if (e.rowIndex === null || e.rowPinned) return
              const node = e.api.getDisplayedRowAtIndex(e.rowIndex)
              if (node?.data) setFocusedId(node.data.position.id)
            }}
            onRowDragEnd={onRowDragEnd}
            stopEditingWhenCellsLoseFocus
          />
        </div>
        {showValidation ? (
          <div className='hidden w-80 shrink-0 lg:block'>
            <ValidationPanel
              boqId={boqId}
              ruleset={ruleset}
              onRuleset={setRuleset}
              onFinding={reveal}
            />
          </div>
        ) : null}
      </div>

      <div className='flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md border px-4 py-2 text-sm'>
        <span className='font-medium'>{t('boq.markups')}</span>
        {markup('overhead_pct', t('boq.overhead'))}
        {markup('profit_pct', t('boq.profit'))}
        {markup('contingency_pct', t('boq.contingency'))}
        {markup('tax_pct', t('boq.tax'))}
        <dl className='ms-auto grid grid-cols-[auto_auto] gap-x-4 text-end tabular-nums sm:grid-cols-[auto_auto_auto_auto]'>
          <dt className='text-muted-foreground'>{t('boq.net_total')}</dt>
          <dd>{money(totals.net_total)}</dd>
          <dt className='text-muted-foreground'>{t('boq.overhead_amount')}</dt>
          <dd>{money(totals.overhead)}</dd>
          <dt className='text-muted-foreground'>{t('boq.profit_amount')}</dt>
          <dd>{money(totals.profit)}</dd>
          <dt className='text-muted-foreground'>
            {t('boq.contingency_amount')}
          </dt>
          <dd>{money(totals.contingency)}</dd>
          <dt className='text-muted-foreground'>{t('boq.subtotal')}</dt>
          <dd>{money(totals.subtotal)}</dd>
          <dt className='text-muted-foreground'>{t('boq.tax_amount')}</dt>
          <dd>{money(totals.tax)}</dd>
          <dt className='font-semibold'>{t('boq.grand_total')}</dt>
          <dd className='font-semibold' data-testid='boq-grand-total'>
            {money(totals.grand_total)}
          </dd>
        </dl>
      </div>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('boq.delete_row')}
        desc={t('boq.delete_row_desc', {
          text: deleting ? `${deleting.ordinal} ${deleting.short_text}` : '',
        })}
        destructive
        confirmText={t('boq.delete')}
        handleConfirm={() => {
          if (deleting) actions.remove.mutate(deleting.id)
          setDeleting(null)
          setFocusedId(null)
        }}
      />
      <ImportDialog
        open={importing}
        onOpenChange={setImporting}
        title={t('boq.import_title')}
        previewUrl={`/api/v1/boq/${boqId}/import/preview`}
        importUrl={`/api/v1/boq/${boqId}/import`}
        gaeb
        replaceOption
        onDone={() => actions.refresh()}
      />
    </Page>
  )
}

export default function BoqEditorPage() {
  const { boqId } = useModuleParams()
  const { data: bill, error } = useBoq(Number(boqId))
  if (error)
    return (
      <Page title='—'>
        <p className='text-sm text-muted-foreground'>{error.message}</p>
      </Page>
    )
  if (!bill) return null
  return <Editor key={bill.id} bill={bill} />
}
