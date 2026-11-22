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
import { materialsApi, PRODUCT_FORMS, useAct, useHeat } from './api'
import { NodePicker } from './node-picker'

const today = () => new Date().toISOString().slice(0, 10)

function NewHeat({
  projectId,
  onDone,
}: {
  projectId: number
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    heat_number: '',
    material_grade: '',
    product_form: 'pipe',
    received_on: today(),
    supplied_by: 'company',
    expected_delivery: '',
  })
  const [node, setNode] = useState<{ id: number; label: string }>()
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value })
  const act = useAct(() =>
    materialsApi.createHeat({
      project_id: projectId,
      heat_number: form.heat_number,
      material_grade: form.material_grade,
      product_form: form.product_form as never,
      received_on: form.received_on || null,
      supplied_by: form.supplied_by as never,
      expected_delivery: form.expected_delivery || null,
      planned_node_id: node?.id ?? null,
    })
  )
  return (
    <form
      className='grid gap-3 sm:grid-cols-2'
      onSubmit={(e) => {
        e.preventDefault()
        act.mutate(undefined, { onSuccess: onDone })
      }}
    >
      <Field label={t('materials.heat')}>
        <Input
          required
          value={form.heat_number}
          onChange={set('heat_number')}
        />
      </Field>
      <Field label={t('materials.grade')}>
        <Input
          required
          value={form.material_grade}
          onChange={set('material_grade')}
        />
      </Field>
      <Field label={t('materials.form')}>
        <NativeSelect
          values={PRODUCT_FORMS}
          value={form.product_form}
          onChange={set('product_form')}
        />
      </Field>
      <Field label={t('materials.supplied_by')}>
        <NativeSelect
          options={[
            { value: 'company', label: t('materials.company') },
            { value: 'client', label: t('materials.client') },
          ]}
          value={form.supplied_by}
          onChange={set('supplied_by')}
        />
      </Field>
      <Field label={t('materials.received')}>
        <Input
          type='date'
          value={form.received_on}
          onChange={set('received_on')}
        />
      </Field>
      <Field label={t('materials.expected')}>
        <Input
          type='date'
          value={form.expected_delivery}
          onChange={set('expected_delivery')}
        />
      </Field>
      <Field label={t('materials.planned_for')} className='sm:col-span-2'>
        <NodePicker projectId={projectId} value={node} onChange={setNode} />
      </Field>
      <div>
        <Button type='submit' size='sm' disabled={act.isPending}>
          {t('materials.save')}
        </Button>
      </div>
    </form>
  )
}

