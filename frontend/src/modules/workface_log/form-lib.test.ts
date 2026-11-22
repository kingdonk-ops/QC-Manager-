import { describe, expect, it } from 'vitest'
import { sumHours, toBody, toDraft, unallocated } from './form-lib'

const log = {
  weather: 'Fine',
  temp_max_c: '32.0',
  hours: [
    {
      person: 'J. Miller',
      trade: 'Rigger',
      hours: '8.5',
      anchor_id: 4,
      anchor_code: '101 / 101.1',
    },
    { person: 'J. Miller', hours: '1.5', delay_code: 'weather' },
    { person: 'K. Thorne', hours: '1', overhead_code: 'toolbox' },
  ],
  quantities: [{ node_id: 4, node_code: '101 / 101.1', qty: '14', uom: 'm2' }],
}

describe('toDraft / toBody', () => {
  it('round-trips a log into the PUT body', () => {
    const draft = toDraft(log)
    expect(draft.hours.map((h) => h.code)).toEqual([
      '',
      'delay:weather',
      'overhead:toolbox',
    ])
    const body = toBody(draft)
    expect(body.weather).toBe('Fine')
    expect(body.temp_min_c).toBeNull()
    expect(body.hours).toEqual([
      {
        person: 'J. Miller',
        trade: 'Rigger',
        hours: '8.5',
        node_id: 4,
        delay_code: null,
        overhead_code: null,
      },
      {
        person: 'J. Miller',
        trade: null,
        hours: '1.5',
        node_id: null,
        delay_code: 'weather',
        overhead_code: null,
      },
      {
        person: 'K. Thorne',
        trade: null,
        hours: '1',
        node_id: null,
        delay_code: null,
        overhead_code: 'toolbox',
      },
    ])
    expect(body.quantities).toEqual([{ node_id: 4, qty: '14', uom: 'm2' }])
  })

  it('drops blank rows', () => {
    const draft = toDraft({})
    draft.hours.push({
      person: ' ',
      trade: '',
      hours: '4',
      node_id: null,
      node_label: null,
      code: '',
    })
    draft.quantities.push({
      node_id: null,
      node_label: null,
      qty: '3',
      uom: '',
    })
    expect(toBody(draft).hours).toEqual([])
    expect(toBody(draft).quantities).toEqual([])
  })
})

describe('unallocated', () => {
  it('finds hours with neither a work anchor nor a code', () => {
    const rows = toDraft(log).hours
    expect(unallocated(rows)).toEqual([])
    rows.push({
      person: 'New',
      trade: '',
      hours: '8',
      node_id: null,
      node_label: null,
      code: '',
    })
    rows.push({
      person: 'Zero',
      trade: '',
      hours: '0',
      node_id: null,
      node_label: null,
      code: '',
    })
    expect(unallocated(rows).map((r) => r.person)).toEqual(['New'])
    expect(sumHours(rows)).toBe(19)
  })
})
