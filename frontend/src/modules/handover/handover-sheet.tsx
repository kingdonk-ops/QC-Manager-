import { useState } from 'react'
import { FileDown, Plus, Trash2 } from 'lucide-react'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NodeSelect } from '@/components/asset-node-picker'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Handover,
  type ItemIn,
  KINDS,
  handoverApi,
  useHandover,
  useHandoverHistory,
  useHandoverMutation,
  useItemStatuses,
} from './api'

type Row = ItemIn & { node_label?: string | null }

function rowsOf(h: Handover): Row[] {
  return (h.items ?? []).map((i) => ({
    kind: i.kind as ItemIn['kind'],
    title: i.title,
    status: i.status,
    detail: i.detail,
    reference: i.reference,
    node_id: i.anchor_id,
    node_label: i.anchor_code,
    link_type: i.link_type,
    link_id: i.link_id,
    link_label: i.link_label,
  }))
}

export function HandoverSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { data: h } = useHandover(id)
  return (
    <RecordSheet
      open={id !== null}
      onClose={onClose}
      wide
      title={h ? `${h.code} · ${h.shift_date}` : 'Handover'}
      subtitle={
        h
          ? `${h.area_name ?? 'Whole project'} · ${h.from_shift} → ${h.to_shift} · ${h.author_name ?? '—'} → ${h.recipient_name ?? '—'}`
          : undefined
      }
      badges={h ? <StatusBadge status={h.status} /> : null}
      record={
        h
          ? { projectId: h.project_id, entityType: 'handover', entityId: h.id }
          : undefined
      }
      tabs={h ? { History: <History id={h.id} /> } : undefined}
    >
      {h ? <Body key={`${h.id}-${h.status}`} h={h} /> : null}
    </RecordSheet>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHandoverHistory(id)
  return (
    <ul className='grid gap-1 text-sm'>
      {data.map((x, i) => (
        <li key={i}>
          <StatusBadge status={x.to_status} />{' '}
          <span className='text-muted-foreground'>
            {new Date(x.changed_at).toLocaleString()}
          </span>{' '}
          {x.note}
        </li>
      ))}
    </ul>
  )
}

