import { useEffect, useState } from 'react'
import { useProjectStore } from '@/stores/project-store'

/** Reads `?project=&id=` from a notification link: selects the project and returns the record id to open. */
export function useDeepLink() {
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const [id] = useState(() => {
    const value = Number(new URLSearchParams(window.location.search).get('id'))
    return Number.isInteger(value) && value > 0 ? value : null
  })
  useEffect(() => {
    const project = Number(
      new URLSearchParams(window.location.search).get('project')
    )
    if (Number.isInteger(project) && project > 0) setProjectId(project)
  }, [setProjectId])
  return id
}
