/**
 * The bill's hierarchy as a flat grid: AG Grid Community has no tree data, so the editor shows
 * the server's depth-first list, hides what's under collapsed rows, indents by depth, and adds a
 * full-width "detail" row under each position whose resources are open.
 */
import type { Position } from './api'

export type GridRow =
  | { key: string; kind: 'row'; position: Position }
  | { key: string; kind: 'detail'; position: Position }

export function visibleRows(
  positions: Position[],
  collapsed: ReadonlySet<number>,
  open: ReadonlySet<number>
): GridRow[] {
  const rows: GridRow[] = []
  let hideBelow: number | null = null
  for (const p of positions) {
    if (hideBelow !== null) {
      if (p.depth > hideBelow) continue
      hideBelow = null
    }
    rows.push({ key: `r${p.id}`, kind: 'row', position: p })
    if (open.has(p.id) && p.kind !== 'section')
      rows.push({ key: `d${p.id}`, kind: 'detail', position: p })
    if (collapsed.has(p.id) && p.has_children) hideBelow = p.depth
  }
  return rows
}

export function childrenOf(positions: Position[], parentId: number | null) {
  return positions.filter((p) => p.parent_id === parentId)
}

export function isDescendant(
  positions: Position[],
  id: number,
  ancestorId: number
): boolean {
  const byId = new Map(positions.map((p) => [p.id, p]))
  let current = byId.get(id)
  while (current?.parent_id != null) {
    if (current.parent_id === ancestorId) return true
    current = byId.get(current.parent_id)
  }
  return false
}

export type MoveTarget = { parent_id: number | null; before_id: number | null }

/**
 * Where a dragged row lands. Dropping on the upper half of a row puts it above that row, as its
 * sibling; on the lower half of a section (or a position with sub-positions), inside it as the
 * first child. Dropping below the last row moves it to the end of the top level.
 */
export function dropTarget(
  positions: Position[],
  moving: Position,
  over: Position | undefined,
  lowerHalf: boolean
): MoveTarget | null {
  if (!over) return { parent_id: null, before_id: null }
  if (over.id === moving.id || isDescendant(positions, over.id, moving.id))
    return null
  const into =
    lowerHalf &&
    (over.kind === 'section' || over.has_children) &&
    !(moving.kind === 'section' && over.kind !== 'section')
  if (into) {
    const first = childrenOf(positions, over.id).find((c) => c.id !== moving.id)
    return { parent_id: over.id, before_id: first?.id ?? null }
  }
  if (moving.kind === 'section' && over.parent_id !== null) {
    const parent = positions.find((p) => p.id === over.parent_id)
    if (parent && parent.kind !== 'section') return null
  }
  return { parent_id: over.parent_id, before_id: over.id }
}

/** Make the row the last child of the sibling above it. */
export function indentTarget(
  positions: Position[],
  row: Position
): MoveTarget | null {
  const siblings = childrenOf(positions, row.parent_id)
  const index = siblings.findIndex((s) => s.id === row.id)
  const above = siblings[index - 1]
  if (!above) return null
  if (row.kind === 'section' && above.kind !== 'section') return null
  return { parent_id: above.id, before_id: null }
}

/** Make the row the sibling just below its parent. */
export function outdentTarget(
  positions: Position[],
  row: Position
): MoveTarget | null {
  if (row.parent_id === null) return null
  const parent = positions.find((p) => p.id === row.parent_id)
  if (!parent) return null
  const siblings = childrenOf(positions, parent.parent_id)
  const next = siblings[siblings.findIndex((s) => s.id === parent.id) + 1]
  return { parent_id: parent.parent_id, before_id: next?.id ?? null }
}

/** Excel's clipboard text: tab-separated cells, newline-separated rows, quotes around cells with either. */
export function parseTsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"'
        i++
      } else if (ch === '"') quoted = false
      else cell += ch
    } else if (ch === '"' && cell === '') quoted = true
    else if (ch === '\t') {
      row.push(cell)
      cell = ''
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += ch
  }
  if (cell !== '' || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows.filter((r) => r.some((c) => c.trim() !== ''))
}