function Body({ h }: { h: Handover }) {
  const session = useSession()
  const mine = h.author_id === session.id
  const editable =
    h.status === 'draft' && mine && can(session, 'handover.update')
  const forMe = h.recipient_id === session.id
  const { data: statuses } = useItemStatuses()
  const [summary, setSummary] = useState(h.summary ?? '')
  const [safety, setSafety] = useState(h.safety_notes ?? '')
  const [recipient, setRecipient] = useState<number | null>(h.recipient_id)
  const [rows, setRows] = useState<Row[]>(() => rowsOf(h))
  const [ackNote, setAckNote] = useState('')
  const [dirty, setDirty] = useState(false)
  const save = useHandoverMutation(handoverApi.save)
  const submit = useHandoverMutation(handoverApi.submit)
  const recall = useHandoverMutation(handoverApi.recall)
  const ack = useHandoverMutation(handoverApi.acknowledge)

  const body = () => ({
    summary: summary || null,
    safety_notes: safety || null,
    recipient_id: recipient,
    items: rows.map(({ node_label: _label, ...r }) => r),
  })
  const edit = (i: number, patch: Partial<Row>) => {
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
    setDirty(true)
  }

  return (
    <div className='grid gap-4 text-sm'>
      {h.status === 'submitted' ? (
        <div className='rounded-md bg-amber-500/10 p-2 text-amber-800 dark:text-amber-300'>
          Waiting for {h.recipient_name ?? 'the incoming supervisor'} to
          acknowledge
          {h.waiting_hours != null ? ` (${h.waiting_hours} h)` : ''}
          {h.reminders_sent ? ` · ${h.reminders_sent} reminder(s) sent` : ''}.
        </div>
      ) : null}
      {h.status === 'acknowledged' ? (
        <div className='rounded-md bg-green-500/10 p-2 text-green-800 dark:text-green-300'>
          Acknowledged{' '}
          {h.acknowledged_at
            ? new Date(h.acknowledged_at).toLocaleString()
            : ''}
          {h.ack_note ? ` — “${h.ack_note}”` : ''}
        </div>
      ) : null}

      <div className='grid gap-1.5'>
        <Label>Incoming supervisor</Label>
        {editable ? (
          <UserSelect
            value={recipient}
            onChange={(id) => {
              setRecipient(id)
              setDirty(true)
            }}
          />
        ) : (
          <span>{h.recipient_name ?? '—'}</span>
        )}
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='ho-summary'>Summary</Label>
        <Textarea
          id='ho-summary'
          rows={3}
          disabled={!editable}
          value={summary}
          onChange={(e) => {
            setSummary(e.target.value)
            setDirty(true)
          }}
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='ho-safety'>Safety notes</Label>
        <Textarea
          id='ho-safety'
          rows={2}
          disabled={!editable}
          value={safety}
          onChange={(e) => {
            setSafety(e.target.value)
            setDirty(true)
          }}
        />
      </div>

      {KINDS.map(([kind, title]) => {
        const indexed = rows
          .map((r, i) => [r, i] as const)
          .filter(([r]) => r.kind === kind)
        if (!editable && indexed.length === 0) return null
        return (
          <section key={kind} className='grid gap-1.5'>
            <div className='flex items-center justify-between'>
              <h4 className='font-semibold'>{title}</h4>
              {editable ? (
                <Button
                  size='sm'
                  variant='ghost'
                  onClick={() => {
                    setRows([...rows, { kind, title: '' }])
                    setDirty(true)
                  }}
                >
                  <Plus /> Add
                </Button>
              ) : null}
            </div>
            {indexed.map(([r, i]) => (
              <div
                key={i}
                className='grid gap-2 rounded-md border p-2 sm:grid-cols-[1.4fr_9rem_1fr_auto]'
              >
                <Input
                  aria-label={`${title} item`}
                  placeholder='What'
                  disabled={!editable}
                  value={r.title}
                  onChange={(e) => edit(i, { title: e.target.value })}
                />
                <NativeSelect
                  aria-label='Status'
                  disabled={!editable}
                  values={statuses?.statuses[kind] ?? [r.status ?? '']}
                  value={r.status ?? statuses?.statuses[kind]?.[0] ?? ''}
                  onChange={(e) => edit(i, { status: e.target.value })}
                />
                {editable ? (
                  <NodeSelect
                    projectId={h.project_id}
                    value={r.node_id}
                    label={r.node_label}
                    placeholder={kind === 'wip' ? 'Work anchor' : 'Where'}
                    onChange={(id, n) =>
                      edit(i, {
                        node_id: id,
                        node_label: n ? n.display_code || n.code : null,
                      })
                    }
                  />
                ) : (
                  <span className='self-center text-muted-foreground'>
                    {r.node_label ?? ''}
                  </span>
                )}
                {editable ? (
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label='Remove'
                    onClick={() => {
                      setRows(rows.filter((_, j) => j !== i))
                      setDirty(true)
                    }}
                  >
                    <Trash2 />
                  </Button>
                ) : (
                  <span />
                )}
                <Input
                  className='sm:col-span-2'
                  aria-label='Detail'
                  placeholder='Detail'
                  disabled={!editable}
                  value={r.detail ?? ''}
                  onChange={(e) => edit(i, { detail: e.target.value || null })}
                />
                <Input
                  aria-label='Reference'
                  placeholder={
                    kind === 'issue' ? 'Link, e.g. NCR-004' : 'Ref / tag'
                  }
                  disabled={!editable}
                  value={(kind === 'issue' ? r.link_label : r.reference) ?? ''}
                  onChange={(e) =>
                    edit(
                      i,
                      kind === 'issue'
                        ? { link_label: e.target.value || null }
                        : { reference: e.target.value || null }
                    )
                  }
                />
              </div>
            ))}
          </section>
        )
      })}

      <div className='flex flex-wrap gap-2 border-t pt-3'>
        {editable ? (
          <>
            <Button
              variant='outline'
              disabled={!dirty || save.isPending}
              onClick={() =>
                save.mutate(
                  { id: h.id, body: body() },
                  { onSuccess: () => setDirty(false) }
                )
              }
            >
              Save draft
            </Button>
            {can(session, 'handover.submit') ? (
              <Button
                disabled={!recipient || save.isPending || submit.isPending}
                onClick={() =>
                  dirty
                    ? save.mutate(
                        { id: h.id, body: body() },
                        { onSuccess: () => submit.mutate(h.id) }
                      )
                    : submit.mutate(h.id)
                }
              >
                Hand over
              </Button>
            ) : null}
          </>
        ) : null}
        {h.status === 'submitted' && mine ? (
          <Button variant='outline' onClick={() => recall.mutate(h.id)}>
            Recall
          </Button>
        ) : null}
        {h.status === 'submitted' &&
        forMe &&
        can(session, 'handover.respond') ? (
          <div className='flex w-full flex-wrap gap-2'>
            <Input
              className='min-w-48 flex-1'
              placeholder='Questions or notes for the author (optional)'
              aria-label='Acknowledgement note'
              value={ackNote}
              onChange={(e) => setAckNote(e.target.value)}
            />
            <Button
              onClick={() => ack.mutate({ id: h.id, note: ackNote || null })}
            >
              I have read this handover
            </Button>
          </div>
        ) : null}
        {can(session, 'handover.export') ? (
          <Button size='sm' variant='outline' asChild className='ms-auto'>
            <a
              href={`/api/v1/handover/handovers/${h.id}/pdf`}
              target='_blank'
              rel='noreferrer'
            >
              <FileDown /> PDF
            </a>
          </Button>
        ) : null}
      </div>
    </div>
  )
}
