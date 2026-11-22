import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, unwrap } from '@/api/client'
import { useProjectStore } from '@/stores/project-store'
import { handleServerError } from '@/lib/handle-server-error'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { projectKeys, type Project } from './api'
import { CLASSIFICATIONS } from './constants'

/** Creates a project; picking a region fills in its currency and classification standard. */
export function ProjectForm({
  formId,
  onCreated,
}: {
  formId: string
  onCreated: (p: Project) => void
}) {
  const queryClient = useQueryClient()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const { data: regions = [] } = useQuery({
    queryKey: ['projects', 'regions'],
    queryFn: () => unwrap(api.GET('/api/v1/projects/regions')),
    staleTime: Infinity,
  })
  const [region, setRegion] = useState('AU')
  const [classification, setClassification] = useState('')
  const regionInfo = regions.find((r) => r.code === region)

  const create = useMutation({
    mutationFn: (body: Record<string, string>) =>
      unwrap(api.POST('/api/v1/projects/', { body: body as never })),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: projectKeys.all })
      setProjectId(project.id)
      onCreated(project)
    },
    onError: handleServerError,
  })

  return (
    <form
      id={formId}
      className='grid grid-cols-2 gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        const body: Record<string, string> = {}
        for (const [k, v] of new FormData(e.currentTarget).entries())
          if (String(v).trim()) body[k] = String(v).trim()
        body.region = region
        if (classification) body.classification_standard = classification
        create.mutate(body)
      }}
    >
      <div className='col-span-2 grid gap-1.5'>
        <Label htmlFor='name'>Project name</Label>
        <Input
          id='name'
          name='name'
          placeholder='e.g. LNG Train 3 Insulation'
          required
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='code'>Code</Label>
        <Input
          id='code'
          name='code'
          placeholder='P-24017'
          required
          pattern='[A-Za-z0-9._-]+'
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='client_name'>Client</Label>
        <Input id='client_name' name='client_name' />
      </div>
      <div className='col-span-2 grid gap-1.5'>
        <Label htmlFor='description'>Description</Label>
        <Textarea
          id='description'
          name='description'
          rows={2}
          placeholder='Brief scope description'
        />
      </div>
      <div className='grid gap-1.5'>
        <Label>Region</Label>
        <Select value={region} onValueChange={setRegion}>
          <SelectTrigger className='w-full'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {regions.map((r) => (
              <SelectItem key={r.code} value={r.code}>
                {r.name} · {r.currency}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label>Classification standard</Label>
        <Select
          value={classification || regionInfo?.classification || ''}
          onValueChange={setClassification}
        >
          <SelectTrigger className='w-full'>
            <SelectValue placeholder='From the region' />
          </SelectTrigger>
          <SelectContent>
            {CLASSIFICATIONS.map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='location'>Location</Label>
        <Input id='location' name='location' />
      </div>
      <div className='grid grid-cols-2 gap-2'>
        <div className='grid gap-1.5'>
          <Label htmlFor='start_date'>Start</Label>
          <Input id='start_date' name='start_date' type='date' />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='end_date'>Finish</Label>
          <Input id='end_date' name='end_date' type='date' />
        </div>
      </div>
    </form>
  )
}