/** A number typed or pasted with either decimal mark, as a plain decimal string; `null` if it isn't one. */
export function parseNumber(text: string): string | null {
  let s = text.replace(/\s/g, '').replace(/[^\d.,-]/g, '')
  if (!s) return null
  if (s.includes(',') && s.includes('.'))
    s =
      s.lastIndexOf(',') > s.lastIndexOf('.')
        ? s.replace(/\./g, '').replace(',', '.')
        : s.replace(/,/g, '')
  else s = s.replace(',', '.')
  return /^-?\d*\.?\d+$/.test(s) ? s : null
}

/** More than a plain number: `2*3.5+1.2`, `(4+2)/3`, `3 x 2`. */
export function isFormula(text: string): boolean {
  const t = text.trim().replace(/^=/, '')
  return /[-+*/^()x×÷]/.test(t.replace(/^-/, '')) && /\d/.test(t)
}

export const PASTE_FIELDS = [
  'code',
  'short_text',
  'classification',
  'unit',
  'quantity',
  'unit_rate',
] as const
export type PasteField = (typeof PASTE_FIELDS)[number]
export type PastedRow = Partial<Record<PasteField | 'quantity_formula', string>>

/** Spreadsheet cells as new positions, the first cell going to `startField` and the rest to the columns after it. */
export function pastedRows(
  cells: string[][],
  startField: PasteField = 'short_text'
): PastedRow[] {
  const fields = PASTE_FIELDS.slice(PASTE_FIELDS.indexOf(startField))
  return cells.map((cellsOfRow) => {
    const row: PastedRow = {}
    fields.forEach((field, i) => {
      const raw = (cellsOfRow[i] ?? '').trim()
      if (!raw) return
      if (field === 'quantity' && isFormula(raw)) row.quantity_formula = raw
      else if (field === 'quantity' || field === 'unit_rate') {
        const n = parseNumber(raw)
        if (n !== null) row[field] = n
      } else row[field] = raw
    })
    return row
  })
}

export type InsertKind = 'section' | 'position' | 'sub'

/** Where a toolbar insert goes, relative to the focused row. */
export function insertTarget(
  positions: Position[],
  focused: Position | undefined,
  kind: InsertKind
): { parent_id: number | null; after_id?: number } | null {
  if (kind === 'sub') {
    if (!focused || focused.kind === 'section') return null
    return { parent_id: focused.id }
  }
  if (kind === 'position') {
    if (!focused) return { parent_id: null }
    if (focused.kind === 'section') return { parent_id: focused.id }
    return { parent_id: focused.parent_id, after_id: focused.id }
  }
  // a section: next to the nearest section around the focused row
  let current = focused
  while (current && current.kind !== 'section')
    current = positions.find((p) => p.id === current?.parent_id)
  if (!current) return { parent_id: null }
  return { parent_id: current.parent_id, after_id: current.id }
}

export type EditField =
  | 'code'
  | 'short_text'
  | 'long_text'
  | 'classification'
  | 'unit'
  | 'quantity'
  | 'unit_rate'

/** The PATCH body for a value typed into a cell, or why it can't be saved. */
export function cellChange(
  field: EditField,
  raw: unknown
): Record<string, string | null> | string {
  const text = raw === null || raw === undefined ? '' : String(raw).trim()
  if (field === 'quantity') {
    if (!text) return { quantity: null }
    if (isFormula(text)) return { quantity_formula: text.replace(/^=/, '') }
    const n = parseNumber(text)
    return n === null ? `'${text}' isn't a quantity` : { quantity: n }
  }
  if (field === 'unit_rate') {
    if (!text) return { unit_rate: null }
    const n = parseNumber(text)
    return n === null ? `'${text}' isn't a rate` : { unit_rate: n }
  }
  return { [field]: text || (field === 'short_text' ? '' : null) }
}

/** factor × (1 + waste %) × rate, summed: the same composite rate the server computes. */
export function compositeRate(
  lines: { rate: string; factor: string; waste_pct: string }[]
) {
  return lines.reduce(
    (sum, l) =>
      sum +
      Number(parseNumber(l.factor) ?? 0) *
        (1 + Number(parseNumber(l.waste_pct) ?? 0) / 100) *
        Number(l.rate),
    0
  )
}
