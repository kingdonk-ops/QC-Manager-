import { useMemo, useState } from 'react'
import type { ColDef } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataGrid } from '@/components/data-grid'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Joint,
  useAct,
  useJoint,
  useJoints,
  useUsableTools,
  weldingApi,
} from './api'
import { NodePicker } from './node-picker'

const today = () => new Date().toISOString().slice(0, 10)

function NewJoint({
  projectId,
  onDone,
}: {
  projectId: number
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [node, setNode] = useState<{ id: number; label: string }>()
  const [form, setForm] = useState({
    joint_ref: '',
    size: '',
    rating: '',
    target: '',
    unit: 'Nm',
  })
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value })
  const act = useAct(() =>
    weldingApi.createJoint({
      project_id: projectId,
      node_id: node!.id,
      joint_ref: form.joint_ref,
      size: form.size || null,
      rating: form.rating || null,
      target_value: form.target || null,
      unit: form.unit,
      method: 'torque',
      tolerance_pct: '5',
      status: 'new',
    })
  )
  return (
    <div className='grid gap-3 sm:grid-cols-2'>
      <Field label={t('welding.node')} className='sm:col-span-2'>
        <NodePicker projectId={projectId} value={node} onChange={setNode} />
      </Field>
      <Field label={t('welding.joint_ref')}>
        <Input value={form.joint_ref} onChange={set('joint_ref')} />
      </Field>
      <Field label={t('welding.size_rating')}>
        <div className='flex gap-2'>
          <Input value={form.size} onChange={set('size')} />
          <Input value={form.rating} onChange={set('rating')} />
        </div>
      </Field>
      <Field label={t('welding.target')}>
        <div className='flex gap-2'>
          <Input value={form.target} onChange={set('target')} />
          <Input className='w-20' value={form.unit} onChange={set('unit')} />
        </div>
      </Field>
      <div className='flex items-end'>
        <Button
          size='sm'
          disabled={!node || !form.joint_ref}
          onClick={() => act.mutate(undefined, { onSuccess: onDone })}
        >
          {t('welding.save')}
        </Button>
      </div>
    </div>
  )
}

function JointSheet({
  projectId,
  id,
  onClose,
}: {
  projectId: number
  id: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: joint } = useJoint(id)
  const { data: tools = [] } = useUsableTools(projectId)
  const [tool, setTool] = useState<number[]>([])
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const act = useAct((kind: 'breakout' | 'make_up') =>
    weldingApi.jointEvent(id, {
      kind,
      performed_on: today(),
      equipment_ids: kind === 'make_up' ? tool : [],
      applied_value: kind === 'make_up' ? value || null : null,
      pass_values: [],
      gasket_replaced: kind === 'make_up',
      reason: reason || null,
    })
  )
  if (!joint) return null
  const editable = can(session, 'welding.update')
  return (
    <RecordSheet
      open
      onClose={onClose}
      title={joint.joint_ref}
      subtitle={joint.node_path ?? undefined}
      badges={<StatusBadge status={joint.status} />}
      record={{ projectId, entityType: 'bolted_joint', entityId: joint.id }}
    >
      <div className='grid gap-4 text-sm'>
        <p>
          {joint.size} {joint.rating} · {t('welding.target')}{' '}
          {joint.target_value ?? '–'} {joint.unit} ± {joint.tolerance_pct}%
        </p>
        {editable && joint.status === 'made_up' ? (
          <div className='flex gap-2'>
            <Input
              placeholder={t('welding.reason_short')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button size='sm' onClick={() => act.mutate('breakout')}>
              {t('welding.breakout')}
            </Button>
          </div>
        ) : null}
        {editable && joint.status !== 'made_up' ? (
          <div className='grid gap-2 rounded-md border p-3'>
            <span className='text-xs text-muted-foreground'>
              {t('welding.tools')}
            </span>
            {tools.map((e) => (
              <label key={e.id} className='flex items-center gap-2'>
                <input
                  type='checkbox'
                  checked={tool.includes(e.id)}
                  onChange={(ev) =>
                    setTool(
                      ev.target.checked
                        ? [...tool, e.id]
                        : tool.filter((x) => x !== e.id)
                    )
                  }
                />
                {e.code} {e.name} ({t('welding.due')} {e.due_on ?? '–'})
              </label>
            ))}
            {!tools.length ? (
              <p className='text-muted-foreground'>{t('welding.no_tools')}</p>
            ) : null}
            <div className='flex gap-2'>
              <Input
                placeholder={t('welding.applied')}
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
              <Button
                size='sm'
                disabled={!tool.length || !value}
                onClick={() => act.mutate('make_up')}
              >
                {t('welding.make_up')}
              </Button>
            </div>
          </div>
        ) : null}
        <table className='w-full'>
          <tbody>
            {(joint.events ?? []).map((e) => (
              <tr key={e.id} className='border-t'>
                <td className='py-1'>{e.performed_on}</td>
                <td>{t(`welding.event.${e.kind}`)}</td>
                <td>
                  {e.applied_value ? `${e.applied_value} ${joint.unit}` : ''}
                </td>
                <td className='text-muted-foreground'>{e.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </RecordSheet>
  )
}

export function JointsTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: joints = [] } = useJoints(projectId)
  const [openId, setOpenId] = useState<number | 'new'>()
  const columns = useMemo<ColDef<Joint>[]>(
    () => [
      { field: 'joint_ref', headerName: t('welding.joint_ref'), width: 120 },
      { field: 'node_path', headerName: t('welding.node'), flex: 1 },
      { field: 'size', headerName: t('welding.size'), width: 90 },
      { field: 'rating', headerName: t('welding.rating'), width: 90 },
      { field: 'target_value', headerName: t('welding.target'), width: 100 },
      { field: 'breakouts', headerName: t('welding.breakouts'), width: 100 },
      {
        field: 'last_event_on',
        headerName: t('welding.last_event'),
        width: 120,
      },
      {
        field: 'status',
        headerName: t('welding.status'),
        width: 130,
        cellRenderer: (p: { value?: string }) => (
          <StatusBadge status={p.value} />
        ),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-2'>
      {can(session, 'welding.create') ? (
        <Button size='sm' className='ms-auto' onClick={() => setOpenId('new')}>
          <Plus /> {t('welding.new_joint')}
        </Button>
      ) : null}
      <div className='h-[480px]'>
        <DataGrid<Joint>
          rowData={joints}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && setOpenId(e.data.id)}
        />
      </div>
      {openId === 'new' ? (
        <RecordSheet
          open
          onClose={() => setOpenId(undefined)}
          title={t('welding.new_joint')}
        >
          <NewJoint projectId={projectId} onDone={() => setOpenId(undefined)} />
        </RecordSheet>
      ) : openId ? (
        <JointSheet
          projectId={projectId}
          id={openId}
          onClose={() => setOpenId(undefined)}
        />
      ) : null}
    </div>
  )
}
