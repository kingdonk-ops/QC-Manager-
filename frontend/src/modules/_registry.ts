/**
 * Every frontend module. Add yours to the array; nothing else needs editing.
 * Order is the default menu order within a group.
 */
import type { ModuleManifest } from './_types'
import { manifest as cvr } from './cvr/manifest'
import { manifest as overview } from './overview/manifest'
import { manifest as people } from './people/manifest'
import { manifest as portal } from './portal/manifest'
import { manifest as projects } from './projects/manifest'
import { manifest as teams } from './team/manifest'

export const MODULE_REGISTRY: ModuleManifest[] = [
  overview,
  projects,
  cvr,
  people,
  teams,
  portal,
]
