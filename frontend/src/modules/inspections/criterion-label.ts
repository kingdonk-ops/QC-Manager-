import type { TemplateItem } from './api'
import type { Criterion } from './criteria-api'
import { isNumericRule, itemLimits, toleranceDisplay } from './tolerance'

export function criterionLabel(c: Criterion): string {
  const tolerance = toleranceDisplay(c)
  return `${c.code} · ${c.title}${tolerance ? ` (${tolerance})` : ''}`
}

/** The code and title of a criterion by id for read-only screens; its number alone while the library is not loaded. */
export function criterionName(
  criteria: Criterion[],
  id: number | null | undefined
): string | null {
  if (id == null) return null
  const found = criteria.find((c) => c.id === id)
  return found ? `${found.code} · ${found.title}` : `#${id}`
}

/**
 * A template item after choosing (or clearing) a criterion: the limits and unit follow it, a clear unlocks them.
 * A numeric criterion makes the item a numeric reading, as the inspection page presents it.
 */
export function applyCriterion(
  item: TemplateItem,
  criterion: Criterion | null
): TemplateItem {
  if (!criterion) return { ...item, criterion_id: null }
  return {
    ...item,
    ...(isNumericRule(criterion.rule_type)
      ? { response_type: 'numeric' as const }
      : {}),
    criterion_id: criterion.id,
    ...itemLimits(criterion),
  }
}

/**
 * An item as the editor shows it: one saved with a link to a numeric criterion (for example through the template
 * API, without limits) is a numeric reading with that criterion's limits and unit. Anything else is untouched.
 */
export function presentItem(
  item: TemplateItem,
  criteria: Criterion[]
): TemplateItem {
  if (item.criterion_id == null) return item
  const linked = criteria.find((c) => c.id === item.criterion_id)
  return linked && isNumericRule(linked.rule_type)
    ? applyCriterion(item, linked)
    : item
}
