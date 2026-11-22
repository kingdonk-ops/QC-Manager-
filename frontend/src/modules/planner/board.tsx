import { useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  type Assignment,
  plannerApi,
  useBoard,
  usePlannerMutation,
} from './api'
import {
  byCell,
  cellKey,
  dayHeading,
  doubleBooked,
  readinessTone,
} from './board-lib'

const CREW_DRAG = 'application/x-planner-crew'

/** Work anchors × days of the plan's window. Drag a crew onto a cell (or tap a crew, then cells). */
export function PlanBoard({
  planId,
  onOpenPack,
}: {
  planId: number
  onOpenPack: (id: number) => void
}) {
  const session = useSession()
  const editable = can(session, 'planner.assign')
  const { data: board, isLoading } = useBoard(planId)
  const [armed, setArmed] = useState<number | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const assign = usePlannerMutation(plannerApi.assign)
  const unassign = usePlannerMutation(plannerApi.unassign)

  const cells = useMemo(() => byCell(board?.assignments ?? []), [board])
  const doubled = useMemo(() => doubleBooked(board?.assignments ?? []), [board])
  const days = board?.days ?? []

  if (isLoading || !board)
    return <p className='text-sm text-muted-foreground'>Loading board…</p>
  if (board.rows.length === 0)
    return (
      <p className='text-sm text-muted-foreground'>
        No work anchors yet. Add a work pack with work anchors from the asset
        tree, then put crews on them here.
      </p>
    )

  const put = (crewId: number, anchorId: number, day: string) =>
    assign.mutate(
      { plan_id: planId, crew_id: crewId, anchor_id: anchorId, work_date: day },
      {
        onSuccess: (made) =>
          made.warnings?.length
            ? toast.warning(made.warnings.join(' '))
            : undefined,
      }
    )

  return (
    <div className='grid gap-3'>
      {editable ? (
        <div className='flex flex-wrap items-center gap-2'>
          <span className='text-xs text-muted-foreground'>
            Crews (drag onto a day, or tap one and then the cells):
          </span>
          {board.crews.map((c) => (
            <button
              type='button'
              key={c.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(CREW_DRAG, String(c.id))
                e.dataTransfer.effectAllowed = 'copy'
              }}
              onClick={() => setArmed(armed === c.id ? null : c.id)}
              className={cn(
                'cursor-grab rounded-full border px-2.5 py-0.5 text-xs font-medium active:cursor-grabbing',
                armed === c.id
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'bg-background hover:bg-accent'
              )}
              title={`${c.name} · ${c.headcount} people`}
            >
              {c.code}
            </button>
          ))}
          {board.crews.length === 0 ? (
            <span className='text-xs text-muted-foreground'>
              Add crews on the Crews tab.
            </span>
          ) : null}
        </div>
      ) : null}
      <div className='overflow-x-auto rounded-md border'>
        <table className='w-full border-collapse text-xs'>
          <thead>
            <tr className='bg-muted/50'>
              <th className='sticky left-0 z-10 min-w-56 border-b bg-muted px-2 py-1.5 text-left font-semibold'>
                Work anchor
              </th>
              {days.map((d) => {
                const h = dayHeading(d)
                return (
                  <th
                    key={d}
                    className={cn(
                      'min-w-20 border-b border-l px-1 py-1 text-center font-medium',
                      h.weekend && 'bg-muted'
                    )}
                  >
                    <div className='text-muted-foreground'>{h.weekday}</div>
                    <div>{h.day}</div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {board.rows.map((row) => (
              <tr key={row.anchor_id} className='align-top'>
                <th className='sticky left-0 z-10 border-b bg-background px-2 py-1.5 text-left font-normal'>
                  <div className='flex items-center gap-1.5'>
                    <span className='font-medium'>{row.anchor_code}</span>
                    <Badge
                      variant='outline'
                      className={cn(
                        'border-transparent px-1.5 py-0 text-[10px]',
                        readinessTone(row.readiness)
                      )}
                    >
                      {row.readiness}
                    </Badge>
                  </div>
                  <div className='truncate text-muted-foreground'>
                    {row.pack_codes.map((code, i) => (
                      <button
                        type='button'
                        key={code}
                        className='me-1 text-primary hover:underline'
                        onClick={() => onOpenPack(row.pack_ids[i])}
                      >
                        {code}
                      </button>
                    ))}
                    {Number(row.planned_hours) > 0
                      ? `${Number(row.planned_hours)} h`
                      : null}
                    {row.planned_qty != null
                      ? ` · ${Number(row.planned_qty)} ${row.uom ?? ''}`
                      : null}
                  </div>
                </th>
                {days.map((d) => {
                  const key = cellKey(row.anchor_id, d)
                  const here = cells.get(key) ?? []
                  return (
                    <td
                      key={d}
                      data-testid={`cell-${key}`}
                      className={cn(
                        'h-12 border-b border-l p-0.5',
                        over === key && 'bg-primary/10',
                        armed && editable && 'cursor-copy hover:bg-accent'
                      )}
                      onDragOver={(e) => {
                        if (!editable) return
                        e.preventDefault()
                        setOver(key)
                      }}
                      onDragLeave={() => setOver(null)}
                      onDrop={(e) => {
                        e.preventDefault()
                        setOver(null)
                        const crew = Number(e.dataTransfer.getData(CREW_DRAG))
                        if (crew) put(crew, row.anchor_id, d)
                      }}
                      onClick={() => armed && put(armed, row.anchor_id, d)}
                    >
                      <div className='flex flex-wrap gap-0.5'>
                        {here.map((a) => (
                          <CrewChip
                            key={a.id}
                            a={a}
                            warn={doubled.has(`${a.crew_id}|${a.work_date}`)}
                            onRemove={
                              editable ? () => unassign.mutate(a.id) : undefined
                            }
                          />
                        ))}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CrewChip({
  a,
  warn,
  onRemove,
}: {
  a: Assignment
  warn: boolean
  onRemove?: () => void
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] font-medium',
        warn
          ? 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
          : 'bg-blue-500/15 text-blue-700 dark:text-blue-400'
      )}
      title={
        warn
          ? `${a.crew_name}: on more than one work anchor this day`
          : (a.crew_name ?? '')
      }
    >
      {a.crew_code}
      {a.planned_hours ? ` ${Number(a.planned_hours)}h` : ''}
      {onRemove ? (
        <button
          type='button'
          aria-label={`Remove ${a.crew_code}`}
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
        >
          <X className='size-3' />
        </button>
      ) : null}
    </span>
  )
}