export function HeatSheet({
  projectId,
  heatId,
  onClose,
}: {
  projectId: number
  heatId?: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: heat } = useHeat(heatId)
  const id = heat?.id ?? 0
  const [cert, setCert] = useState('')
  const [reason, setReason] = useState('')
  const [node, setNode] = useState<{ id: number; label: string }>()
  const addCert = useAct(() =>
    materialsApi.addCertificate(id, {
      certificate_number: cert,
      certificate_type: '3.1',
      chemistry: {},
      mechanicals: {},
    })
  )
  const verify = useAct(({ cid, ok }: { cid: number; ok: boolean }) =>
    materialsApi.verify(
      cid,
      ok ? 'verified' : 'rejected',
      ok ? undefined : reason
    )
  )
  const hold = useAct(() => materialsApi.hold(id, reason))
  const close = useAct(({ hid, ok }: { hid: number; ok: boolean }) =>
    materialsApi.closeHold(hid, ok ? 'released' : 'rejected')
  )
  const receive = useAct(() => materialsApi.receive(id, today()))
  const issue = useAct(() =>
    materialsApi.issue({
      project_id: projectId,
      heat_id: id,
      node_id: node?.id,
    })
  )

  if (!heatId)
    return (
      <RecordSheet open onClose={onClose} title={t('materials.new_heat')}>
        <NewHeat projectId={projectId} onDone={onClose} />
      </RecordSheet>
    )
  if (!heat) return null
  return (
    <RecordSheet
      open
      wide
      onClose={onClose}
      title={`${heat.heat_number} · ${heat.material_grade}`}
      subtitle={[heat.product_form, heat.receipt_code, heat.supplied_by]
        .filter(Boolean)
        .join(' · ')}
      badges={
        <>
          <StatusBadge status={heat.status} />
          <StatusBadge status={heat.certificate_status} />
        </>
      }
      record={{ projectId, entityType: 'material_heat', entityId: heat.id }}
      tabs={{
        [t('materials.where_used')]: (
          <ul className='grid gap-1 text-sm'>
            {(heat.issues ?? []).map((i) => (
              <li key={i.id}>
                {i.issued_on} · {i.node_path}
                {i.item_tag ? ` · ${i.item_tag}` : ''}
                {i.quantity ? ` · ${i.quantity} ${i.uom ?? ''}` : ''}
              </li>
            ))}
            {!heat.issues?.length ? (
              <li className='text-muted-foreground'>
                {t('materials.not_issued')}
              </li>
            ) : null}
          </ul>
        ),
      }}
    >
      <div className='grid gap-4 text-sm'>
        {heat.status === 'expected' && can(session, 'materials.update') ? (
          <Button
            size='sm'
            className='w-fit'
            onClick={() => receive.mutate(undefined)}
          >
            {t('materials.receive_today')}
          </Button>
        ) : null}
        <section className='grid gap-2'>
          <h4 className='font-semibold'>{t('materials.certificates')}</h4>
          {(heat.certificates ?? []).map((c) => (
            <div key={c.id} className='flex flex-wrap items-center gap-2'>
              <span className='font-mono'>{c.certificate_number}</span>
              <span className='text-muted-foreground'>
                {c.certificate_type}
              </span>
              <StatusBadge status={c.status} />
              {c.status === 'pending_verification' &&
              can(session, 'materials.approve') ? (
                <>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => verify.mutate({ cid: c.id, ok: true })}
                  >
                    {t('materials.verify')}
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    disabled={!reason}
                    onClick={() => verify.mutate({ cid: c.id, ok: false })}
                  >
                    {t('materials.reject')}
                  </Button>
                </>
              ) : null}
            </div>
          ))}
          {can(session, 'materials.upload') ? (
            <div className='flex gap-2'>
              <Input
                placeholder={t('materials.cert_number')}
                value={cert}
                onChange={(e) => setCert(e.target.value)}
              />
              <Button
                size='sm'
                disabled={!cert}
                onClick={() =>
                  addCert.mutate(undefined, { onSuccess: () => setCert('') })
                }
              >
                {t('materials.add_cert')}
              </Button>
            </div>
          ) : null}
          <p className='text-xs text-muted-foreground'>
            {t('materials.cert_help')}
          </p>
        </section>
        <section className='grid gap-2'>
          <h4 className='font-semibold'>{t('materials.holds')}</h4>
          {(heat.holds ?? []).map((h) => (
            <div key={h.id} className='flex flex-wrap items-center gap-2'>
              <span className='font-mono'>{h.code}</span>
              <span>{h.reason}</span>
              <StatusBadge status={h.status} />
              {h.status === 'open' && can(session, 'materials.approve') ? (
                <>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => close.mutate({ hid: h.id, ok: true })}
                  >
                    {t('materials.release')}
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => close.mutate({ hid: h.id, ok: false })}
                  >
                    {t('materials.reject')}
                  </Button>
                </>
              ) : null}
            </div>
          ))}
          {can(session, 'materials.review') ? (
            <div className='flex gap-2'>
              <Input
                placeholder={t('materials.reason')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <Button
                size='sm'
                variant='outline'
                disabled={!reason}
                onClick={() => hold.mutate(undefined)}
              >
                {t('materials.quarantine')}
              </Button>
            </div>
          ) : null}
        </section>
        {heat.status === 'available' && can(session, 'materials.create') ? (
          <section className='grid gap-2'>
            <h4 className='font-semibold'>{t('materials.issue')}</h4>
            <NodePicker projectId={projectId} value={node} onChange={setNode} />
            <Button
              size='sm'
              className='w-fit'
              disabled={!node}
              onClick={() =>
                issue.mutate(undefined, {
                  onSuccess: () => toast.success(t('materials.issued')),
                })
              }
            >
              {t('materials.issue')}
            </Button>
          </section>
        ) : null}
      </div>
    </RecordSheet>
  )
}
