import { describe, expect, it } from 'vitest'
import type { Position } from './api'
import {
  cellChange,
  compositeRate,
  dropTarget,
  indentTarget,
  insertTarget,
  isFormula,
  outdentTarget,
  parseNumber,
  parseTsv,
  pastedRows,
  visibleRows,
} from './tree'

function pos(
  id: number,
  parent_id: number | null,
  depth: number,
  extra: Partial<Position> = {}
): Position {
  return {
    id,
    parent_id,
    depth,
    kind: 'position',
    ordinal: String(id),
    sort: 0,
    code: null,
    short_text: `row ${id}`,
    long_text: null,
    unit: 'm',
    quantity: '1',
    quantity_formula: null,
    unit_rate: '1',
    total: '1',
    classification: null,
    assembly_id: null,
    has_children: false,
    resources: [],
    ...extra,
  }
}

// 1 (section) > 2, 3 (position with sub 4); 5 (section, empty)
const bill = [
  pos(1, null, 0, { kind: 'section', has_children: true }),
  pos(2, 1, 1),
  pos(3, 1, 1, { has_children: true }),
  pos(4, 3, 2),
  pos(5, null, 0, { kind: 'section' }),
]

describe('visibleRows', () => {
  it('hides rows under collapsed rows and adds detail rows', () => {
    const keys = (c: number[], o: number[]) =>
      visibleRows(bill, new Set(c), new Set(o)).map((r) => r.key)
    expect(keys([], [])).toEqual(['r1', 'r2', 'r3', 'r4', 'r5'])
    expect(keys([1], [])).toEqual(['r1', 'r5'])
    expect(keys([3], [2])).toEqual(['r1', 'r2', 'd2', 'r3', 'r5'])
    expect(keys([], [5])).toEqual(['r1', 'r2', 'r3', 'r4', 'r5'])
  })
})

describe('dropTarget', () => {
  it('drops above a row, or into a section on its lower half', () => {
    expect(dropTarget(bill, bill[1], bill[2], false)).toEqual({
      parent_id: 1,
      before_id: 3,
    })
    expect(dropTarget(bill, bill[1], bill[4], true)).toEqual({
      parent_id: 5,
      before_id: null,
    })
    expect(dropTarget(bill, bill[3], bill[0], true)).toEqual({
      parent_id: 1,
      before_id: 2,
    })
    expect(dropTarget(bill, bill[1], undefined, false)).toEqual({
      parent_id: null,
      before_id: null,
    })
  })

  it('refuses drops into itself and sections under positions', () => {
    expect(dropTarget(bill, bill[0], bill[1], false)).toBeNull()
    expect(dropTarget(bill, bill[2], bill[3], false)).toBeNull()
    expect(dropTarget(bill, bill[4], bill[3], false)).toBeNull()
  })
})

describe('indent and outdent', () => {
  it('moves under the sibling above, or next to the parent', () => {
    expect(indentTarget(bill, bill[2])).toEqual({
      parent_id: 2,
      before_id: null,
    })
    expect(indentTarget(bill, bill[1])).toBeNull()
    expect(outdentTarget(bill, bill[3])).toEqual({
      parent_id: 1,
      before_id: null,
    })
    expect(outdentTarget(bill, bill[1])).toEqual({
      parent_id: null,
      before_id: 5,
    })
    expect(outdentTarget(bill, bill[0])).toBeNull()
  })
})

describe('insertTarget', () => {
  it('places inserts relative to the focused row', () => {
    expect(insertTarget(bill, bill[1], 'position')).toEqual({
      parent_id: 1,
      after_id: 2,
    })
    expect(insertTarget(bill, bill[0], 'position')).toEqual({ parent_id: 1 })
    expect(insertTarget(bill, bill[3], 'section')).toEqual({
      parent_id: null,
      after_id: 1,
    })
    expect(insertTarget(bill, bill[1], 'sub')).toEqual({ parent_id: 2 })
    expect(insertTarget(bill, bill[0], 'sub')).toBeNull()
    expect(insertTarget(bill, undefined, 'section')).toEqual({
      parent_id: null,
    })
  })
})

describe('clipboard', () => {
  it('parses Excel text with quotes, tabs and CRLF', () => {
    expect(parseTsv('a\tb\r\n"multi\nline"\t"say ""hi"""\n\n')).toEqual([
      ['a', 'b'],
      ['multi\nline', 'say "hi"'],
    ])
  })

  it('maps pasted cells from the focused column on', () => {
    const cells = parseTsv('Pipe\t420\tm\t2*3.5\t1.234,50\nValve\t\tpcs\t4\t80')
    expect(pastedRows(cells, 'short_text')).toEqual([
      {
        short_text: 'Pipe',
        classification: '420',
        unit: 'm',
        quantity_formula: '2*3.5',
        unit_rate: '1234.50',
      },
      { short_text: 'Valve', unit: 'pcs', quantity: '4', unit_rate: '80' },
    ])
    expect(pastedRows([['12', '3']], 'quantity')).toEqual([
      { quantity: '12', unit_rate: '3' },
    ])
  })
})

describe('numbers and formulas', () => {
  it('reads either decimal mark', () => {
    expect(parseNumber('1.234,5')).toBe('1234.5')
    expect(parseNumber('1,234.5')).toBe('1234.5')
    expect(parseNumber('3,5')).toBe('3.5')
    expect(parseNumber('-2')).toBe('-2')
    expect(parseNumber('abc')).toBeNull()
  })

  it('tells formulas from numbers', () => {
    expect(isFormula('2*3.5+1.2')).toBe(true)
    expect(isFormula('=4')).toBe(false)
    expect(isFormula('3 x 2')).toBe(true)
    expect(isFormula('-5')).toBe(false)
    expect(isFormula('12.5')).toBe(false)
  })

  it('turns a typed cell into a PATCH body', () => {
    expect(cellChange('quantity', '2*3')).toEqual({ quantity_formula: '2*3' })
    expect(cellChange('quantity', '=2+2')).toEqual({ quantity_formula: '2+2' })
    expect(cellChange('quantity', '7,5')).toEqual({ quantity: '7.5' })
    expect(cellChange('quantity', '')).toEqual({ quantity: null })
    expect(cellChange('unit_rate', 'x')).toMatch(/isn't a rate/)
    expect(cellChange('unit', ' m2 ')).toEqual({ unit: 'm2' })
    expect(cellChange('code', '')).toEqual({ code: null })
  })

  it('computes an assembly rate like the server', () => {
    expect(
      compositeRate([
        { rate: '12.5', factor: '1.05', waste_pct: '0' },
        { rate: '20', factor: '1', waste_pct: '10' },
      ])
    ).toBeCloseTo(35.125)
  })
})
