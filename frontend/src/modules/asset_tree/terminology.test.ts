import { describe, expect, it } from 'vitest'
import { type Term, schemaFields } from './api'
import { resolveTerm } from './terminology'

const terms: Term[] = [
  { key: 'level.rsw', one: 'RSW', other: 'RSWs', source: 'level' },
  { key: 'level.line', one: 'Line', other: 'Lines', source: 'project' },
  {
    key: 'noun.item',
    one: 'Test point',
    other: 'Test points',
    source: 'project',
  },
]

describe('resolveTerm', () => {
  it('uses the project words, singular or plural', () => {
    expect(resolveTerm(terms, 'level.rsw')).toBe('RSW')
    expect(resolveTerm(terms, 'level.rsw', 2)).toBe('RSWs')
    expect(resolveTerm(terms, 'noun.item', 0)).toBe('Test points')
  })

  it('falls back to the key when the project has no word for it', () => {
    expect(resolveTerm(terms, 'noun.job_pack')).toBe('Job pack')
    expect(resolveTerm(undefined, 'noun.job_pack', 3)).toBe('Job packs')
  })
})

describe('schemaFields', () => {
  it('turns a JSONSchema into form fields', () => {
    const fields = schemaFields({
      properties: {
        priority: { type: 'string', enum: ['P1', 'P2'] },
        budget_hrs: { type: 'number', title: 'Budget hrs' },
        shutdown: { type: 'boolean' },
        last_inspection_date: { type: 'string', format: 'date' },
      },
    })
    expect(fields.map((f) => [f.key, f.type, f.title])).toEqual([
      ['priority', 'enum', 'Priority'],
      ['budget_hrs', 'number', 'Budget hrs'],
      ['shutdown', 'boolean', 'Shutdown'],
      ['last_inspection_date', 'date', 'Last inspection date'],
    ])
    expect(fields[0].options).toEqual(['P1', 'P2'])
    expect(schemaFields({})).toEqual([])
    expect(schemaFields(null)).toEqual([])
  })
})
