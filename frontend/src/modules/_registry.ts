/**
 * Every frontend module. Add yours to the array; nothing else needs editing.
 * Order is the default menu order within a group.
 */
import type { ModuleManifest } from './_types'
import { manifest as asBuilt } from './as_built/manifest'
import { manifest as assetTree } from './asset_tree/manifest'
import { manifest as assets } from './assets/manifest'
import { manifest as audit } from './audit/manifest'
import { manifest as boq } from './boq/manifest'
import { manifest as calibration } from './calibration/manifest'
import { manifest as cde } from './cde/manifest'
import { manifest as changeOfScope } from './change_of_scope/manifest'
import { manifest as changeOrders } from './change_orders/manifest'
import { manifest as claims } from './claims/manifest'
import { manifest as coatings } from './coatings/manifest'
import { manifest as contacts } from './contacts/manifest'
import { manifest as correspondence } from './correspondence/manifest'
import { manifest as cvr } from './cvr/manifest'
import { manifest as dataExchange } from './data_exchange/manifest'
import { manifest as evm } from './evm/manifest'
import { manifest as files } from './files/manifest'
import { manifest as handover } from './handover/manifest'
import { manifest as inspections } from './inspections/manifest'
import { manifest as lobby } from './lobby/manifest'
import { manifest as markups } from './markups/manifest'
import { manifest as materials } from './materials/manifest'
import { manifest as mdr } from './mdr/manifest'
import { manifest as meetings } from './meetings/manifest'
import { manifest as ncr } from './ncr/manifest'
import { manifest as notifications } from './notifications/manifest'
import { manifest as numbering } from './numbering/manifest'
import { manifest as overview } from './overview/manifest'
import { manifest as p6 } from './p6/manifest'
import { manifest as people } from './people/manifest'
import { manifest as planner } from './planner/manifest'
import { manifest as platform } from './platform/manifest'
import { manifest as portal } from './portal/manifest'
import { manifest as procurement } from './procurement/manifest'
import { manifest as projects } from './projects/manifest'
import { manifest as reporting } from './reporting/manifest'
import { manifest as rfi } from './rfi/manifest'
import { manifest as risk } from './risk/manifest'
import { manifest as safety } from './safety/manifest'
import { manifest as scaffolds } from './scaffolds/manifest'
import { manifest as schedule } from './schedule/manifest'
import { manifest as submittals } from './submittals/manifest'
import { manifest as tasks } from './tasks/manifest'
import { manifest as teams } from './team/manifest'
import { manifest as temporaryWorks } from './temporary_works/manifest'
import { manifest as transmittals } from './transmittals/manifest'
import { manifest as welding } from './welding/manifest'
import { manifest as workfaceLog } from './workface_log/manifest'

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
  evm,
  assets,
  markups,
  reporting,
  dataExchange,
  boq,
  planner,
  workfaceLog,
  handover,
  assetTree,
  numbering,
  audit,
  mdr,
  p6,
  changeOfScope,
  claims,
  scaffolds,
  coatings,
  lobby,
  welding,
  materials,
  calibration,
  asBuilt,
  temporaryWorks,
]
