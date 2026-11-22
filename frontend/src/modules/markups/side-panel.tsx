import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Plus, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Comments } from '@/components/records/comments'
import {
  keys,
  useStamps,
  type Calibration,
  type Markup,
  type MarkupSet,
} from './api'
import { formatMeasurement } from './geometry'

const TYPE_LABELS: Record<string, string> = {
  rect: 'Rectangle',
  ellipse: 'Ellipse',
  cloud: 'Cloud',
  arrow: 'Arrow',
  line: 'Line',
  polyline: 'Polyline',
  freehand: 'Freehand',
  text: 'Text',
  callout: 'Callout',
  highlight: 'Highlight',
  stamp: 'Stamp',
  measure_length: 'Length',
  measure_polyline: 'Path length',
  measure_area: 'Area',
}

function Stamps({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const { data: stamps = [] } = useStamps(projectId)
  const [label, setLabel] = useState('')
  const [color, setColor] = useState('#16a34a')
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: keys.stamps(projectId) })
  const add = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/markups/stamps/', {
          body: { project_id: projectId, label, color } as never,
        })
      ),
    onSuccess: () => {
      setLabel('')
      refresh()
    },
    onError: handleServerError,
  })
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/markups/stamps/{stamp_id}', {
          params: { path: { stamp_id: id } },
        })
      ),
    onSuccess: refresh,
    onError: handleServerError,
  })
  return (
    <div className='grid gap-2 text-sm'>
      <p className='text-xs text-muted-foreground'>
        The project&apos;s stamps, for everyone marking up its drawings.
      </p>
      {stamps.map((s) => (
        <div key={s.id} className='flex items-center gap-2'>
          <span
            className='rounded border-2 px-1.5 text-xs font-bold uppercase'
            style={{ borderColor: s.color, color: s.color }}
          >
            {s.label}
          </span>
          <Button
            size='icon'
            variant='ghost'
            className='ms-auto size-7'
            aria-label={`Remove ${s.label}`}
            onClick={() => remove.mutate(s.id)}
          >
            <Trash2 className='size-3.5' />
          </Button>
        </div>
      ))}
      <div className='flex gap-1'>
        <Input
          className='h-8'
          placeholder='New stamp'
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input
          type='color'
          aria-label='Stamp colour'
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className='h-8 w-9'
        />
        <Button
          size='sm'
          disabled={!label.trim() || add.isPending}
          onClick={() => add.mutate()}
        >
          <Plus />
        </Button>
      </div>
    </div>
  )
}

