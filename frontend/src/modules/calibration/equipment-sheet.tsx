import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import { StatusBadge } from '@/components/records/status-badge'
import {
  EQUIPMENT_TYPES,
  type Equipment,
  type EquipmentUpdate,
  NEXT,
  useAddCertificate,
  useCertificates,
  useEquipmentStatus,
  useHistory,
  useSaveEquipment,
} from './api'

const today = () => new Date().toISOString().slice(0, 10)

function Certificates({
  projectId,
  equipment,
}: {
  projectId: number
  equipment: Equipment
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: certs = [] } = useCertificates(equipment.id)
  const add = useAddCertificate(projectId)
  const [number, setNumber] = useState('')
  const [calibratedOn, setCalibratedOn] = useState(today())
  const [facility, setFacility] = useState('')
  return (
    <div className='grid gap-4'>
      {can(session, 'calibration.upload') ? (
        <form
          className='grid gap-2 rounded-md border p-3 sm:grid-cols-4'
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(
              {
                id: equipment.id,
                body: {
                  certificate_number: number,
                  calibrated_on: calibratedOn,
                  facility: facility || null,
                  result: 'pass',
                },
              },
              {
                onSuccess: () => {
                  setNumber('')
                  toast.success(t('calibration.cert_saved'))
                },
              }
            )
          }}
        >
          <Field label={t('calibration.cert_number')}>
            <Input
              required
              value={number}
              onChange={(e) => setNumber(e.target.value)}
            />
          </Field>
          <Field label={t('calibration.calibrated_on')}>
            <Input
              type='date'
              required
              max={today()}
              value={calibratedOn}
              onChange={(e) => setCalibratedOn(e.target.value)}
            />
          </Field>
          <Field label={t('calibration.facility')}>
            <Input
              value={facility}
              onChange={(e) => setFacility(e.target.value)}
            />
          </Field>
          <div className='flex items-end'>
            <Button type='submit' size='sm' disabled={add.isPending}>
              {t('calibration.record_cert')}
            </Button>
          </div>
          <p className='text-xs text-muted-foreground sm:col-span-4'>
            {t('calibration.cert_help')}
          </p>
        </form>
      ) : null}
      <table className='w-full text-sm'>
        <thead className='text-left text-xs text-muted-foreground'>
          <tr>
            <th>{t('calibration.cert_number')}</th>
            <th>{t('calibration.calibrated_on')}</th>
            <th>{t('calibration.expires_on')}</th>
            <th>{t('calibration.facility')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {certs.map((c) => (
            <tr key={c.id} className='border-t'>
              <td className='py-1.5 font-mono'>{c.certificate_number}</td>
              <td>{c.calibrated_on}</td>
              <td>{c.expires_on}</td>
              <td>{c.facility}</td>
              <td>
                {c.is_active ? (
                  <StatusBadge status='active' />
                ) : (
                  <span className='text-xs text-muted-foreground'>
                    {t('calibration.superseded')}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!certs.length ? (
        <p className='text-sm text-muted-foreground'>
          {t('calibration.no_certs')}
        </p>
      ) : null}
    </div>
  )
}

function History({ id }: { id: number }) {
  const { data = [] } = useHistory(id)
  return (
    <ol className='grid gap-2 text-sm'>
      {data.map((h, i) => (
        <li key={i} className='border-b pb-1'>
          {h.from_status ? `${statusLabel(h.from_status)} → ` : ''}
          <strong>{statusLabel(h.to_status)}</strong>{' '}
          <span className='text-xs text-muted-foreground'>
            {h.changed_at?.slice(0, 16).replace('T', ' ')}
          </span>
          {h.note ? <p className='text-muted-foreground'>{h.note}</p> : null}
        </li>
      ))}
    </ol>
  )
}

export function EquipmentSheet({
  projectId,
  equipment,
  onClose,
}: {
  projectId: number
  equipment?: Equipment
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const save = useSaveEquipment(projectId)
  const status = useEquipmentStatus(projectId)
  const [form, setForm] = useState<EquipmentUpdate>(() => ({
    name: equipment?.name ?? '',
    code: equipment?.code ?? null,
    equipment_type: (equipment?.equipment_type ?? 'other') as never,
    requires_calibration: equipment?.requires_calibration ?? true,
    manufacturer: equipment?.manufacturer ?? null,
    model: equipment?.model ?? null,
    serial_number: equipment?.serial_number ?? null,
    custodian_id: equipment?.custodian_id ?? null,
    location: equipment?.location ?? null,
    interval_days: equipment?.interval_days ?? 365,
    reminder_days: equipment?.reminder_days ?? 14,
    notes: equipment?.notes ?? null,
  }))
  const editable = can(
    session,
    equipment ? 'calibration.update' : 'calibration.create'
  )
  const set = (patch: Partial<EquipmentUpdate>) =>
    setForm((f) => ({ ...f, ...patch }))
  const text = (key: keyof EquipmentUpdate) => ({
    value: (form[key] as string | null | undefined) ?? '',
    disabled: !editable,
    onChange: (e: { target: { value: string } }) =>
      set({ [key]: e.target.value || null }),
  })

  const details = (
    <form
      className='grid gap-3 sm:grid-cols-2'
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(
          { id: equipment?.id, body: form },
          {
            onSuccess: () => {
              toast.success(t('calibration.saved'))
              if (!equipment) onClose()
            },
          }
        )
      }}
    >
      <Field label={t('calibration.name')} className='sm:col-span-2'>
        <Input required {...text('name')} />
      </Field>
      <Field label={t('calibration.code')}>
        <Input placeholder={t('calibration.code_auto')} {...text('code')} />
      </Field>
      <Field label={t('calibration.type')}>
        <NativeSelect
          values={EQUIPMENT_TYPES}
          value={form.equipment_type ?? 'other'}
          disabled={!editable}
          onChange={(e) => set({ equipment_type: e.target.value as never })}
        />
      </Field>
      <Field label={t('calibration.manufacturer')}>
        <Input {...text('manufacturer')} />
      </Field>
      <Field label={t('calibration.model')}>
        <Input {...text('model')} />
      </Field>
      <Field label={t('calibration.serial')}>
        <Input {...text('serial_number')} />
      </Field>
      <Field label={t('calibration.location')}>
        <Input {...text('location')} />
      </Field>
      <Field label={t('calibration.custodian')}>
        <UserSelect
          value={form.custodian_id}
          onChange={(id) => set({ custodian_id: id })}
        />
      </Field>
      <Field label={t('calibration.interval')}>
        <Input
          type='number'
          min={1}
          value={form.interval_days ?? 365}
          disabled={!editable}
          onChange={(e) => set({ interval_days: Number(e.target.value) })}
        />
      </Field>
      <Field label={t('calibration.reminder')}>
        <Input
          type='number'
          min={0}
          value={form.reminder_days ?? 14}
          disabled={!editable}
          onChange={(e) => set({ reminder_days: Number(e.target.value) })}
        />
      </Field>
      <label className='flex items-center gap-2 self-end text-sm'>
        <input
          type='checkbox'
          checked={!!form.requires_calibration}
          disabled={!editable}
          onChange={(e) => set({ requires_calibration: e.target.checked })}
        />
        {t('calibration.requires')}
      </label>
      <Field label={t('calibration.notes')} className='sm:col-span-2'>
        <Textarea rows={3} {...text('notes')} />
      </Field>
      {equipment ? (
        <dl className='grid grid-cols-2 gap-1 text-sm sm:col-span-2'>
          <dt className='text-muted-foreground'>
            {t('calibration.last_calibrated')}
          </dt>
          <dd>{equipment.last_calibrated_on ?? '–'}</dd>
          <dt className='text-muted-foreground'>{t('calibration.due')}</dt>
          <dd>{equipment.due_on ?? '–'}</dd>
        </dl>
      ) : null}
      {editable ? (
        <div className='flex gap-2 sm:col-span-2'>
          <Button type='submit' size='sm' disabled={save.isPending}>
            {t('calibration.save')}
          </Button>
        </div>
      ) : null}
      {equipment && can(session, 'calibration.transition') ? (
        <div className='flex flex-wrap gap-2 border-t pt-3 sm:col-span-2'>
          {NEXT[equipment.stored_status]?.map((s) => (
            <Button
              key={s}
              type='button'
              size='sm'
              variant='outline'
              disabled={status.isPending}
              onClick={() => status.mutate({ id: equipment.id, status: s })}
            >
              {t(`calibration.to.${s}`)}
            </Button>
          ))}
        </div>
      ) : null}
    </form>
  )

  return (
    <RecordSheet
      open
      onClose={onClose}
      title={
        equipment ? `${equipment.code} ${equipment.name}` : t('calibration.new')
      }
      subtitle={equipment?.serial_number ?? undefined}
      badges={equipment ? <StatusBadge status={equipment.status} /> : null}
      record={
        equipment
          ? {
              projectId,
              entityType: 'calibration_equipment',
              entityId: equipment.id,
            }
          : undefined
      }
      tabs={
        equipment
          ? {
              [t('calibration.certificates')]: (
                <Certificates projectId={projectId} equipment={equipment} />
              ),
              [t('calibration.history')]: <History id={equipment.id} />,
            }
          : undefined
      }
    >
      {details}
    </RecordSheet>
  )
}
