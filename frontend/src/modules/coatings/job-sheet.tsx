import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import { Field } from '@/components/records/fields'
import { RecordSheet } from '@/components/records/record-sheet'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type JobDetail,
  type Stage,
  useAddDft,
  useAddEnvironment,
  useJob,
  useRelease,
  useUpdateStage,
} from './api'
import {
  type DftRule,
  RULES,
  dewPoint,
  dftStats,
  environmentCheck,
  parseReadings,
} from './calc'

const ids = (text: string) =>
  text
    .split(/[\s,;]+/)
    .map(Number)
    .filter((n) => Number.isInteger(n) && n > 0)

function Verdict({ passed, children }: { passed: boolean; children: string }) {
  return (
    <span
      className={cn(
        'rounded px-2 py-0.5 text-xs font-semibold',
        passed
          ? 'bg-green-500/15 text-green-700 dark:text-green-400'
          : 'bg-red-500/15 text-red-700 dark:text-red-400'
      )}
    >
      {children}
    </span>
  )
}

function EnvironmentForm({
  job,
  stage,
  margin,
}: {
  job: JobDetail
  stage: Stage
  margin: number
}) {
  const { t } = useTranslation()
  const add = useAddEnvironment(job.id)
  const [air, setAir] = useState('')
  const [surface, setSurface] = useState('')
  const [rh, setRh] = useState('')
  const [equipment, setEquipment] = useState('')
  const dew =
    air && rh && Number(rh) > 0 && Number(rh) <= 100
      ? dewPoint(Number(air), Number(rh))
      : null
  const check =
    dew != null && surface
      ? environmentCheck(Number(surface), dew, margin)
      : null
  return (
    <form
      className='grid gap-2 rounded-md border p-3'
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate(
          {
            stage_id: stage.id,
            air_temp_c: Number(air),
            surface_temp_c: Number(surface),
            rh_pct: Number(rh),
            equipment_ids: ids(equipment),
          },
          {
            onSuccess: () => {
              setSurface('')
            },
          }
        )
      }}
    >
      <h4 className='text-sm font-semibold'>{t('coatings.environment')}</h4>
      <div className='grid grid-cols-4 gap-2'>
        <Field label={t('coatings.air_temp')}>
          <Input
            type='number'
            step='0.1'
            required
            value={air}
            onChange={(e) => setAir(e.target.value)}
          />
        </Field>
        <Field label={t('coatings.surface_temp')}>
          <Input
            type='number'
            step='0.1'
            required
            value={surface}
            onChange={(e) => setSurface(e.target.value)}
          />
        </Field>
        <Field label={t('coatings.rh')}>
          <Input
            type='number'
            step='0.1'
            min={1}
            max={100}
            required
            value={rh}
            onChange={(e) => setRh(e.target.value)}
          />
        </Field>
        <Field label={t('coatings.equipment')}>
          <Input
            placeholder='12, 15'
            value={equipment}
            onChange={(e) => setEquipment(e.target.value)}
          />
        </Field>
      </div>
      <div className='flex items-center gap-2 text-sm'>
        {dew != null ? (
          <span>
            {t('coatings.dew_point')} {dew} °C
          </span>
        ) : null}
        {check ? (
          <Verdict passed={check.passed}>
            {`${check.margin} °C above dew point (needs ${margin})`}
          </Verdict>
        ) : null}
        <Button
          size='sm'
          type='submit'
          className='ms-auto'
          disabled={add.isPending}
        >
          {t('coatings.record')}
        </Button>
      </div>
    </form>
  )
}

