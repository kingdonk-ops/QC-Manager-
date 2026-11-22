import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type Row = components['schemas']['ModuleAccessRow']
type Level = NonNullable<Row['level']>
const LEVELS: (Level | 'roles')[] = ['roles', 'none', 'view', 'edit', 'full']
const LABEL: Record<string, string> = {
  roles: 'From roles',
  none: 'None',
  view: 'View',
  edit: 'Edit',
  full: 'Full',
}

/** The per-module access grid for one user, with presets. */
export function ModuleAccess({ userId }: { userId: number }) {
  const queryClient = useQueryClient()
  const key = ['platform', 'access', userId]
  const { data: rows = [] } = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/platform/access/{user_id}', {
          params: { path: { user_id: userId } },
        })
      ),
  })
  const done = (data: Row[]) => {
    queryClient.setQueryData(key, data)
    void queryClient.invalidateQueries({ queryKey: ['people'] })
  }
  const set = useMutation({
    mutationFn: (levels: Record<string, Level | null>) =>
      unwrap(
        api.PUT('/api/v1/platform/access/{user_id}', {
          params: { path: { user_id: userId } },
          body: { levels },
        })
      ),
    onSuccess: done,
    onError: handleServerError,
  })
  const preset = useMutation({
    mutationFn: (name: 'full' | 'view_only' | 'minimal' | 'clear') =>
      unwrap(
        api.POST('/api/v1/platform/access/{user_id}/preset', {
          params: { path: { user_id: userId } },
          body: { preset: name },
        })
      ),
    onSuccess: (data) => {
      done(data)
      toast.success('Preset applied')
    },
    onError: handleServerError,
  })

  return (
    <div className='grid gap-3'>
      <div className='flex flex-wrap gap-1.5'>
        {(
          [
            ['full', 'Full access'],
            ['view_only', 'View only'],
            ['minimal', 'Minimal'],
            ['clear', 'Follow roles'],
          ] as const
        ).map(([name, label]) => (
          <Button
            key={name}
            size='sm'
            variant='outline'
            className='h-7 text-xs'
            onClick={() => preset.mutate(name)}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className='grid gap-1.5'>
        {rows.map((row) => (
          <div
            key={row.module}
            className='flex items-center gap-3 rounded-md border px-3 py-1.5 text-sm'
          >
            <span className='flex-1'>
              {row.display_name}
              <span className='block text-[11px] text-muted-foreground'>
                {row.effective?.length
                  ? row.effective.map((p) => p.split('.')[1]).join(', ')
                  : 'no access'}
              </span>
            </span>
            <Select
              value={row.level ?? 'roles'}
              onValueChange={(v) =>
                set.mutate({
                  [row.module]: v === 'roles' ? null : (v as Level),
                })
              }
            >
              <SelectTrigger size='sm' className='h-7 w-32 text-xs'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {LABEL[l]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))}
      </div>
      <p className='text-xs text-muted-foreground'>
        A level replaces what the person's roles give for that module. "From
        roles" removes it.
      </p>
    </div>
  )
}
