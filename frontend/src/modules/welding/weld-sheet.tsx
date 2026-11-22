import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/native-select'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  CATEGORIES,
  JOINT_TYPES,
  useAct,
  useWeld,
  useWelders,
  useWps,
  type WeldDetail,
  weldingApi,
} from './api'
import { NodePicker } from './node-picker'

const today = () => new Date().toISOString().slice(0, 10)

/** Who welded it: one welder per pass. Refused by the backend for an unqualified welder. */
function RecordWelding({
  projectId,
  weld,
}: {
  projectId: number
  weld: WeldDetail
}) {
  const { t } = useTranslation()
  const { data: welders = [] } = useWelders(projectId)
  const [on, setOn] = useState(today())
  const [passes, setPasses] = useState([{ pass_name: 'root', welder_id: 0 }])
  const act = useAct(() =>
    weldingApi.recordWelding(weld.id, {
      welded_on: on,
      passes: passes.filter((p) => p.welder_id),
    })
  )
  const options = welders.map((w) => ({
    value: String(w.id),
    label: `${w.stamp} ${w.name}`,
  }))
  return (
    <div className='grid gap-2 rounded-md border p-3'>
      <h4 className='text-sm font-semibold'>{t('welding.record_welding')}</h4>
      <Field label={t('welding.welded_on')}>
        <Input
          type='date'
          max={today()}
          value={on}
          onChange={(e) => setOn(e.target.value)}
        />
      </Field>
      {passes.map((p, i) => (
        <div key={i} className='grid grid-cols-2 gap-2'>
          <Input
            value={p.pass_name}
            onChange={(e) =>
              setPasses(
                passes.map((x, j) =>
                  j === i ? { ...x, pass_name: e.target.value } : x
                )
              )
            }
          />
          <NativeSelect
            options={options}
            placeholder={t('welding.welder')}
            value={p.welder_id ? String(p.welder_id) : ''}
            onChange={(e) =>
              setPasses(
                passes.map((x, j) =>
                  j === i ? { ...x, welder_id: Number(e.target.value) } : x
                )
              )
            }
          />
        </div>
      ))}
      <div className='flex gap-2'>
        <Button
          size='sm'
          variant='outline'
          onClick={() =>
            setPasses([...passes, { pass_name: 'cap', welder_id: 0 }])
          }
        >
          {t('welding.add_pass')}
        </Button>
        <Button
          size='sm'
          disabled={act.isPending}
          onClick={() => act.mutate(undefined)}
        >
          {t('welding.save')}
        </Button>
      </div>
    </div>
  )
}

function Repair({ projectId, weld }: { projectId: number; weld: WeldDetail }) {
  const { t } = useTranslation()
  const { data: welders = [] } = useWelders(projectId)
  const [welder, setWelder] = useState('')
  const [defect, setDefect] = useState('')
  const act = useAct(() =>
    weldingApi.repair(weld.id, {
      repaired_on: today(),
      welder_ids: [Number(welder)],
      defect: defect || null,
    })
  )
  return (
    <div className='grid gap-2 rounded-md border p-3'>
      <h4 className='text-sm font-semibold'>
        {t('welding.repair', { n: weld.repair_count + 1 })}
      </h4>
      <NativeSelect
        options={welders.map((w) => ({
          value: String(w.id),
          label: `${w.stamp} ${w.name}`,
        }))}
        placeholder={t('welding.welder')}
        value={welder}
        onChange={(e) => setWelder(e.target.value)}
      />
      <Input
        placeholder={t('welding.defect')}
        value={defect}
        onChange={(e) => setDefect(e.target.value)}
      />
      <Button
        size='sm'
        disabled={!welder || act.isPending}
        onClick={() => act.mutate(undefined)}
      >
        {t('welding.record_repair')}
      </Button>
    </div>
  )
}

