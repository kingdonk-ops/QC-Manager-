import { describe, expect, it } from 'vitest'
import { codeTokens, formatCodeList, parseCodeList, segments } from './pattern'

describe('numbering patterns', () => {
  it('splits literals and tokens and flags unknown ones', () => {
    expect(segments('{project}-{discipline}-{seq:4}')).toEqual([
      { kind: 'token', name: 'project', width: undefined, known: true },
      { kind: 'literal', text: '-' },
      { kind: 'token', name: 'discipline', width: undefined, known: true },
      { kind: 'literal', text: '-' },
      { kind: 'token', name: 'seq', width: 4, known: true },
    ])
    expect(segments('{owner}-{seq:2}')[0]).toMatchObject({
      name: 'owner',
      known: false,
    })
    expect(segments('{project:3}')[0]).toMatchObject({ known: false })
  })

  it('lists the code tokens once, in order', () => {
    expect(codeTokens('{project}-{type}-{discipline}-{type}-{seq:3}')).toEqual([
      'type',
      'discipline',
    ])
  })

  it('reads and writes code lists', () => {
    const codes = parseCodeList('me Mechanical\n\nEL  Electrical works\n')
    expect(codes).toEqual([
      { code: 'ME', label: 'Mechanical' },
      { code: 'EL', label: 'Electrical works' },
    ])
    expect(formatCodeList(codes)).toBe('ME Mechanical\nEL Electrical works')
  })
})
