/**
 * Display helpers for as-built records. They decide only which actions a status offers and how a tolerance
 * result is shown; the server decides whether an action is allowed.
 */

export const STATUSES = [
  'draft',
  'surveyed',
  'verified',
  'recorded',
  'superseded',
  'void',
] as const

export const TOLERANCE_RESULTS = [
  'within',
  'out_of_tolerance',
  'not_assessed',
] as const

export const CAPTURE_METHODS = [
  'laser_scan',
  'photogrammetry',
  'total_station',
  'satellite_positioning',
  'tape',
  'drone_lidar',
  'model_extraction',
  'manual',
] as const

export const SOURCE_KINDS = [
  'point_cloud_scan',
  'point_cloud_registration',
  'takeoff_measurement',
  'document',
  'manual',
] as const

export type ActionSet = { survey: boolean; verify: boolean; sign: boolean }

/** Survey for a draft or surveyed record, verify for a surveyed one, sign for a verified one; nothing after. */
export function statusActions(status: string): ActionSet {
  return {
    survey: status === 'draft' || status === 'surveyed',
    verify: status === 'surveyed',
    sign: status === 'verified',
  }
}

export type Held = { update: boolean; review: boolean; approve: boolean }

/** The actions a status offers, narrowed to the permissions the person holds. */
export function allowedActions(status: string, held: Held): ActionSet {
  const base = statusActions(status)
  return {
    survey: base.survey && held.update,
    verify: base.verify && held.review,
    sign: base.sign && held.approve,
  }
}

/** A recorded record is the legal record: no further edit is offered. */
export function isEditable(status: string): boolean {
  return status === 'draft' || status === 'surveyed'
}

export function toleranceTone(result: string | null | undefined): string {
  switch (result) {
    case 'within':
      return 'bg-green-600 text-white'
    case 'out_of_tolerance':
      return 'bg-red-600 text-white'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

export function digestPrefix(
  digest: string | null | undefined,
  length = 12
): string {
  return digest ? `${digest.slice(0, length)}…` : ''
}
