import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import { CriterionPicker } from '@/modules/inspections/criterion-picker'
import {
  type AsBuilt,
  type AsBuiltBody,
  type VerifyBody,
  useCreateRecord,
  useSignRecord,
  useSurvey,
  useVerify,
} from './api'
import { CAPTURE_METHODS, SOURCE_KINDS } from './as-built'

const orNull = (v: string) => (v.trim() === '' ? null : v.trim())

function Text({
  id,
  label,
  value,
  onChange,
  type,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
}) {
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

export function CreateRecordDialog({
  projectId,
  onClose,
}: {
  projectId: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreateRecord()
  const [f, setF] = useState({
    title: '',
    discipline: '',
    location: '',
    instrument: '',
    calibration_ref: '',
    measured_value: '',
    deviation_value: '',
    source_ref: '',
    notes: '',
  })
  const [capture, setCapture] = useState<AsBuiltBody['capture_method']>('manual')
  const [source, setSource] = useState<AsBuiltBody['source_kind']>('manual')
  const [criterionId, setCriterionId] = useState<number | null>(null)
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{t('as_built.new')}</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3 sm:grid-cols-2'>
          <div className='sm:col-span-2'>
            <Text
              id='ab-title'
              label={t('as_built.title')}
              value={f.title}
              onChange={(title) => set({ title })}
            />
          </div>
          <Text
            id='ab-discipline'
            label={t('as_built.discipline')}
            value={f.discipline}
            onChange={(discipline) => set({ discipline })}
          />
          <Text
            id='ab-location'
            label={t('as_built.location')}
            value={f.location}
            onChange={(location) => set({ location })}
          />
          <div className='grid gap-1.5'>
            <Label htmlFor='ab-capture'>{t('as_built.capture_method')}</Label>
            <NativeSelect
              id='ab-capture'
              options={CAPTURE_METHODS.map((m) => ({
                value: m,
                label: t(`as_built.capture.${m}`),
              }))}
              value={capture}
              onChange={(e) =>
                setCapture(e.target.value as AsBuiltBody['capture_method'])
              }
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='ab-source'>{t('as_built.source_kind')}</Label>
            <NativeSelect
              id='ab-source'
              options={SOURCE_KINDS.map((s) => ({
                value: s,
                label: t(`as_built.source.${s}`),
              }))}
              value={source}
              onChange={(e) =>
                setSource(e.target.value as AsBuiltBody['source_kind'])
              }
            />
          </div>
          <Text
            id='ab-instrument'
            label={t('as_built.instrument')}
            value={f.instrument}
            onChange={(instrument) => set({ instrument })}
          />
          <Text
            id='ab-calibration'
            label={t('as_built.calibration_ref')}
            value={f.calibration_ref}
            onChange={(calibration_ref) => set({ calibration_ref })}
          />
          <div className='grid gap-1.5 sm:col-span-2'>
            <Label>{t('as_built.criterion')}</Label>
            <CriterionPicker
              projectId={projectId}
              value={criterionId}
              onChange={(c) => setCriterionId(c?.id ?? null)}
            />
          </div>
          <Text
            id='ab-measured'
            label={t('as_built.measured_value')}
            value={f.measured_value}
            onChange={(measured_value) => set({ measured_value })}
          />
          <Text
            id='ab-deviation'
            label={t('as_built.deviation_value')}
            value={f.deviation_value}
            onChange={(deviation_value) => set({ deviation_value })}
          />
          <div className='sm:col-span-2'>
            <Text
              id='ab-source-ref'
              label={t('as_built.source_ref')}
              value={f.source_ref}
              onChange={(source_ref) => set({ source_ref })}
            />
          </div>
          <div className='grid gap-1.5 sm:col-span-2'>
            <Label htmlFor='ab-notes'>{t('as_built.notes')}</Label>
            <Textarea
              id='ab-notes'
              value={f.notes}
              onChange={(e) => set({ notes: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!f.title.trim() || create.isPending}
            onClick={() =>
              create.mutate(
                {
                  project_id: projectId,
                  title: f.title.trim(),
                  discipline: orNull(f.discipline),
                  location: orNull(f.location),
                  capture_method: capture,
                  accuracy_class: 'standard',
                  source_kind: source,
                  instrument: orNull(f.instrument),
                  calibration_ref: orNull(f.calibration_ref),
                  criterion_id: criterionId,
                  measured_value: orNull(f.measured_value),
                  deviation_value: orNull(f.deviation_value),
                  source_ref: orNull(f.source_ref),
                  notes: orNull(f.notes),
                  supplementary: {},
                },
                {
                  onSuccess: () => {
                    toast.success(t('as_built.created'))
                    onClose()
                  },
                }
              )
            }
          >
            {t('as_built.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type Props = { record: AsBuilt; onClose: () => void }

/** Record a survey. With no measured value the stored one is judged again. */
export function SurveyDialog({ record, onClose }: Props) {
  const { t } = useTranslation()
  const survey = useSurvey(record.id)
  const [f, setF] = useState({
    measured_value: '',
    deviation_value: '',
    accuracy_value: '',
    accuracy_unit: '',
    surveyed_on: '',
    notes: '',
  })
  const set = (patch: Partial<typeof f>) => setF({ ...f, ...patch })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('as_built.survey_title')}</DialogTitle>
          <DialogDescription>{t('as_built.survey_help')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-3 sm:grid-cols-2'>
          <Text
            id='sv-measured'
            label={t('as_built.measured_value')}
            value={f.measured_value}
            onChange={(measured_value) => set({ measured_value })}
          />
          <Text
            id='sv-deviation'
            label={t('as_built.deviation_value')}
            value={f.deviation_value}
            onChange={(deviation_value) => set({ deviation_value })}
          />
          <Text
            id='sv-accuracy'
            label={t('as_built.accuracy_value')}
            value={f.accuracy_value}
            onChange={(accuracy_value) => set({ accuracy_value })}
          />
          <Text
            id='sv-accuracy-unit'
            label={t('as_built.accuracy_unit')}
            value={f.accuracy_unit}
            onChange={(accuracy_unit) => set({ accuracy_unit })}
          />
          <Text
            id='sv-date'
            type='date'
            label={t('as_built.surveyed_on')}
            value={f.surveyed_on}
            onChange={(surveyed_on) => set({ surveyed_on })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='sv-notes'>{t('as_built.notes')}</Label>
          <Textarea
            id='sv-notes'
            value={f.notes}
            onChange={(e) => set({ notes: e.target.value })}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={survey.isPending}
            onClick={() =>
              survey.mutate(
                {
                  measured_value: orNull(f.measured_value),
                  deviation_value: orNull(f.deviation_value),
                  accuracy_value: orNull(f.accuracy_value),
                  accuracy_unit: orNull(f.accuracy_unit),
                  surveyed_on: orNull(f.surveyed_on),
                  notes: orNull(f.notes),
                },
                {
                  onSuccess: () => {
                    toast.success(t('as_built.surveyed'))
                    onClose()
                  },
                }
              )
            }
          >
            {t('as_built.survey')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Verify a surveyed record; an out-of-tolerance result raises a report of the chosen severity (default major). */
export function VerifyDialog({ record, onClose }: Props) {
  const { t } = useTranslation()
  const verify = useVerify(record.id)
  const [notes, setNotes] = useState('')
  const [severity, setSeverity] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('as_built.verify_title')}</DialogTitle>
          <DialogDescription>{t('as_built.verify_help')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-1.5'>
          <Label htmlFor='vf-severity'>{t('as_built.report_severity')}</Label>
          <NativeSelect
            id='vf-severity'
            placeholder={t('as_built.severity_default')}
            options={['minor', 'major', 'critical'].map((s) => ({
              value: s,
              label: t(`as_built.severity.${s}`),
            }))}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='vf-notes'>{t('as_built.verifier_notes')}</Label>
          <Textarea
            id='vf-notes'
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={verify.isPending}
            onClick={() =>
              verify.mutate(
                {
                  notes: orNull(notes),
                  severity: (severity || null) as VerifyBody['severity'],
                },
                {
                  onSuccess: () => {
                    toast.success(t('as_built.verified'))
                    onClose()
                  },
                }
              )
            }
          >
            {t('as_built.verify')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Sign the legal-record attestation, or decline it (the record then stays verified). */
export function SignDialog({ record, onClose }: Props) {
  const { t } = useTranslation()
  const sign = useSignRecord(record.id)
  const [attest, setAttest] = useState(true)
  const [notes, setNotes] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('as_built.sign_title')}</DialogTitle>
          <DialogDescription>{t('as_built.sign_help')}</DialogDescription>
        </DialogHeader>
        <label className='flex items-start gap-2 rounded-md border bg-muted/40 p-3 text-sm'>
          <Checkbox
            checked={attest}
            onCheckedChange={(v) => setAttest(v === true)}
            className='mt-0.5'
          />
          <span>{t('as_built.attest', { number: record.number })}</span>
        </label>
        <div className='grid gap-1.5'>
          <Label htmlFor='sg-notes'>{t('as_built.signature_notes')}</Label>
          <Textarea
            id='sg-notes'
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={sign.isPending}
            onClick={() =>
              sign.mutate(
                { valid: attest, notes: orNull(notes) },
                {
                  onSuccess: () => {
                    toast.success(
                      t(attest ? 'as_built.signed' : 'as_built.declined')
                    )
                    onClose()
                  },
                }
              )
            }
          >
            {attest ? t('as_built.sign') : t('as_built.decline')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
