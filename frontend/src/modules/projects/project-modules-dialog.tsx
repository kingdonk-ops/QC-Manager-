import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Project } from './api'

/** Per-project module overrides over the system-wide switches. */
export function ProjectModulesDialog({
  project,
  onClose,
}: {
  project: Project | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { data: modules = [] } = useQuery({
    queryKey: ['platform', 'modules', 'admin'],
    queryFn: () => unwrap(api.GET('/api/v1/modules')),
    enabled: project !== null,
  })
  const { data: overrides = {} } = useQuery({
    queryKey: ['projects', project?.id, 'modules'],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/projects/{project_id}/modules', {
          params: { path: { project_id: project!.id } },
        })
      ),
    enabled: project !== null,
  })
  const save = useMutation({
    mutationFn: (change: Record<string, boolean | null>) =>
      unwrap(
        api.PUT('/api/v1/projects/{project_id}/modules', {
          params: { path: { project_id: project!.id } },
          body: { overrides: change },
        })
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['projects', project?.id, 'modules'],
      })
      void queryClient.invalidateQueries({ queryKey: ['platform', 'modules'] })
    },
    onError: handleServerError,
  })

  const switchable = modules.filter((m) => m.installed && !m.core)
  return (
    <Dialog open={project !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-w-lg'>
        <DialogHeader>
          <DialogTitle>Modules for {project?.name}</DialogTitle>
          <DialogDescription>
            Override the system-wide switches for this project only. A module
            switched off system-wide stays off.
          </DialogDescription>
        </DialogHeader>
        <div className='grid max-h-[60vh] gap-1.5 overflow-y-auto'>
          {switchable.map((m) => {
            const value =
              m.name in overrides
                ? overrides[m.name]
                  ? 'on'
                  : 'off'
                : 'default'
            return (
              <div
                key={m.name}
                className='flex items-center gap-3 rounded-md border px-3 py-1.5 text-sm'
              >
                <span className='flex-1'>{m.display_name}</span>
                <Select
                  value={value}
                  onValueChange={(v) =>
                    save.mutate({
                      [m.name]: v === 'default' ? null : v === 'on',
                    })
                  }
                >
                  <SelectTrigger size='sm' className='h-7 w-40 text-xs'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='default'>System default</SelectItem>
                    <SelectItem value='on'>On for this project</SelectItem>
                    <SelectItem value='off'>Off for this project</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )
          })}
        </div>
      </DialogContent>
    </Dialog>
  )
}
