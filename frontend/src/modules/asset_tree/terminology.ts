/**
 * The project's words for its levels and domain nouns (ADR 0003 terminology packs).
 *
 *   const term = useTerms(projectId)
 *   term('level.rsw')          // "RSW"
 *   term('level.rsw', 3)       // "RSWs"
 *   term('role.work_anchor')   // "RSW" in a remediation project, "Line" in a CUI one
 *
 * Never hard-code a level name in a screen: go through `term`.
 */
import { useCallback } from 'react'
import { type Term, useTermList } from './api'

export type TermFn = (key: string, count?: number) => string

export function resolveTerm(
  terms: Term[] | undefined,
  key: string,
  count = 1
): string {
  const found = terms?.find((t) => t.key === key)
  if (found) return count === 1 ? found.one : found.other
  const last = key.split('.').pop() ?? key
  const word = last.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  return count === 1 ? word : `${word}s`
}

export function useTerms(projectId: number): TermFn {
  const { data } = useTermList(projectId)
  return useCallback(
    (key: string, count = 1) => resolveTerm(data, key, count),
    [data]
  )
}
