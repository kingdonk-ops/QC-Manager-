/** The log form's editable state and how it becomes the PUT body. */

export type HoursRow = {
  person: string
  trade: string
  hours: string
  node_id: number | null
  node_label: string | null
  /** `''` (on a work anchor), `delay:<code>` or `overhead:<code>`. */
  code: string
}

export type QtyRow = {
  node_id: number | null
  node_label: string | null
  qty: string
  uom: string
}

export type DelayRow = {
  code: string
  hours: string
  node_id: number | null
  node_label: string | null
  description: string
}

export type KitRow = {
  equipment: string
  hours: string
  status: string
}

export type Draft = {
  weather: string
  temp_min_c: string
  temp_max_c: string
  wind_kmh: string
  rain_mm: string
  notes: string
  hours: HoursRow[]
  quantities: QtyRow[]
  delays: DelayRow[]
  equipment: KitRow[]
}

type LogLike = {
  weather?: string | null
  temp_min_c?: string | number | null
  temp_max_c?: string | number | null
  wind_kmh?: string | number | null
  rain_mm?: string | number | null
  notes?: string | null
  hours?: {
    person: string
    trade?: string | null
    hours: string | number
    anchor_id?: number | null
    anchor_code?: string | null
    delay_code?: string | null
    overhead_code?: string | null
  }[]
  quantities?: {
    node_id: number
    node_code?: string | null
    qty: string | number
    uom?: string | null
  }[]
  delays?: {
    code: string
    hours: string | number
    anchor_id?: number | null
    anchor_code?: string | null
    description?: string | null
  }[]
  equipment?: { equipment: string; hours: string | number; status: string }[]
}

const s = (v: unknown) => (v === null || v === undefined ? '' : String(v))
const n = (v: string) => (v.trim() === '' ? null : v.trim())

export function toDraft(log: LogLike): Draft {
  return {
    weather: s(log.weather),
    temp_min_c: s(log.temp_min_c),
    temp_max_c: s(log.temp_max_c),
    wind_kmh: s(log.wind_kmh),
    rain_mm: s(log.rain_mm),
    notes: s(log.notes),
    hours: (log.hours ?? []).map((h) => ({
      person: h.person,
      trade: s(h.trade),
      hours: s(h.hours),
      node_id: h.anchor_id ?? null,
      node_label: h.anchor_code ?? null,
      code: h.delay_code
        ? `delay:${h.delay_code}`
        : h.overhead_code
          ? `overhead:${h.overhead_code}`
          : '',
    })),
    quantities: (log.quantities ?? []).map((q) => ({
      node_id: q.node_id,
      node_label: q.node_code ?? null,
      qty: s(q.qty),
      uom: s(q.uom),
    })),
    delays: (log.delays ?? []).map((d) => ({
      code: d.code,
      hours: s(d.hours),
      node_id: d.anchor_id ?? null,
      node_label: d.anchor_code ?? null,
      description: s(d.description),
    })),
    equipment: (log.equipment ?? []).map((e) => ({
      equipment: e.equipment,
      hours: s(e.hours),
      status: e.status,
    })),
  }
}

/** The PUT body. Rows without a person / equipment name or node are dropped. */
export function toBody(d: Draft) {
  return {
    weather: n(d.weather),
    temp_min_c: n(d.temp_min_c),
    temp_max_c: n(d.temp_max_c),
    wind_kmh: n(d.wind_kmh),
    rain_mm: n(d.rain_mm),
    notes: n(d.notes),
    hours: d.hours
      .filter((h) => h.person.trim())
      .map((h) => {
        const [kind, code] = h.code.split(':')
        return {
          person: h.person.trim(),
          trade: n(h.trade),
          hours: h.hours.trim() || '0',
          node_id: h.node_id,
          delay_code: kind === 'delay' ? code : null,
          overhead_code: kind === 'overhead' ? code : null,
        }
      }),
    quantities: d.quantities
      .filter((q) => q.node_id)
      .map((q) => ({
        node_id: q.node_id as number,
        qty: q.qty.trim() || '0',
        uom: n(q.uom),
      })),
    delays: d.delays
      .filter((x) => x.code)
      .map((x) => ({
        code: x.code,
        hours: x.hours.trim() || '0',
        node_id: x.node_id,
        description: n(x.description),
      })),
    equipment: d.equipment
      .filter((e) => e.equipment.trim())
      .map((e) => ({
        equipment: e.equipment.trim(),
        hours: e.hours.trim() || '0',
        status: e.status,
      })),
  }
}

/** A row's hours need a work anchor unless they carry a delay or overhead code. */
export function unallocated(rows: HoursRow[]) {
  return rows.filter(
    (h) => h.person.trim() && Number(h.hours) > 0 && !h.node_id && !h.code
  )
}

export function sumHours(rows: { hours: string }[]) {
  return rows.reduce((t, r) => t + (Number(r.hours) || 0), 0)
}
