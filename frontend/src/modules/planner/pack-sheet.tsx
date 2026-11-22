import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileDown, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NodeBrowser } from '@/components/asset-node-picker'
import { nodeLabel } from '@/components/asset-nodes'
import { NativeSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type LineIn,
  type Pack,
  PACK_NEXT,
  PREREQ_KINDS,
  plannerApi,
  usePack,
  usePlannerMutation,
} from './api'
import { readinessTone } from './board-lib'

type DraftLine = LineIn & { label: string }

function toDraft(pack: Pack): DraftLine[] {
  return (pack.lines ?? []).map((l) => ({
    node_id: l.anchor_id,
    label: l.anchor_path ?? l.anchor_code ?? `#${l.anchor_id}`,
    activity_code: l.activity_code,
    description: l.description,
    planned_qty: l.planned_qty == null ? null : String(l.planned_qty),
    uom: l.uom,
    planned_hours: l.planned_hours == null ? null : String(l.planned_hours),
  }))
}

export function PackSheet({
  id,
  projectId,
  onClose,
}: {
  id: number | null
  projectId: number
  onClose: () => void
}) {
  const { data: pack } = usePack(id)
  return (
    <RecordSheet
      open={id !== null}
      onClose={onClose}
      wide
      title={pack ? `${pack.code} ${pack.title}` : 'Work pack'}
      subtitle={pack?.crew_name ?? undefined}
      badges={
        pack ? (
          <>
            <StatusBadge status={pack.status} />
            <Badge
              variant='outline'
              className={cn(
                'border-transparent',
                readinessTone(pack.readiness)
              )}
            >
              {pack.readiness}
            </Badge>
          </>
        ) : null
      }
      record={
        pack
          ? { projectId, entityType: 'work_pack', entityId: pack.id }
          : undefined
      }
      tabs={pack ? { History: <History id={pack.id} /> } : undefined}
    >
      {pack ? (
        <PackDetail key={pack.id} pack={pack} projectId={projectId} />
      ) : null}
    </RecordSheet>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useQuery({
    queryKey: ['planner', 'pack-history', id],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/planner/packs/{pack_id}/history', {
          params: { path: { pack_id: id } },
        })
      ) as Promise<{ to_status: string; changed_at: string; note?: string }[]>,
  })
  return (
    <ul className='grid gap-1 text-sm'>
      {data.map((h, i) => (
        <li key={i}>
          <StatusBadge status={h.to_status} />{' '}
          <span className='text-muted-foreground'>
            {new Date(h.changed_at).toLocaleString()}
          </span>{' '}
          {h.note}
        </li>
      ))}
    </ul>
  )
}

