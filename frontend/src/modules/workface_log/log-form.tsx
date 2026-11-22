import { useState, type ReactNode } from 'react'
import { Copy, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NodeSelect } from '@/components/asset-node-picker'
import { NativeSelect, type Option } from '@/components/native-select'
import { Attachments } from '@/components/records/attachments'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Log,
  type LogUpdate,
  logApi,
  useCodes,
  useLogMutation,
} from './api'
import { type Draft, sumHours, toBody, toDraft, unallocated } from './form-lib'

const label = (v: string) =>
  v.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function Section({
  title,
  action,
  children,
}: {
  title: ReactNode
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <Card className='gap-2 py-3'>
      <CardHeader className='flex flex-row items-center justify-between px-3'>
        <CardTitle className='text-sm'>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className='grid gap-2 px-3'>{children}</CardContent>
    </Card>
  )
}

/** The whole day on one form, stacked for a phone: crew hours, quantities, delays, plant, weather, notes, photos. */
export function LogForm({ log }: { log: Log }) {
  const session = useSession()
  const { data: codes } = useCodes()
  const [draft, setDraft] = useState<Draft>(() => toDraft(log))
  const [dirty, setDirty] = useState(false)
  const save = useLogMutation(logApi.save)
  const copy = useLogMutation(logApi.copyPrevious)
  const step = useLogMutation(logApi.step)
  const editable = log.status === 'draft' && can(session, 'workface_log.update')

  const set = (patch: Partial<Draft>) => {
    setDraft({ ...draft, ...patch })
    setDirty(true)
  }
  const codeOptions: Option[] = [
    { value: '', label: 'On the work anchor' },
    ...(codes?.delay_codes ?? []).map((c) => ({
      value: `delay:${c}`,
      label: `Delay: ${label(c)}`,
    })),
    ...(codes?.overhead_codes ?? []).map((c) => ({
      value: `overhead:${c}`,
      label: `Overhead: ${label(c)}`,
    })),
  ]
  const missing = unallocated(draft.hours)
  const persist = (then?: () => void) =>
    save.mutate(
      { id: log.id, body: toBody(draft) as LogUpdate },
      {
        onSuccess: (saved) => {
          setDraft(toDraft(saved))
          setDirty(false)
          saved.warnings?.forEach((w) => toast.warning(w))
          then?.()
        },
      }
    )

  return (
    <div className='grid gap-3 pb-20'>
      <div className='flex flex-wrap items-center gap-2 text-sm'>
        <span className='font-mono'>{log.code}</span>
        <StatusBadge status={log.status} />
        <span className='text-muted-foreground'>
          {log.work_date} · {log.shift} shift · {log.crew_code} {log.crew_name}
        </span>
        {editable ? (
          <Button
            size='sm'
            variant='outline'
            className='ms-auto'
            disabled={copy.isPending}
            onClick={() =>
              copy.mutate(log.id, {
                onSuccess: (got) => {
                  setDraft(toDraft(got))
                  setDirty(false)
                },
              })
            }
          >
            <Copy /> Copy yesterday
          </Button>
        ) : null}
      </div>

      <Section
        title={`Crew hours (${sumHours(draft.hours)} h)`}
        action={
          editable ? (
            <Button
              size='sm'
              variant='ghost'
              onClick={() =>
                set({
                  hours: [
                    ...draft.hours,
                    {
                      person: '',
                      trade: '',
                      hours: '',
                      node_id:
                        draft.hours[draft.hours.length - 1]?.node_id ?? null,
                      node_label:
                        draft.hours[draft.hours.length - 1]?.node_label ?? null,
                      code: '',
                    },
                  ],
                })
              }
            >
              <Plus /> Person
            </Button>
          ) : null
        }
      >
        {draft.hours.map((h, i) => {
          const edit = (patch: Partial<typeof h>) =>
            set({
              hours: draft.hours.map((r, j) =>
                j === i ? { ...r, ...patch } : r
              ),
            })
          const bad = missing.includes(h)
          return (
            <div
              key={i}
              className={cn(
                'grid gap-2 rounded-md border p-2 sm:grid-cols-[1fr_7rem_5rem_1.2fr_1fr_auto]',
                bad && 'border-red-500'
              )}
            >
              <Input
                aria-label='Person'
                placeholder='Name'
                disabled={!editable}
                value={h.person}
                onChange={(e) => edit({ person: e.target.value })}
              />
              <Input
                aria-label='Trade'
                placeholder='Trade'
                disabled={!editable}
                value={h.trade}
                onChange={(e) => edit({ trade: e.target.value })}
              />
              <Input
                aria-label='Hours'
                inputMode='decimal'
                placeholder='h'
                disabled={!editable}
                value={h.hours}
                onChange={(e) => edit({ hours: e.target.value })}
              />
              <NodeSelect
                projectId={log.project_id}
                value={h.node_id}
                label={h.node_label}
                placeholder='Work anchor'
                onChange={(id, n) =>
                  edit({
                    node_id: id,
                    node_label: n ? n.display_code || n.code : null,
                  })
                }
              />
              <NativeSelect
                aria-label='Code'
                disabled={!editable}
                options={codeOptions}
                value={h.code}
                onChange={(e) => edit({ code: e.target.value })}
              />
              {editable ? (
                <RemoveButton
                  onClick={() =>
                    set({ hours: draft.hours.filter((_, j) => j !== i) })
                  }
                />
              ) : null}
              {bad ? (
                <p className='text-xs text-red-600 sm:col-span-6'>
                  Pick a work anchor, or a delay or overhead code.
                </p>
              ) : null}
            </div>
          )
        })}
      </Section>

      <Section
        title='Installed today'
        action={
          editable ? (
            <Button
              size='sm'
              variant='ghost'
              onClick={() =>
                set({
                  quantities: [
                    ...draft.quantities,
                    { node_id: null, node_label: null, qty: '', uom: '' },
                  ],
                })
              }
            >
              <Plus /> Quantity
            </Button>
          ) : null
        }
      >
        {draft.quantities.map((q, i) => {
          const edit = (patch: Partial<typeof q>) =>
            set({
              quantities: draft.quantities.map((r, j) =>
                j === i ? { ...r, ...patch } : r
              ),
            })
          return (
            <div key={i} className='grid grid-cols-[1fr_6rem_4rem_auto] gap-2'>
              <NodeSelect
                projectId={log.project_id}
                value={q.node_id}
                label={q.node_label}
                placeholder='Work anchor / progress unit'
                onChange={(id, n) =>
                  edit({
                    node_id: id,
                    node_label: n ? n.display_code || n.code : null,
                    uom: q.uom || n?.uom || '',
                  })
                }
              />
              <Input
                aria-label='Quantity'
                inputMode='decimal'
                disabled={!editable}
                value={q.qty}
                onChange={(e) => edit({ qty: e.target.value })}
              />
              <Input
                aria-label='Unit'
                disabled={!editable}
                value={q.uom}
                onChange={(e) => edit({ uom: e.target.value })}
              />
              {editable ? (
                <RemoveButton
                  onClick={() =>
                    set({
                      quantities: draft.quantities.filter((_, j) => j !== i),
                    })
                  }
                />
              ) : null}
            </div>
          )
        })}
        {log.warnings?.map((w) => (
          <p key={w} className='text-xs text-amber-700 dark:text-amber-400'>
            {w}
          </p>
        ))}
      </Section>

      <Section
        title='Delays'
        action={
          editable ? (
            <Button
              size='sm'
              variant='ghost'
              onClick={() =>
                set({
                  delays: [
                    ...draft.delays,
                    {
                      code: 'weather',
                      hours: '',
                      node_id: null,
                      node_label: null,
                      description: '',
                    },
                  ],
                })
              }
            >
              <Plus /> Delay
            </Button>
          ) : null
        }
      >
        {draft.delays.map((d, i) => {
          const edit = (patch: Partial<typeof d>) =>
            set({
              delays: draft.delays.map((r, j) =>
                j === i ? { ...r, ...patch } : r
              ),
            })
          return (
            <div
              key={i}
              className='grid gap-2 sm:grid-cols-[9rem_5rem_1fr_1.5fr_auto]'
            >
              <NativeSelect
                aria-label='Delay code'
                disabled={!editable}
                values={codes?.delay_codes ?? [d.code]}
                value={d.code}
                onChange={(e) => edit({ code: e.target.value })}
              />
              <Input
                aria-label='Delay hours'
                inputMode='decimal'
                placeholder='h'
                disabled={!editable}
                value={d.hours}
                onChange={(e) => edit({ hours: e.target.value })}
              />
              <NodeSelect
                projectId={log.project_id}
                value={d.node_id}
                label={d.node_label}
                placeholder='Where (optional)'
                onChange={(id, n) =>
                  edit({
                    node_id: id,
                    node_label: n ? n.display_code || n.code : null,
                  })
                }
              />
              <Input
                aria-label='What happened'
                placeholder='What happened'
                disabled={!editable}
                value={d.description}
                onChange={(e) => edit({ description: e.target.value })}
              />
              {editable ? (
                <RemoveButton
                  onClick={() =>
                    set({ delays: draft.delays.filter((_, j) => j !== i) })
                  }
                />
              ) : null}
            </div>
          )
        })}
      </Section>

      <Section
        title='Plant and equipment'
        action={
          editable ? (
            <Button
              size='sm'
              variant='ghost'
              onClick={() =>
                set({
                  equipment: [
                    ...draft.equipment,
                    { equipment: '', hours: '', status: 'operating' },
                  ],
                })
              }
            >
              <Plus /> Equipment
            </Button>
          ) : null
        }
      >
        {draft.equipment.map((e, i) => {
          const edit = (patch: Partial<typeof e>) =>
            set({
              equipment: draft.equipment.map((r, j) =>
                j === i ? { ...r, ...patch } : r
              ),
            })
          return (
            <div key={i} className='grid grid-cols-[1fr_5rem_8rem_auto] gap-2'>
              <Input
                aria-label='Equipment'
                placeholder='e.g. CR-08 100t crane'
                disabled={!editable}
                value={e.equipment}
                onChange={(ev) => edit({ equipment: ev.target.value })}
              />
              <Input
                aria-label='Equipment hours'
                inputMode='decimal'
                disabled={!editable}
                value={e.hours}
                onChange={(ev) => edit({ hours: ev.target.value })}
              />
              <NativeSelect
                aria-label='Equipment status'
                disabled={!editable}
                values={codes?.equipment_statuses ?? [e.status]}
                value={e.status}
                onChange={(ev) => edit({ status: ev.target.value })}
              />
              {editable ? (
                <RemoveButton
                  onClick={() =>
                    set({
                      equipment: draft.equipment.filter((_, j) => j !== i),
                    })
                  }
                />
              ) : null}
            </div>
          )
        })}
      </Section>

      <Section title='Weather and notes'>
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-5'>
          <Input
            className='col-span-2 sm:col-span-1'
            aria-label='Weather'
            placeholder='Conditions'
            disabled={!editable}
            value={draft.weather}
            onChange={(e) => set({ weather: e.target.value })}
          />
          {(
            [
              ['temp_min_c', 'Min °C'],
              ['temp_max_c', 'Max °C'],
              ['wind_kmh', 'Wind km/h'],
              ['rain_mm', 'Rain mm'],
            ] as const
          ).map(([key, text]) => (
            <Input
              key={key}
              aria-label={text}
              placeholder={text}
              inputMode='decimal'
              disabled={!editable}
              value={draft[key]}
              onChange={(e) => set({ [key]: e.target.value })}
            />
          ))}
        </div>
        <Textarea
          aria-label='Diary notes'
          placeholder='What the crew did, safety observations, anything for tomorrow'
          rows={3}
          disabled={!editable}
          value={draft.notes}
          onChange={(e) => set({ notes: e.target.value })}
        />
      </Section>

      <Section title='Photos'>
        <Attachments
          projectId={log.project_id}
          entityType='workface_log'
          entityId={log.id}
        />
      </Section>

      {log.totals ? (
        <Section title='Day summary'>
          <div className='grid grid-cols-2 gap-1 text-sm sm:grid-cols-4'>
            <span>Productive: {Number(log.totals.productive_hours)} h</span>
            <span>Delays: {Number(log.totals.delay_hours)} h</span>
            <span>Overhead: {Number(log.totals.overhead_hours)} h</span>
            <span>Headcount: {log.totals.headcount}</span>
          </div>
          <ul className='text-xs text-muted-foreground'>
            {log.totals.by_anchor.map((a) => (
              <li key={a.anchor_id}>
                {a.anchor_code}: {Number(a.hours)} h
                {Number(a.qty) ? ` · ${Number(a.qty)} ${a.uom ?? ''}` : ''}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <div className='sticky bottom-0 flex flex-wrap gap-2 border-t bg-background py-2'>
        {editable ? (
          <>
            <Button
              variant='outline'
              disabled={!dirty || save.isPending}
              onClick={() => persist()}
            >
              Save draft
            </Button>
            {can(session, 'workface_log.submit') ? (
              <Button
                disabled={
                  save.isPending || step.isPending || missing.length > 0
                }
                onClick={() =>
                  dirty
                    ? persist(() => step.mutate({ id: log.id, step: 'submit' }))
                    : step.mutate({ id: log.id, step: 'submit' })
                }
              >
                Submit for sign-off
              </Button>
            ) : null}
          </>
        ) : null}
        {log.status === 'submitted' && can(session, 'workface_log.review') ? (
          <>
            <Button onClick={() => step.mutate({ id: log.id, step: 'sign' })}>
              Sign off
            </Button>
            <Button
              variant='outline'
              onClick={() => {
                const note = window.prompt('What needs changing?')
                if (note !== null)
                  step.mutate({ id: log.id, step: 'return', note })
              }}
            >
              Return
            </Button>
          </>
        ) : null}
        {log.status === 'signed' ? (
          <span className='text-sm text-muted-foreground'>
            Signed by {log.signed_by_name ?? '—'}
            {log.signed_at
              ? ` on ${new Date(log.signed_at).toLocaleString()}`
              : ''}
          </span>
        ) : null}
      </div>
    </div>
  )
}

function RemoveButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type='button'
      size='icon'
      variant='ghost'
      className='size-9'
      aria-label='Remove'
      onClick={onClick}
    >
      <Trash2 />
    </Button>
  )
}
