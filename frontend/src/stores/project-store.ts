import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** The project the workspace is focused on, remembered per browser. */
type ProjectState = {
  projectId: number | null
  setProjectId: (id: number | null) => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      projectId: null,
      setProjectId: (projectId) => set({ projectId }),
    }),
    { name: 'current-project' }
  )
)
