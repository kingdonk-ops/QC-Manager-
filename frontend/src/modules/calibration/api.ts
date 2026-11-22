import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type Equipment = S['EquipmentRead']
export type EquipmentCreate = S['EquipmentCreate']
export type EquipmentUpdate = S['EquipmentUpdate']
export type Certificate = S['CalibrationCertificateRead']
export type CertificateCreate = S['CalibrationCertificateCreate']

export const EQUIPMENT_TYPES = [
  'pressure_gauge',
  'dft_meter',
  'thermometer',
  'torque_wrench',
  'tensioning_tool',
  'ut_thickness_gauge',
  'pmi_analyser',
  'surface_profile_gauge',
  'holiday_detector',
  'hygrometer',
  'welding_gauge',
  'multimeter',
  'other',
] as const
export const STATUSES = [
  'in_service',
  'due',
  'overdue',
  'sent_for_calibration',
  'quarantined',
  'out_of_service',
] as const
/** Where the stored status may go next; mirrors the backend's flow. */
export const NEXT: Record<string, string[]> = {
  in_service: ['sent_for_calibration', 'quarantined', 'out_of_service'],
  sent_for_calibration: ['in_service', 'quarantined', 'out_of_service'],
  quarantined: ['in_service', 'sent_for_calibration', 'out_of_service'],
  out_of_service: ['in_service', 'sent_for_calibration'],
}

/** Row colour of the register: red overdue, amber due soon, grey not in use. */
export function dueTone(status?: string | null) {
  if (status === 'overdue') return 'bg-red-500/10'
  if (status === 'due') return 'bg-amber-500/10'
  if (status === 'quarantined' || status === 'out_of_service')
    return 'text-muted-foreground'
  return ''
}

const keys = {
  all: (projectId: number) => ['calibration', projectId] as const,
  list: (projectId: number, status?: string) =>
    ['calibration', projectId, 'list', status ?? ''] as const,
  summary: (projectId: number) =>
    ['calibration', projectId, 'summary'] as const,
  certs: (id: number) => ['calibration', 'certs', id] as const,
  history: (id: number) => ['calibration', 'history', id] as const,
}

export function useEquipment(projectId: number, status?: string) {
  return useQuery({
    queryKey: keys.list(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/calibration/equipment/', {
            params: {
              query: {
                project_id: projectId,
                items_per_page: 100,
                status: (status || undefined) as never,
              },
            },
          })
        )
      ).data,
  })
}

export function useSummary(projectId: number) {
  return useQuery({
    queryKey: keys.summary(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/calibration/summary', {
          params: { query: { project_id: projectId } },
        })
      ),
  })
}

export function useCertificates(id: number | undefined) {
  return useQuery({
    queryKey: keys.certs(id ?? 0),
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/calibration/equipment/{equipment_id}/certificates', {
          params: { path: { equipment_id: id! } },
        })
      ),
  })
}

export function useHistory(id: number | undefined) {
  return useQuery({
    queryKey: keys.history(id ?? 0),
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/calibration/equipment/{equipment_id}/history', {
          params: { path: { equipment_id: id! } },
        })
      ),
  })
}

function useRefresh(projectId: number) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: keys.all(projectId) })
    void queryClient.invalidateQueries({ queryKey: ['calibration', 'certs'] })
    void queryClient.invalidateQueries({ queryKey: ['calibration', 'history'] })
  }
}

export function useSaveEquipment(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: EquipmentUpdate }) =>
      id
        ? unwrap(
            api.PATCH('/api/v1/calibration/equipment/{equipment_id}', {
              params: { path: { equipment_id: id } },
              body,
            })
          )
        : unwrap(
            api.POST('/api/v1/calibration/equipment/', {
              body: { ...body, project_id: projectId } as EquipmentCreate,
            })
          ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useEquipmentStatus(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({
      id,
      status,
      note,
    }: {
      id: number
      status: string
      note?: string
    }) =>
      unwrap(
        api.POST('/api/v1/calibration/equipment/{equipment_id}/status', {
          params: { path: { equipment_id: id } },
          body: { status: status as never, note: note || null },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export function useAddCertificate(projectId: number) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: CertificateCreate }) =>
      unwrap(
        api.POST('/api/v1/calibration/equipment/{equipment_id}/certificates', {
          params: { path: { equipment_id: id } },
          body,
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
}

export const exportUrl = (projectId: number) =>
  `/api/v1/calibration/export?project_id=${projectId}&format=xlsx`