function DftForm({ job, stage }: { job: JobDetail; stage: Stage }) {
  const { t } = useTranslation()
  const add = useAddDft(job.id)
  const [text, setText] = useState('')
  const [rule, setRule] = useState<DftRule>(job.dft_rule as DftRule)
  const [equipment, setEquipment] = useState('')
  const [location, setLocation] = useState('')
  const readings = parseReadings(text)
  const stats =
    stage.dft_min_um != null
      ? dftStats(readings, stage.dft_min_um, stage.dft_max_um, rule)
      : null
  return (
    <form
      className='grid gap-2 rounded-md border p-3'
      onSubmit={(e) => {
        e.preventDefault()
        add.mutate(
          {
            stage_id: stage.id,
            readings,
            rule,
            location: location || null,
            equipment_ids: ids(equipment),
          },
          { onSuccess: () => setText('') }
        )
      }}
    >
      <h4 className='text-sm font-semibold'>
        {t('coatings.dft')} · {stage.dft_min_um}–{stage.dft_max_um ?? '∞'} µm
      </h4>
      <Textarea
        aria-label={t('coatings.readings')}
        placeholder={t('coatings.readings_placeholder')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className='grid grid-cols-3 gap-2'>
        <Field label={t('coatings.rule')}>
          <NativeSelect
            options={RULES.map((r) => ({ value: r, label: r }))}
            value={rule}
            onChange={(e) => setRule(e.target.value as DftRule)}
          />
        </Field>
        <Field label={t('coatings.location')}>
          <Input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </Field>
        <Field label={t('coatings.equipment')}>
          <Input
            placeholder='7'
            value={equipment}
            onChange={(e) => setEquipment(e.target.value)}
          />
        </Field>
      </div>
      {stats ? (
        <div className='grid gap-1 text-sm'>
          <div className='flex flex-wrap items-center gap-3'>
            <span>n {stats.count}</span>
            <span>mean {stats.mean}</span>
            <span>min {stats.minimum}</span>
            <span>max {stats.maximum}</span>
            <span>{stats.pctWithin}% in range</span>
            <Verdict passed={stats.passed}>
              {stats.passed ? t('coatings.pass') : t('coatings.fail')}
            </Verdict>
          </div>
          {stats.failures.map((f) => (
            <p key={f} className='text-xs text-red-600'>
              {f}
            </p>
          ))}
        </div>
      ) : null}
      <Button
        size='sm'
        type='submit'
        className='justify-self-end'
        disabled={!readings.length || add.isPending}
      >
        {t('coatings.record')}
      </Button>
    </form>
  )
}

function StagePanel({ job, stage }: { job: JobDetail; stage: Stage }) {
  const { t } = useTranslation()
  const session = useSession()
  const update = useUpdateStage(job.id)
  const release = useRelease(job.id)
  const [batch, setBatch] = useState('')
  const editable = stage.status === 'pending' && can(session, 'coatings.update')
  const env = job.environment.filter((r) => r.stage_id === stage.id)
  const sets = job.dft_sets.filter((d) => d.stage_id === stage.id)
  return (
    <div className='grid gap-3'>
      <div className='flex items-center gap-2'>
        <h3 className='font-semibold'>{stage.name}</h3>
        <StatusBadge status={stage.status} />
        {stage.product ? (
          <span className='text-sm text-muted-foreground'>{stage.product}</span>
        ) : null}
      </div>
      {editable ? (
        <EnvironmentForm
          job={job}
          stage={stage}
          margin={job.system.dew_point_margin_c}
        />
      ) : null}
      {editable && stage.kind === 'coat' ? (
        <DftForm job={job} stage={stage} />
      ) : null}
      {stage.kind === 'surface_prep' ? (
        <Field
          label={`${t('coatings.profile')} (${job.system.profile_min_um ?? '–'}–${job.system.profile_max_um ?? '–'} µm)`}
        >
          <Input
            type='number'
            disabled={!editable}
            defaultValue={stage.measured_profile_um ?? ''}
            onBlur={(e) =>
              e.target.value &&
              update.mutate({
                stageId: stage.id,
                body: { measured_profile_um: Number(e.target.value) },
              })
            }
          />
        </Field>
      ) : (
        <Field label={t('coatings.batches')}>
          <div className='flex flex-wrap items-center gap-2 text-sm'>
            {stage.batch_numbers.map((b, i) => (
              <span key={i} className='rounded border px-2 font-mono'>
                {String(b.batch)}
              </span>
            ))}
            {editable ? (
              <form
                className='flex gap-1'
                onSubmit={(e) => {
                  e.preventDefault()
                  update.mutate(
                    {
                      stageId: stage.id,
                      body: {
                        batch_numbers: [
                          ...stage.batch_numbers.map((b) => ({
                            batch: String(b.batch),
                            product: (b.product as string | null) ?? null,
                          })),
                          { batch, product: stage.product },
                        ],
                      },
                    },
                    { onSuccess: () => setBatch('') }
                  )
                }}
              >
                <Input
                  className='h-8 w-32'
                  aria-label={t('coatings.batch')}
                  placeholder={t('coatings.batch')}
                  value={batch}
                  onChange={(e) => setBatch(e.target.value)}
                  required
                />
                <Button size='sm' variant='outline' type='submit'>
                  +
                </Button>
              </form>
            ) : null}
          </div>
        </Field>
      )}
      <table className='w-full text-xs'>
        <tbody>
          {env.map((r) => (
            <tr key={`e${r.id}`} className='border-t'>
              <td>{new Date(r.taken_at).toLocaleString()}</td>
              <td>
                air {r.air_temp_c} °C · surface {r.surface_temp_c} °C · RH{' '}
                {r.rh_pct}% · dew {r.dew_point_c} °C
              </td>
              <td className='text-right'>
                <Verdict passed={r.passed}>{`Δ ${r.margin_c} °C`}</Verdict>
              </td>
            </tr>
          ))}
          {sets.map((d) => (
            <tr key={`d${d.id}`} className='border-t'>
              <td>{new Date(d.taken_at).toLocaleString()}</td>
              <td>
                DFT n {d.count} · mean {d.mean} · min {d.minimum} · max{' '}
                {d.maximum} · {d.pct_within}% · {d.rule}
              </td>
              <td className='text-right'>
                <Verdict passed={d.passed}>
                  {d.passed ? t('coatings.pass') : t('coatings.fail')}
                </Verdict>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {stage.status === 'pending' && can(session, 'coatings.review') ? (
        <div className='flex gap-2'>
          <Button
            size='sm'
            onClick={() =>
              release.mutate({ stageId: stage.id, result: 'passed' })
            }
          >
            {t('coatings.release')}
          </Button>
          <Button
            size='sm'
            variant='outline'
            onClick={() =>
              release.mutate({ stageId: stage.id, result: 'failed' })
            }
          >
            {t('coatings.fail_hold_point')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export function JobSheet({
  id,
  onClose,
}: {
  id: number | null
  onClose: () => void
}) {
  const { data: job } = useJob(id)
  const [stageId, setStageId] = useState<number | null>(null)
  if (!id || !job) return null
  const current =
    job.stages.find((s) => s.id === stageId) ??
    job.stages.find((s) => s.status === 'pending') ??
    job.stages[job.stages.length - 1]
  return (
    <RecordSheet
      open
      onClose={onClose}
      wide
      title={`${job.code} · ${job.title}`}
      subtitle={`${job.system.code} ${job.system.name} · ${job.node_path ?? ''}`}
      badges={<StatusBadge status={job.status} />}
      record={{
        projectId: job.project_id,
        entityType: 'coating_job',
        entityId: job.id,
      }}
    >
      <div className='grid gap-4'>
        <ol className='flex flex-wrap gap-2'>
          {job.stages.map((s) => (
            <li key={s.id}>
              <button
                type='button'
                onClick={() => setStageId(s.id)}
                className={cn(
                  'rounded-md border px-2 py-1 text-xs',
                  s.id === current?.id && 'border-primary',
                  s.status === 'passed' && 'bg-green-500/15',
                  s.status === 'failed' && 'bg-red-500/15'
                )}
              >
                {s.seq + 1}. {s.name}
              </button>
            </li>
          ))}
        </ol>
        {current ? (
          <StagePanel key={current.id} job={job} stage={current} />
        ) : null}
      </div>
    </RecordSheet>
  )
}
