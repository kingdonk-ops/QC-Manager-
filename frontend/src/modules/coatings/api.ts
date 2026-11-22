import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import type { components } from '@/api/schema'
import { handleServerError } from '@/lib/handle-server-error'

type S = components['schemas']
export type CoatingSystem = S['SystemRead']
export type SystemCreate = S['SystemCreate']
export type Job = S['JobRead']
export type JobDetail = S['JobDetail']
export type Stage = S['StageRead']
export type EnvironmentCreate = S['EnvironmentCreate']
export type DftCreate = S['DftCreate']

const keys = {
  all: ['coatings'] as const,
  systems: (projectId: number) => ['coatings', projectId, 'systems'] as const,
  jobs: (projectId: number, status: string) =>
    ['coatings', projectId, 'jobs', status] as const,
  job: (id: number) => ['coatings', 'job', id] as const,
}

export function useSystems(projectId: number) {
  return useQuery({
    queryKey: keys.systems(projectId),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/coatings/systems/', {
            params: { query: { project_id: projectId } },
          })
        )
      ).data,
  })
}

export function useJobs(projectId: number, status: string) {
  return useQuery({
    queryKey: keys.jobs(projectId, status),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/coatings/jobs/', {
            params: {
              query: { project_id: projectId, status: status || undefined },
            },
          })
        )
      ).data,
  })
}

export function useJob(id: number | null) {
  return useQuery({
    queryKey: keys.job(id ?? 0),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/coatings/jobs/{job_id}', {
          params: { path: { job_id: id ?? 0 } },
        })
      ),
  })
}

function useWrite<T, R>(call: (v: T) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: call,
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.all }),
    onError: handleServerError,
  })
}

export function useCreateSystem() {
  return useWrite((body: SystemCreate) =>
    unwrap(api.POST('/api/v1/coatings/systems/', { body }))
  )
}

export function useCreateJob() {
  return useWrite((body: S['JobCreate']) =>
    unwrap(api.POST('/api/v1/coatings/jobs/', { body }))
  )
}

const at = (id: number) => ({ params: { path: { job_id: id } } })

export function useAddEnvironment(jobId: number) {
  return useWrite((body: EnvironmentCreate) =>
    unwrap(
      api.POST('/api/v1/coatings/jobs/{job_id}/environment', {
        ...at(jobId),
        body,
      })
    )
  )
}

export function useAddDft(jobId: number) {
  return useWrite((body: DftCreate) =>
    unwrap(
      api.POST('/api/v1/coatings/jobs/{job_id}/dft', { ...at(jobId), body })
    )
  )
}

export function useUpdateStage(jobId: number) {
  return useWrite(
    ({ stageId, body }: { stageId: number; body: S['StageUpdate'] }) =>
      unwrap(
        api.PATCH('/api/v1/coatings/jobs/{job_id}/stages/{stage_id}', {
          params: { path: { job_id: jobId, stage_id: stageId } },
          body,
        })
      )
  )
}

export function useRelease(jobId: number) {
  return useWrite(
    ({
      stageId,
      result,
      note,
    }: {
      stageId: number
      result: 'passed' | 'failed'
      note?: string
    }) =>
      unwrap(
        api.POST('/api/v1/coatings/jobs/{job_id}/stages/{stage_id}/release', {
          params: { path: { job_id: jobId, stage_id: stageId } },
          body: { result, note: note || null },
        })
      )
  )
}
