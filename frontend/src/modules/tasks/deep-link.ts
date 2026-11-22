import { useEffect } from 'react'
import { useLocation, useRouter } from '@tanstack/react-router'
import { useProjectStore } from '@/stores/project-store'

/**
 * A record id carried in the URL (`/tasks?project=3&task=9`), as notifications link to it.
 * Selecting the project in the URL switches the top bar to it. Returns the id and a setter
 * that rewrites the query string without adding a history entry.
 */
export function useRecordParam(name: string) {
  const router = useRouter()
  const { pathname, searchStr } = useLocation()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const params = new URLSearchParams(searchStr)
  const project = Number(params.get('project')) || null
  const value = Number(params.get(name)) || null

  useEffect(() => {
    if (project && useProjectStore.getState().projectId !== project)
      setProjectId(project)
  }, [project, setProjectId])

  const set = (id: number | null) => {
    const next = new URLSearchParams(searchStr)
    if (id) next.set(name, String(id))
    else {
      next.delete(name)
      next.delete('project')
      next.delete('id')
    }
    const query = next.toString()
    router.history.replace(query ? `${pathname}?${query}` : pathname)
  }

  return [value ?? (Number(params.get('id')) || null), set] as const
}