function NdeHistory({ weld }: { weld: WeldDetail }) {
  const { t } = useTranslation()
  return (
    <div className='grid gap-4 text-sm'>
      <table className='w-full'>
        <thead className='text-left text-xs text-muted-foreground'>
          <tr>
            <th>{t('welding.method')}</th>
            <th>{t('welding.reason')}</th>
            <th>{t('welding.repair_short')}</th>
            <th>{t('welding.request')}</th>
            <th>{t('welding.report')}</th>
            <th>{t('welding.result')}</th>
          </tr>
        </thead>
        <tbody>
          {(weld.nde ?? []).map((r) => (
            <tr key={r.id} className='border-t'>
              <td className='py-1.5 uppercase'>{r.method}</td>
              <td>
                {t(`welding.reason.${r.reason}`)}
                {r.tier ? ` (${r.tier})` : ''}
              </td>
              <td>{r.repair_seq ? `R${r.repair_seq}` : ''}</td>
              <td>{r.request_code}</td>
              <td>{r.report_ref}</td>
              <td>
                <StatusBadge status={r.result} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4 className='font-semibold'>{t('welding.passes')}</h4>
      <ul>
        {(weld.passes ?? []).map((p) => (
          <li key={p.id}>
            {p.repair_seq ? `R${p.repair_seq} · ` : ''}
            {p.pass_name}: <strong>{p.welder_stamp}</strong>
          </li>
        ))}
      </ul>
      {weld.repairs?.length ? (
        <>
          <h4 className='font-semibold'>{t('welding.repairs')}</h4>
          <ul>
            {(weld.repairs ?? []).map((r) => (
              <li key={r.id}>
                R{r.seq} · {r.repaired_on} {r.defect ? `· ${r.defect}` : ''}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  )
}

function NewWeld({
  projectId,
  onDone,
}: {
  projectId: number
  onDone: () => void
}) {
  const { t } = useTranslation()
  const { data: wps = [] } = useWps(projectId)
  const [node, setNode] = useState<{ id: number; label: string }>()
  const [form, setForm] = useState({
    weld_number: '',
    drawing_ref: '',
    joint_type: 'butt',
    weld_category: 'normal',
    wps_id: '',
    diameter: '',
    thickness: '',
  })
  const act = useAct(() =>
    weldingApi.createWeld({
      project_id: projectId,
      node_id: node?.id,
      weld_number: form.weld_number,
      drawing_ref: form.drawing_ref || null,
      joint_type: form.joint_type as never,
      weld_category: form.weld_category,
      wps_id: form.wps_id ? Number(form.wps_id) : null,
      diameter: form.diameter || null,
      thickness: form.thickness || null,
    })
  )
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value })
  return (
    <form
      className='grid gap-3 sm:grid-cols-2'
      onSubmit={(e) => {
        e.preventDefault()
        act.mutate(undefined, {
          onSuccess: () => {
            toast.success(t('welding.created'))
            onDone()
          },
        })
      }}
    >
      <Field label={t('welding.node')} className='sm:col-span-2'>
        <NodePicker projectId={projectId} value={node} onChange={setNode} />
      </Field>
      <Field label={t('welding.weld_number')}>
        <Input
          required
          value={form.weld_number}
          onChange={set('weld_number')}
        />
      </Field>
      <Field label={t('welding.drawing')}>
        <Input value={form.drawing_ref} onChange={set('drawing_ref')} />
      </Field>
      <Field label={t('welding.joint_type')}>
        <NativeSelect
          values={JOINT_TYPES}
          value={form.joint_type}
          onChange={set('joint_type')}
        />
      </Field>
      <Field label={t('welding.category')}>
        <NativeSelect
          values={CATEGORIES}
          value={form.weld_category}
          onChange={set('weld_category')}
        />
      </Field>
      <Field label={t('welding.wps')}>
        <NativeSelect
          placeholder='—'
          options={wps.map((w) => ({
            value: String(w.id),
            label: `${w.code} rev ${w.revision} (${w.status})`,
          }))}
          value={form.wps_id}
          onChange={set('wps_id')}
        />
      </Field>
      <Field label={t('welding.diameter')}>
        <Input value={form.diameter} onChange={set('diameter')} />
      </Field>
      <Field label={t('welding.thickness')}>
        <Input value={form.thickness} onChange={set('thickness')} />
      </Field>
      <div className='flex items-end'>
        <Button type='submit' size='sm' disabled={!node || act.isPending}>
          {t('welding.save')}
        </Button>
      </div>
    </form>
  )
}

export function WeldSheet({
  projectId,
  weldId,
  onClose,
}: {
  projectId: number
  weldId?: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: weld } = useWeld(weldId)
  const id = weld?.id ?? 0
  const visual = useAct((r: 'accepted' | 'rejected') =>
    weldingApi.visual(id, r)
  )
  const pwht = useAct(() => weldingApi.pwht(id, today()))
  const accept = useAct(() => weldingApi.accept(id))
  const cutOut = useAct(() => weldingApi.cutOut(id))
  const canUpdate = can(session, 'welding.update')
  const canReview = can(session, 'welding.review')

  if (!weldId)
    return (
      <RecordSheet open onClose={onClose} title={t('welding.new_weld')}>
        <NewWeld projectId={projectId} onDone={onClose} />
      </RecordSheet>
    )
  if (!weld) return null
  const open = !['accepted', 'cut_out', 'fit_up'].includes(weld.status)
  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={`${weld.weld_number}${weld.repair_label ? ` ${weld.repair_label}` : ''}`}
      subtitle={[weld.drawing_ref, weld.node_path].filter(Boolean).join(' · ')}
      badges={<StatusBadge status={weld.status} />}
      record={{ projectId, entityType: 'weld', entityId: weld.id }}
      tabs={{ [t('welding.nde_repairs')]: <NdeHistory weld={weld} /> }}
    >
      <div className='grid gap-4'>
        <dl className='grid grid-cols-2 gap-1 text-sm sm:grid-cols-4'>
          <dt className='text-muted-foreground'>{t('welding.wps')}</dt>
          <dd>{weld.wps_code ?? '–'}</dd>
          <dt className='text-muted-foreground'>{t('welding.joint_type')}</dt>
          <dd>{weld.joint_type}</dd>
          <dt className='text-muted-foreground'>{t('welding.category')}</dt>
          <dd>{weld.weld_category}</dd>
          <dt className='text-muted-foreground'>{t('welding.size')}</dt>
          <dd>
            {weld.diameter ?? '–'}in {weld.schedule ?? ''} /{' '}
            {weld.thickness ?? '–'}mm
          </dd>
          <dt className='text-muted-foreground'>{t('welding.welders')}</dt>
          <dd>{(weld.welders ?? []).join(', ') || '–'}</dd>
          <dt className='text-muted-foreground'>{t('welding.welded_on')}</dt>
          <dd>{weld.welded_on ?? '–'}</dd>
          <dt className='text-muted-foreground'>{t('welding.nde_required')}</dt>
          <dd>
            {Object.entries(weld.nde_required)
              .map(([m, p]) => `${m.toUpperCase()} ${p}%`)
              .join(', ') || '–'}
          </dd>
          <dt className='text-muted-foreground'>{t('welding.visual')}</dt>
          <dd>
            <StatusBadge status={weld.visual_result} />
          </dd>
          <dt className='text-muted-foreground'>PWHT</dt>
          <dd>
            {weld.pwht_required
              ? (weld.pwht_on ?? t('welding.pwht_due'))
              : t('welding.not_required')}
          </dd>
        </dl>
        {weld.status === 'fit_up' && canUpdate ? (
          <RecordWelding projectId={projectId} weld={weld} />
        ) : null}
        {weld.status === 'rejected' && canUpdate ? (
          <Repair projectId={projectId} weld={weld} />
        ) : null}
        <div className='flex flex-wrap gap-2'>
          {open && canReview ? (
            <>
              <Button
                size='sm'
                variant='outline'
                onClick={() => visual.mutate('accepted')}
              >
                {t('welding.visual_ok')}
              </Button>
              <Button
                size='sm'
                variant='outline'
                onClick={() => visual.mutate('rejected')}
              >
                {t('welding.visual_reject')}
              </Button>
            </>
          ) : null}
          {open && weld.pwht_required && !weld.pwht_on && canUpdate ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => pwht.mutate(undefined)}
            >
              {t('welding.pwht_done')}
            </Button>
          ) : null}
          {weld.status === 'welded' && canReview ? (
            <Button size='sm' onClick={() => accept.mutate(undefined)}>
              {t('welding.accept')}
            </Button>
          ) : null}
          {open && canReview ? (
            <Button
              size='sm'
              variant='destructive'
              onClick={() => cutOut.mutate(undefined)}
            >
              {t('welding.cut_out')}
            </Button>
          ) : null}
        </div>
      </div>
    </RecordSheet>
  )
}
