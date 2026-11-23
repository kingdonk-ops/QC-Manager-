export type Filters = {
  search: string
  status: string
  family: string
  category: string
}

export const NO_FILTERS: Filters = {
  search: '',
  status: '',
  family: '',
  category: '',
}

type Filterable = {
  reference: string
  title: string
  status: string
  family: string
  design_check_category?: number | null
}

/** The loaded items that match the filters. This only narrows what is already on the page; it judges nothing. */
export function applyFilters<T extends Filterable>(rows: T[], f: Filters): T[] {
  const q = f.search.trim().toLowerCase()
  return rows.filter((r) => {
    if (q && !`${r.reference} ${r.title}`.toLowerCase().includes(q))
      return false
    if (f.status && r.status !== f.status) return false
    if (f.family && r.family !== f.family) return false
    if (f.category) {
      const c = r.design_check_category
      const unassigned = c === null || c === undefined
      if (f.category === 'unassigned' ? !unassigned : String(c) !== f.category)
        return false
    }
    return true
  })
}
