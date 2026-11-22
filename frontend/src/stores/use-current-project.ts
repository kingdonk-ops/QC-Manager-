import { useProjects } from '@/modules/projects/api'
import { useProjectStore } from './project-store'

/** The project chosen in the top bar, once the list has loaded. */
export function useCurrentProject() {
  const { data: projects = [] } = useProjects()
  const projectId = useProjectStore((s) => s.projectId)
  return projects.find((p) => p.id === projectId) ?? null
}