function PackDetail({ pack, projectId }: { pack: Pack; projectId: number }) {
  const session = useSession()
  const editable = can(session, 'planner.update')
  const [lines, setLines] = useState<DraftLine[]>(() => toDraft(pack))
  const [dirty, setDirty] = useState(false)
  const [picking, setPicking] = useState(false)
  const [prereq, setPrereq] = useState({ kind: 'materials', description: '' })
  const save = usePlannerMutation(plannerApi.setLines)
  const move = usePlannerMutation(plannerApi.transitionPack)
  const addPrereq = usePlannerMutation(plannerApi.addPrerequisite)
  const setPrereqStatus = usePlannerMutation(plannerApi.setPrerequisite)

  const edit = (i: number, patch: Partial<DraftLine>) => {
    setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
    setDirty(true)
  }
  const findings = pack.findings ?? []
  const blockers = findings.filter((f) => f.severity === 'blocker')

  return (
    <div className='grid gap-4 text-sm'>
      <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
        <Info label='Start' value={pack.planned_start} />
        <Info label='Finish' value={pack.planned_end} />
        <Info label='Supervisor' value={pack.supervisor_name} />
        <Info label='Hours' value={Number(pack.planned_hours)} />
      </div>

      {findings.length ? (
        <section>
          <h4 className='mb-1 font-semibold'>Readiness</h4>
          <ul className='grid gap-1'>
            {findings.map((f, i) => (
              <li
                key={i}
                className={cn(
                  'rounded px-2 py-1 text-xs',
                  f.severity === 'blocker'
                    ? 'bg-red-500/10 text-red-700 dark:text-red-400'
                    : 'bg-amber-500/10 text-amber-700 dark:text-amber-400'
                )}
              >
                <span className='font-medium'>{f.source}:</span> {f.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className='grid gap-2'>
        <div className='flex items-center justify-between'>
          <h4 className='font-semibold'>Scope (work anchors)</h4>
          {editable ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setPicking(!picking)}
            >
              {picking ? 'Done adding' : 'Add from asset tree'}
            </Button>
          ) : null}
        </div>
        {picking ? (
          <NodeBrowser
            projectId={projectId}
            picked={lines.map((l) => l.node_id ?? 0)}
            onPick={(n) => {
              if (lines.some((l) => l.node_id === n.id)) return
              setLines([
                ...lines,
                {
                  node_id: n.id,
                  label: n.display_path || nodeLabel(n),
                  uom: n.uom,
                  planned_qty: null,
                  planned_hours: null,
                },
              ])
              setDirty(true)
            }}
          />
        ) : null}
        <div className='overflow-x-auto'>
          <table className='w-full text-xs'>
            <thead className='text-muted-foreground'>
              <tr>
                <th className='text-left font-medium'>Work anchor</th>
                <th className='w-20 text-left font-medium'>Activity</th>
                <th className='w-20 text-right font-medium'>Qty</th>
                <th className='w-16 text-left font-medium'>UoM</th>
                <th className='w-20 text-right font-medium'>Hours</th>
                <th className='w-8' />
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={`${l.node_id}-${i}`}>
                  <td className='py-0.5 pe-1'>{l.label}</td>
                  <td className='pe-1'>
                    <Input
                      className='h-7 text-xs'
                      aria-label='Activity'
                      disabled={!editable}
                      value={l.activity_code ?? ''}
                      onChange={(e) =>
                        edit(i, { activity_code: e.target.value || null })
                      }
                    />
                  </td>
                  <td className='pe-1'>
                    <Input
                      className='h-7 text-right text-xs'
                      inputMode='decimal'
                      aria-label='Planned quantity'
                      disabled={!editable}
                      value={(l.planned_qty as string | null) ?? ''}
                      onChange={(e) =>
                        edit(i, { planned_qty: e.target.value || null })
                      }
                    />
                  </td>
                  <td className='pe-1'>
                    <Input
                      className='h-7 text-xs'
                      aria-label='Unit'
                      disabled={!editable}
                      value={l.uom ?? ''}
                      onChange={(e) => edit(i, { uom: e.target.value || null })}
                    />
                  </td>
                  <td className='pe-1'>
                    <Input
                      className='h-7 text-right text-xs'
                      inputMode='decimal'
                      aria-label='Planned hours'
                      disabled={!editable}
                      value={(l.planned_hours as string | null) ?? ''}
                      onChange={(e) =>
                        edit(i, { planned_hours: e.target.value || null })
                      }
                    />
                  </td>
                  <td>
                    {editable ? (
                      <Button
                        size='icon'
                        variant='ghost'
                        className='size-7'
                        aria-label='Remove line'
                        onClick={() => {
                          setLines(lines.filter((_, j) => j !== i))
                          setDirty(true)
                        }}
                      >
                        <Trash2 />
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {dirty ? (
          <div>
            <Button
              size='sm'
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  {
                    id: pack.id,
                    lines: lines.map(({ label: _label, ...l }) => l),
                  },
                  { onSuccess: () => setDirty(false) }
                )
              }
            >
              Save scope
            </Button>
          </div>
        ) : null}
      </section>

      <section className='grid gap-2'>
        <h4 className='font-semibold'>Prerequisites</h4>
        <ul className='grid gap-1'>
          {(pack.prerequisites ?? []).map((p) => (
            <li key={p.id} className='flex items-center gap-2'>
              <StatusBadge
                status={p.status === 'cleared' ? 'done' : p.status}
              />
              <span className='text-xs text-muted-foreground'>{p.kind}</span>
              <span className='flex-1'>{p.description}</span>
              {editable && p.status === 'pending' ? (
                <Button
                  size='sm'
                  variant='outline'
                  className='h-7'
                  onClick={() =>
                    setPrereqStatus.mutate({ id: p.id, status: 'cleared' })
                  }
                >
                  Clear
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        {editable ? (
          <form
            className='flex flex-wrap gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              addPrereq.mutate(
                { packId: pack.id, ...prereq },
                { onSuccess: () => setPrereq({ ...prereq, description: '' }) }
              )
            }}
          >
            <NativeSelect
              className='h-8 w-32'
              aria-label='Prerequisite kind'
              values={PREREQ_KINDS}
              value={prereq.kind}
              onChange={(e) => setPrereq({ ...prereq, kind: e.target.value })}
            />
            <Input
              className='h-8 min-w-40 flex-1'
              placeholder='e.g. Scaffold green-tagged'
              aria-label='Prerequisite'
              required
              value={prereq.description}
              onChange={(e) =>
                setPrereq({ ...prereq, description: e.target.value })
              }
            />
            <Button size='sm' type='submit' disabled={addPrereq.isPending}>
              Add
            </Button>
          </form>
        ) : null}
      </section>

      <div className='flex flex-wrap gap-2 border-t pt-3'>
        {can(session, 'planner.transition')
          ? (PACK_NEXT[pack.status] ?? []).map((s) => (
              <Button
                key={s}
                size='sm'
                variant={s === 'ready' ? 'default' : 'outline'}
                onClick={() => {
                  if (
                    s === 'ready' &&
                    blockers.length &&
                    !window.confirm(
                      `Not ready: ${blockers.map((b) => b.message).join('; ')}. Mark ready anyway?`
                    )
                  )
                    return
                  move.mutate({
                    id: pack.id,
                    status: s,
                    force: s === 'ready' && blockers.length > 0,
                  })
                }}
              >
                Mark {s.replace(/_/g, ' ')}
              </Button>
            ))
          : null}
        {can(session, 'planner.export') ? (
          <Button size='sm' variant='outline' asChild className='ms-auto'>
            <a
              href={`/api/v1/planner/packs/${pack.id}/pdf`}
              target='_blank'
              rel='noreferrer'
            >
              <FileDown /> Issue PDF
            </a>
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function Info({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className='text-xs text-muted-foreground'>{label}</div>
      <div>
        {value === null || value === undefined || value === ''
          ? '—'
          : String(value)}
      </div>
    </div>
  )
}
