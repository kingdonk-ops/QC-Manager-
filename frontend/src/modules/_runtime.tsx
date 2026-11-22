/**
 * Turning the registry into routes and menus for the signed-in account.
 */
import { createContext, useContext, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import { useProjectStore } from '@/stores/project-store'
import { can, useSession, type Whoami } from '@/lib/session'
import { MODULE_REGISTRY } from './_registry'
import type { ModuleManifest, ModuleNavItem, ModuleRoute } from './_types'

type BackendModule = { name: string; enabled: boolean }

/** Backend modules this deployment runs. A frontend module whose backend is off is hidden. */
function useEnabledBackendModules() {
  const projectId = useProjectStore((s) => s.projectId)
  return useQuery({
    queryKey: ['platform', 'modules', projectId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/modules', {
          params: { query: { project_id: projectId ?? undefined } },
        })
      ) as Promise<BackendModule[]>,
    staleTime: 5 * 60_000,
  })
}

function backendOf(module: ModuleManifest) {
  return module.backend === undefined ? module.id : module.backend
}

function moduleIsOn(
  module: ModuleManifest,
  backend: BackendModule[] | undefined
) {
  const name = backendOf(module)
  if (name === null || backend === undefined) return true
  const found = backend.find((m) => m.name === name)
  return found ? found.enabled : false
}

function allowed(
  session: Whoami,
  item: Pick<ModuleRoute, 'permission' | 'accountTypes'>
) {
  if (item.accountTypes && !item.accountTypes.includes(session.account_type))
    return false
  return can(session, item.permission)
}

export function useActiveModules() {
  const { data: backend } = useEnabledBackendModules()
  return useMemo(
    () => MODULE_REGISTRY.filter((m) => moduleIsOn(m, backend)),
    [backend]
  )
}

export const GROUP_ORDER = [
  'general',
  'estimating',
  'planning',
  'cost_control',
  'commercial',
  'project_management',
  'quality_safety',
  'documents',
  'procurement',
  'assets',
  'reporting',
  'admin',
]

/** Simple or Advanced, from the user's preferences; Advanced shows `advancedOnly` items. */
export function useInterfaceMode(): 'simple' | 'advanced' {
  const { data } = useQuery({
    queryKey: ['platform', 'preferences'],
    queryFn: () =>
      unwrap(api.GET('/api/v1/platform/me/preferences')) as Promise<
        Record<string, Record<string, unknown>>
      >,
    staleTime: 5 * 60_000,
  })
  return data?.interface?.mode === 'simple' ? 'simple' : 'advanced'
}

export type NavGroupModel = { group: string; items: ModuleNavItem[] }

export function useModuleNav(): NavGroupModel[] {
  const session = useSession()
  const modules = useActiveModules()
  const mode = useInterfaceMode()
  return useMemo(() => {
    const groups = new Map<string, ModuleNavItem[]>()
    for (const module of modules)
      for (const item of module.navItems ?? []) {
        if (!allowed(session, item)) continue
        if (item.advancedOnly && mode === 'simple') continue
        groups.set(item.group, [...(groups.get(item.group) ?? []), item])
      }
    const rank = (g: string) => {
      const i = GROUP_ORDER.indexOf(g)
      return i === -1 ? GROUP_ORDER.length - 1.5 : i
    }
    return [...groups.entries()]
      .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
      .map(([group, items]) => ({
        group,
        items: items.sort((a, b) => (a.order ?? 100) - (b.order ?? 100)),
      }))
  }, [modules, session, mode])
}

function match(pattern: string, path: string): Record<string, string> | null {
  const want = pattern.split('/').filter(Boolean)
  const got = path.split('/').filter(Boolean)
  if (want.length !== got.length) return null
  const params: Record<string, string> = {}
  for (let i = 0; i < want.length; i++) {
    if (want[i].startsWith(':'))
      params[want[i].slice(1)] = decodeURIComponent(got[i])
    else if (want[i] !== got[i]) return null
  }
  return params
}

export type ResolvedRoute =
  | { kind: 'found'; route: ModuleRoute; params: Record<string, string> }
  | { kind: 'forbidden' }
  | { kind: 'missing' }

function resolve(
  modules: ModuleManifest[],
  session: Whoami,
  pathname: string
): ResolvedRoute {
  for (const module of modules)
    for (const route of module.routes) {
      const params = match(route.path, pathname)
      if (params === null) continue
      if (!allowed(session, route)) return { kind: 'forbidden' }
      return { kind: 'found', route, params }
    }
  return { kind: 'missing' }
}

export function useResolvedRoute(pathname: string): ResolvedRoute {
  const session = useSession()
  const modules = useActiveModules()
  return useMemo(
    () => resolve(modules, session, pathname),
    [modules, pathname, session]
  )
}

export const ModuleParamsContext = createContext<Record<string, string>>({})

/** The `:params` of the module route being shown. */
export function useModuleParams() {
  return useContext(ModuleParamsContext)
}
