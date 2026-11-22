import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { api, type ApiError, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Page } from '@/components/layout/page'

type Module = components['schemas']['ModuleRead']

const CATEGORY_ORDER = [
  'core',
  'business',
  'portal',
  'integration',
  'extension',
]

export default function ModulesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [pending, setPending] = useState<{
    module: Module
    enabled: boolean
    affected: string[]
  } | null>(null)
  const { data: modules = [] } = useQuery({
    queryKey: ['platform', 'modules', 'admin'],
    queryFn: () => unwrap(api.GET('/api/v1/modules')),
  })
  const names = useMemo(
    () => Object.fromEntries(modules.map((m) => [m.name, m.display_name])),
    [modules]
  )

  const toggle = useMutation({
    mutationFn: ({
      name,
      enabled,
      cascade,
    }: {
      name: string
      enabled: boolean
      cascade: boolean
    }) =>
      unwrap(
        api.PATCH('/api/v1/modules/{name}/toggle', {
          params: { path: { name } },
          body: { enabled, cascade },
        })
      ),
    onSuccess: (result) => {
      toast.success(
        `${result.changed.map((n) => names[n] ?? n).join(', ')} switched`
      )
      setPending(null)
      void queryClient.invalidateQueries({ queryKey: ['platform', 'modules'] })
    },
    onError: handleServerError,
  })

  async function request(module: Module, enabled: boolean) {
    const deps = await unwrap(
      api.GET('/api/v1/modules/{name}/dependencies', {
        params: { path: { name: module.name } },
      })
    ).catch((e: ApiError) => {
      handleServerError(e)
      return null
    })
    if (!deps) return
    const affected = enabled
      ? deps.disabled_dependencies
      : deps.enabled_dependents
    if (affected.length) setPending({ module, enabled, affected })
    else toggle.mutate({ name: module.name, enabled, cascade: false })
  }

  const visible = modules
    .filter((m) => m.installed)
    .filter(
      (m) =>
        !search ||
        `${m.display_name} ${m.description}`
          .toLowerCase()
          .includes(search.toLowerCase())
    )
    .sort(
      (a, b) =>
        CATEGORY_ORDER.indexOf(a.category) -
          CATEGORY_ORDER.indexOf(b.category) ||
        a.display_name.localeCompare(b.display_name)
    )

  return (
    <Page title={t('modules.title')} description={t('modules.description')}>
      <Input
        className='h-8 w-72'
        placeholder='Search modules'
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
        {visible.map((m) => (
          <Card
            key={m.name}
            className={m.enabled ? 'gap-2' : 'gap-2 opacity-70'}
          >
            <CardHeader>
              <div className='flex items-start justify-between gap-2'>
                <div className='grid gap-1'>
                  <CardTitle className='flex items-center gap-2 text-sm'>
                    {m.display_name}
                    <Badge variant='outline' className='text-[10px]'>
                      {m.category}
                    </Badge>
                  </CardTitle>
                  <CardDescription className='text-xs'>
                    {m.description}
                  </CardDescription>
                </div>
                {m.core ? (
                  <Lock
                    className='size-4 text-muted-foreground'
                    aria-label='Core module, always on'
                  />
                ) : (
                  <Switch
                    checked={m.enabled}
                    onCheckedChange={(v) => void request(m, v)}
                    aria-label={`${m.display_name} on`}
                  />
                )}
              </div>
            </CardHeader>
            <CardContent className='text-xs text-muted-foreground'>
              {m.depends.length ? (
                <p>Needs: {m.depends.map((d) => names[d] ?? d).join(', ')}</p>
              ) : null}
              {m.dependents.length ? (
                <p>
                  Needed by: {m.dependents.map((d) => names[d] ?? d).join(', ')}
                </p>
              ) : null}
              <p className='font-mono'>
                v{m.version} · {m.api_prefix}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={
          pending?.enabled
            ? `Switch on ${pending.module.display_name}?`
            : `Switch off ${pending?.module.display_name}?`
        }
        desc={
          pending?.enabled
            ? `It needs ${pending.affected.map((d) => names[d] ?? d).join(', ')}, which will be switched on too.`
            : `${pending?.affected.map((d) => names[d] ?? d).join(', ')} need it and will be switched off too. Their data is kept.`
        }
        confirmText={pending?.enabled ? 'Switch on' : 'Switch off'}
        destructive={!pending?.enabled}
        handleConfirm={() =>
          pending &&
          toggle.mutate({
            name: pending.module.name,
            enabled: pending.enabled,
            cascade: true,
          })
        }
      />
    </Page>
  )
}
