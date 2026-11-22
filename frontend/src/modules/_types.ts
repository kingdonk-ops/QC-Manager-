/**
 * The contract every frontend module declares in `src/modules/<id>/manifest.ts`.
 *
 * Register the manifest in `_registry.ts`; its routes and menu entries then appear
 * on their own. Keep a module's code inside its folder, and talk to the backend
 * through `@/api/client` (typed from the backend's OpenAPI document).
 */
import type { ComponentType, LazyExoticComponent } from 'react'

export type AccountType = 'staff' | 'external'

export type ModuleRoute = {
  /** Path pattern, e.g. `/projects` or `/projects/:projectId`. */
  path: string
  component: LazyExoticComponent<ComponentType> | ComponentType
  /** Hide the page from accounts without this permission. */
  permission?: string
  /** Hide the page from staff or from external (portal) accounts. Default: both see it. */
  accountTypes?: AccountType[]
}

export type ModuleNavItem = {
  /** i18n key for the label. */
  labelKey: string
  to: string
  icon?: ComponentType<{ className?: string }>
  /**
   * A menu group. The shell orders these: `general`, `estimating`, `planning`, `cost_control`,
   * `commercial`, `project_management`, `quality_safety`, `documents`, `procurement`, `assets`,
   * `reporting`, `admin`. Any other value makes a new group named `nav.group.<value>`, after them.
   */
  group: string
  order?: number
  permission?: string
  accountTypes?: AccountType[]
  /** Hidden in Simple mode (Settings → Display). */
  advancedOnly?: boolean
}

export type ModuleManifest = {
  /** Matches the backend module's `name` when there is one; the menu hides modules the backend reports disabled. */
  id: string
  name: string
  description?: string
  version: string
  /** A backend module name to follow, when it differs from `id`, or `null` for a frontend-only module. */
  backend?: string | null
  depends?: string[]
  routes: ModuleRoute[]
  navItems?: ModuleNavItem[]
  /** `{ en: { 'key': 'English text' } }`, merged into i18next. */
  messages?: Record<string, Record<string, string>>
}
