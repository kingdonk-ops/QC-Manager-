import { describe, expect, it } from 'vitest'
import { checkValue, compose, parse, type Convention } from './naming'

const convention: Convention = {
  separator: '-',
  fields: [
    { key: 'project', label: 'Project', min_length: 2, max_length: 6 },
    {
      key: 'type',
      label: 'Type',
      codes: [{ code: 'DR' }, { code: 'M3' }],
    },
    {
      key: 'number',
      label: 'Number',
      min_length: 4,
      max_length: 6,
      charset: 'numeric',
    },
  ],
}

describe('CDE naming', () => {
  it('builds the name and upper-cases the codes', () => {
    const result = compose(convention, {
      project: 'prj',
      type: 'dr',
      number: '0001',
    })
    expect(result).toEqual({ name: 'PRJ-DR-0001', errors: {} })
  })

  it('names the field that fails and why', () => {
    const { errors } = compose(convention, {
      project: 'PRJ',
      type: 'XY',
      number: '12',
    })
    expect(errors.type).toBe(
      "Type (type): 'XY' is not an allowed code (allowed: DR, M3)"
    )
    expect(errors.number).toBe(
      "Number (number): '12' must be 4 to 6 characters long"
    )
    expect(errors.project).toBeUndefined()
  })

  it('refuses the separator, wrong characters and blanks', () => {
    const [project, , number] = convention.fields
    expect(checkValue(project, 'A-B', '-')).toContain('separator')
    expect(checkValue(number, '12A4', '-')).toContain('only digits')
    expect(checkValue(project, '', '-')).toBe('Project (project) is required')
  })

  it('parses a file name into fields', () => {
    expect(parse(convention, 'prj-dr-0002')).toEqual({
      project: 'PRJ',
      type: 'DR',
      number: '0002',
    })
    expect(parse(convention, 'PRJ-DR')).toBeNull()
  })
})
