import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { NodeSelect } from '@/components/node-select'
import { Field } from '@/components/records/fields'
import { DUTIES, TYPES, useCreateScaffold, useWeatherEvent } from './api'

export function RequestScaffold({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const create = useCreateScaffold()
  const [nodeId, setNodeId] = useState<number | null>(null)
  const [custodian, setCustodian] = useState<number | null>(null)
  const [draft, setDraft] = useState({
    purpose: '',
    location_text: '',
    scaffold_type: 'independent',
    duty_class: 'medium',
    required_by: '',
    length_m: '',
    width_m: '',
    height_m: '',
    lifts: '',
  })
  const text = (key: keyof typeof draft) => ({
    value: draft[key],
    onChange: (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >
    ) => setDraft({ ...draft, [key]: e.target.value }),
  })
  const num = (v: string) => (v ? Number(v) : null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('scaffolds.request')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-scaffold'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            if (!nodeId) return
            create.mutate(
              {
                project_id: projectId,
                node_id: nodeId,
                purpose: draft.purpose || null,
                location_text: draft.location_text || null,
                scaffold_type: draft.scaffold_type as never,
                duty_class: draft.duty_class as never,
                required_by: draft.required_by || null,
                custodian_id: custodian,
                dimensions: {
                  length_m: num(draft.length_m),
                  width_m: num(draft.width_m),
                  height_m: num(draft.height_m),
                  lifts: num(draft.lifts),
                },
              },
              {
                onSuccess: (made) => {
                  onClose()
                  onCreated(made.id)
                },
              }
            )
          }}
        >
          <Field label={t('scaffolds.location')}>
            <NodeSelect
              projectId={projectId}
              value={nodeId}
              onChange={setNodeId}
            />
          </Field>
          <Field label={t('scaffolds.location_detail')}>
            <Input {...text('location_text')} />
          </Field>
          <Field label={t('scaffolds.purpose')}>
            <Textarea {...text('purpose')} />
          </Field>
          <div className='grid grid-cols-2 gap-3'>
            <Field label={t('scaffolds.type')}>
              <NativeSelect values={TYPES} {...text('scaffold_type')} />
            </Field>
            <Field label={t('scaffolds.duty')}>
              <NativeSelect values={DUTIES} {...text('duty_class')} />
            </Field>
            <Field label={t('scaffolds.required_by')}>
              <Input type='date' {...text('required_by')} />
            </Field>
            <Field label={t('scaffolds.custodian')}>
              <UserSelect value={custodian} onChange={setCustodian} />
            </Field>
          </div>
          <div className='grid grid-cols-4 gap-2'>
            <Field label='L (m)'>
              <Input type='number' step='0.1' {...text('length_m')} />
            </Field>
            <Field label='W (m)'>
              <Input type='number' step='0.1' {...text('width_m')} />
            </Field>
            <Field label='H (m)'>
              <Input type='number' step='0.1' {...text('height_m')} />
            </Field>
            <Field label={t('scaffolds.lifts')}>
              <Input type='number' {...text('lifts')} />
            </Field>
          </div>
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='new-scaffold'
            disabled={!nodeId || create.isPending}
          >
            {t('scaffolds.request')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function Weather({
  projectId,
  onClose,
}: {
  projectId: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const weather = useWeatherEvent()
  const [nodeId, setNodeId] = useState<number | null>(null)
  const [description, setDescription] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('scaffolds.weather_event')}</DialogTitle>
        </DialogHeader>
        <p className='text-sm text-muted-foreground'>
          {t('scaffolds.weather_help')}
        </p>
        <Field label={t('scaffolds.area_optional')}>
          <NodeSelect
            projectId={projectId}
            value={nodeId}
            onChange={setNodeId}
          />
        </Field>
        <Field label={t('scaffolds.what_happened')}>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <DialogFooter>
          <Button
            disabled={!description || weather.isPending}
            onClick={() =>
              weather.mutate(
                {
                  project_id: projectId,
                  node_id: nodeId ?? undefined,
                  description,
                },
                { onSuccess: onClose }
              )
            }
          >
            {t('scaffolds.record')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
