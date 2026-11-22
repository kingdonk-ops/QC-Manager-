import { describe, expect, it } from 'vitest'
import {
  type FieldDef,
  fieldEditable,
  fieldProblems,
  fieldsByStep,
  isOpen,
  keyFromLabel,
  missingFor,
  movesFor,
} from './workflow'

const fields: FieldDef[] = [
  { key: 'defect', label: 'Defect', type: 'text', step: 'raise' },
  {
    key: 'rectification',
    label: 'What was done',
    type: 'textarea',
    step: 'rectify',
    required: true,
  },
  { key: 'notes', label: 'Notes', type: 'text', step: 'verify' },
]

describe('issue workflow', () => {
  it('offers the next steps of each type', () => {
    expect(movesFor('punch', 'open').map((m) => m.to)).toEqual(['rectified'])
    expect(movesFor('punch', 'rectified').map((m) => m.to)).toEqual([
      'verified',
      'open',
    ])
    expect(movesFor('ncr', 'effectiveness').find((m) => m.attest)?.to).toBe(
      'closed'
    )
    expect(movesFor('ncr', 'closed')).toEqual([])
    expect(isOpen('upgraded')).toBe(false)
  })

  it('locks the fields of completed steps', () => {
    expect(fieldEditable('punch', 'open', fields[1])).toBe(true)
    expect(fieldEditable('punch', 'rectified', fields[1])).toBe(false)
    expect(fieldEditable('punch', 'rectified', fields[2])).toBe(true)
    expect(fieldEditable('punch', 'closed', fields[2])).toBe(false)
  })

  it('lists the required fields a move still needs', () => {
    expect(missingFor('punch', 'open', 'rectified', fields, {})).toEqual([
      'What was done',
    ])
    expect(
      missingFor('punch', 'open', 'rectified', fields, { rectification: 'x' })
    ).toEqual([])
    expect(fieldsByStep('punch', fields).map((g) => g.step)).toEqual([
      'raise',
      'rectify',
      'verify',
    ])
  })

  it('makes keys and finds field problems', () => {
    expect(keyFromLabel('Measured DFT (µm)')).toBe('measured_dft')
    expect(keyFromLabel('1st coat', [])).toBe('f_1st_coat')
    expect(keyFromLabel('Defect', ['defect'])).toBe('defect_2')
    expect(
      fieldProblems('punch', [
        { key: 'a', label: 'A', type: 'select', step: 'containment' },
      ])
    ).toEqual(['a: step containment is not a punch step', 'a: needs options'])
  })
})
