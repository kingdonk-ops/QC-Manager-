/**
 * Every frontend module. Add yours to the array; nothing else needs editing.
 * Order is the default menu order within a group.
 */
import type { ModuleManifest } from './_types'
import { manifest as contacts } from './contacts/manifest'
import { manifest as correspondence } from './correspondence/manifest'
import { manifest as cde } from './cde/manifest'
import { manifest as changeOrders } from './change_orders/manifest'
import { manifest as cvr } from './cvr/manifest'
import { manifest as files } from './files/manifest'
import { manifest as meetings } from './meetings/manifest'
import { manifest as inspections } from './inspections/manifest'
import { manifest as ncr } from './ncr/manifest'
import { manifest as notifications } from './notifications/manifest'
import { manifest as overview } from './overview/manifest'
import { manifest as people } from './people/manifest'
import { manifest as platform } from './platform/manifest'
import { manifest as portal } from './portal/manifest'
import { manifest as procurement } from './procurement/manifest'
import { manifest as projects } from './projects/manifest'
import { manifest as tasks } from './tasks/manifest'
import { manifest as rfi } from './rfi/manifest'
import { manifest as submittals } from './submittals/manifest'
import { manifest as safety } from './safety/manifest'
import { manifest as risk } from './risk/manifest'
import { manifest as schedule } from './schedule/manifest'
import { manifest as teams } from './team/manifest'
import { manifest as transmittals } from './transmittals/manifest'

export const MODULE_REGISTRY: ModuleManifest[] = [
  overview,
  projects,
  cvr,
  files,
  people,
  teams,
  portal,
  platform,
  notifications,
  tasks,
  meetings,
  contacts,
  rfi,
  correspondence,
  transmittals,
  submittals,
  cde,
  inspections,
  ncr,
  safety,
  risk,
  changeOrders,
  procurement,
  schedule,
]