export function SidePanel({
  projectId,
  fileId,
  sets,
  hidden,
  onToggle,
  activeSet,
  onActiveSet,
  calibration,
  page,
  selected,
  editable,
  onEditText,
}: {
  projectId: number | null
  fileId: number
  sets: MarkupSet[]
  hidden: Set<number>
  onToggle: (id: number) => void
  activeSet: number | null
  onActiveSet: (id: number) => void
  calibration: Calibration | null
  page: number
  selected: Markup | null
  editable: boolean
  onEditText: (m: Markup) => void
}) {
  const session = useSession()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [discussing, setDiscussing] = useState<number | null>(null)
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/markups/sets/', { body: { file_id: fileId, name } })
      ),
    onSuccess: (made) => {
      setName('')
      onActiveSet(made.id)
      void queryClient.invalidateQueries({ queryKey: keys.sets(fileId) })
    },
    onError: handleServerError,
  })
  const discussed = discussing ?? activeSet ?? sets[0]?.id ?? null

  return (
    <aside className='flex w-80 shrink-0 flex-col gap-3 overflow-y-auto rounded-md border p-3'>
      <section className='grid gap-1 text-sm'>
        <h3 className='font-medium'>Scale, page {page}</h3>
        {calibration ? (
          <p className='text-muted-foreground'>
            {calibration.real_distance} {calibration.unit} over the picked line
            (1 PDF unit = {(calibration.meters_per_unit * 1000).toFixed(2)} mm)
          </p>
        ) : (
          <p className='text-muted-foreground'>
            Not calibrated. Use the compass tool to pick two points a known
            distance apart.
          </p>
        )}
      </section>
      {selected ? (
        <section className='grid gap-1 rounded-md bg-muted/50 p-2 text-sm'>
          <h3 className='font-medium'>
            {TYPE_LABELS[selected.type] ?? selected.type}
          </h3>
          <p className='text-xs text-muted-foreground'>
            By {selected.author_name ?? 'unknown'}
            {selected.updated_at
              ? ` · ${new Date(selected.updated_at).toLocaleString()}`
              : ''}
          </p>
          {selected.measurement ? (
            <p className='font-mono'>
              {formatMeasurement(selected.measurement as never)}
            </p>
          ) : null}
          {selected.text ? (
            <p className='whitespace-pre-wrap'>{selected.text}</p>
          ) : null}
          {editable &&
          ['text', 'callout', 'stamp', 'cloud'].includes(selected.type) ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => onEditText(selected)}
            >
              Edit text
            </Button>
          ) : null}
        </section>
      ) : null}
      <Tabs defaultValue='sets'>
        <TabsList>
          <TabsTrigger value='sets'>Markup sets</TabsTrigger>
          <TabsTrigger value='comments'>Comments</TabsTrigger>
          {projectId && can(session, 'markups.update') ? (
            <TabsTrigger value='stamps'>Stamps</TabsTrigger>
          ) : null}
        </TabsList>
        <TabsContent value='sets' className='grid gap-1.5'>
          {sets.length === 0 ? (
            <p className='text-sm text-muted-foreground'>No markups yet.</p>
          ) : null}
          {sets.map((s) => (
            <div
              key={s.id}
              className={cn(
                'flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm',
                activeSet === s.id && 'border-primary'
              )}
            >
              <button
                aria-label={hidden.has(s.id) ? 'Show' : 'Hide'}
                onClick={() => onToggle(s.id)}
              >
                {hidden.has(s.id) ? (
                  <EyeOff className='size-4 text-muted-foreground' />
                ) : (
                  <Eye className='size-4' />
                )}
              </button>
              <button
                className='min-w-0 flex-1 text-start'
                onClick={() => {
                  setDiscussing(s.id)
                  if (
                    s.author_id === session.id ||
                    can(session, 'markups.update')
                  )
                    onActiveSet(s.id)
                }}
              >
                <span className='block truncate font-medium'>{s.name}</span>
                <span className='block text-xs text-muted-foreground'>
                  {s.author_name ?? 'unknown'} · {s.markup_count} markups · rev{' '}
                  {s.revision}
                </span>
              </button>
            </div>
          ))}
          {editable ? (
            <div className='flex gap-1 pt-1'>
              <Input
                className='h-8'
                placeholder='New set, e.g. Structural review'
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <Button
                size='sm'
                disabled={!name.trim() || create.isPending}
                onClick={() => create.mutate()}
              >
                <Plus />
              </Button>
            </div>
          ) : null}
          {activeSet ? (
            <p className='text-xs text-muted-foreground'>
              New markups go into the highlighted set.
            </p>
          ) : null}
        </TabsContent>
        <TabsContent value='comments'>
          {projectId && discussed ? (
            <>
              <p className='pb-2 text-xs text-muted-foreground'>
                On {sets.find((s) => s.id === discussed)?.name ?? 'this set'}
              </p>
              <Comments
                projectId={projectId}
                entityType='markup_set'
                entityId={discussed}
              />
            </>
          ) : (
            <p className='text-sm text-muted-foreground'>
              Comments belong to a markup set; add a markup first.
            </p>
          )}
        </TabsContent>
        {projectId ? (
          <TabsContent value='stamps'>
            <Stamps projectId={projectId} />
          </TabsContent>
        ) : null}
      </Tabs>
    </aside>
  )
}
