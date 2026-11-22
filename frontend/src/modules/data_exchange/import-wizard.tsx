import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, FlaskConical, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  type ImportReport,
  type ImporterInfo,
  type Preview,
  postForm,
} from './api'

const NONE = '__none__'
const STEPS = ['upload', 'map', 'dry_run', 'apply'] as const
type Step = (typeof STEPS)[number]

function Steps({ step }: { step: Step }) {
  const { t } = useTranslation()
  const at = STEPS.indexOf(step)
  return (
    <ol className='flex flex-wrap gap-2 text-xs'>
      {STEPS.map((s, i) => (
        <li
          key={s}
          className={cn(
            'rounded-full border px-3 py-1',
            i === at && 'border-primary bg-primary/10 font-medium',
            i < at && 'text-muted-foreground'
          )}
        >
          {i + 1}. {t(`data.step.${s}`)}
        </li>
      ))}
    </ol>
  )
}

function Report({ report }: { report: ImportReport }) {
  const { t } = useTranslation()
  const errors = report.errors ?? []
  const warnings = report.warnings ?? []
  const counts: [string, number][] = [
    ['data.created', report.created],
    ['data.updated', report.updated],
    ['data.unchanged', report.unchanged],
    ['data.skipped', report.skipped],
  ]
  return (
    <div className='grid gap-3' data-testid='import-report'>
      <div className='flex flex-wrap gap-3'>
        <span className='text-sm font-medium'>
          {report.dry_run ? t('data.dry_run_result') : t('data.applied_result')}
          {' · '}
          {t('data.rows', { count: report.rows })}
        </span>
        {counts.map(([key, n]) => (
          <span key={key} className='rounded-md bg-muted px-2 py-0.5 text-sm'>
            {t(key)}: <strong className='tabular-nums'>{n}</strong>
          </span>
        ))}
      </div>
      {errors.length ? (
        <ul className='max-h-48 list-disc overflow-y-auto ps-5 text-sm text-red-600'>
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
      {warnings.length ? (
        <ul className='max-h-40 list-disc overflow-y-auto ps-5 text-sm text-amber-600'>
          {warnings.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** Upload → preview → map columns → dry run → apply, for any registered importer. */
export function ImportWizard({
  importers,
  projectId,
}: {
  importers: ImporterInfo[]
  projectId?: number
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState(importers[0]?.name ?? '')
  const importer = importers.find((i) => i.name === name)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [options, setOptions] = useState<Record<string, string>>({})
  const [report, setReport] = useState<ImportReport | null>(null)
  const [busy, setBusy] = useState(false)
  const step: Step = !preview
    ? 'upload'
    : !report
      ? 'map'
      : report.dry_run
        ? 'dry_run'
        : 'apply'

  const restart = (next = name) => {
    setName(next)
    setFile(null)
    setPreview(null)
    setMapping({})
    setReport(null)
    setOptions({})
  }

  const readFile = async (f: File) => {
    setFile(f)
    setReport(null)
    const form = new FormData()
    form.set('file', f)
    setBusy(true)
    try {
      const result = await postForm<Preview>(
        `/api/v1/data/import/${name}/preview`,
        form
      )
      setPreview(result)
      setMapping(result.mapping)
    } catch (error) {
      handleServerError(error)
    } finally {
      setBusy(false)
    }
  }

  const run = async (dryRun: boolean) => {
    if (!file || !importer) return
    const form = new FormData()
    form.set('file', file)
    form.set('mapping', JSON.stringify(mapping))
    form.set('dry_run', String(dryRun))
    if (Object.keys(options).length)
      form.set('options', JSON.stringify(options))
    if (projectId && importer.project_scoped)
      form.set('project_id', String(projectId))
    setBusy(true)
    try {
      const result = await postForm<ImportReport>(
        `/api/v1/data/import/${importer.name}`,
        form
      )
      setReport(result)
      if (!dryRun) {
        toast.success(t('data.imported'))
        void queryClient.invalidateQueries()
      }
    } catch (error) {
      handleServerError(error)
    } finally {
      setBusy(false)
    }
  }

  if (!importers.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('data.no_importers')}</p>
    )
  const needsProject = importer?.project_scoped && !projectId
  const missing = (importer?.fields ?? []).filter(
    (f) => f.required && !mapping[f.key]
  )

  return (
    <div className='flex flex-col gap-4'>
      <Steps step={step} />
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>{t('data.step.upload')}</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-3 md:grid-cols-2'>
          <div className='grid gap-1'>
            <Label>{t('data.importer')}</Label>
            <Select value={name} onValueChange={(v) => restart(v)}>
              <SelectTrigger aria-label={t('data.importer')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {importers.map((i) => (
                  <SelectItem key={i.name} value={i.name}>
                    {i.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className='text-xs text-muted-foreground'>
              {importer?.description}
            </p>
          </div>
          <div className='grid gap-1'>
            <Label htmlFor='import-file'>{t('data.file')}</Label>
            <Input
              id='import-file'
              type='file'
              accept='.xlsx,.xlsm,.csv,.txt,.tsv'
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void readFile(f)
              }}
            />
            {needsProject ? (
              <p className='text-xs text-amber-600'>
                {t('data.needs_project')}
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {preview && importer ? (
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              {t('data.step.map')} ·{' '}
              <span className='font-normal text-muted-foreground'>
                {t('data.rows', { count: preview.rows })}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col gap-4'>
            <div className='grid gap-2 md:grid-cols-2 xl:grid-cols-3'>
              {importer.fields.map((f) => (
                <div key={f.key} className='grid gap-1'>
                  <Label className='text-xs'>
                    {f.label}
                    {f.required ? (
                      <span className='text-red-600'> *</span>
                    ) : null}
                  </Label>
                  <Select
                    value={mapping[f.key] || NONE}
                    onValueChange={(v) => {
                      const next = { ...mapping }
                      if (v === NONE) delete next[f.key]
                      else next[f.key] = v
                      setMapping(next)
                      setReport(null)
                    }}
                  >
                    <SelectTrigger
                      size='sm'
                      className='h-8'
                      aria-label={f.label}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>
                        {t('data.not_imported')}
                      </SelectItem>
                      {preview.columns.map((c) => (
                        <SelectItem key={c} value={c}>
                          {c}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
              {Object.entries(importer.options).map(([key, choices]) => (
                <div key={key} className='grid gap-1'>
                  <Label className='text-xs'>
                    {t(`data.option.${key}`, key)}
                  </Label>
                  <Select
                    value={options[key] ?? choices[0]}
                    onValueChange={(v) => setOptions({ ...options, [key]: v })}
                  >
                    <SelectTrigger size='sm' className='h-8'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {choices.map((c) => (
                        <SelectItem key={c} value={c}>
                          {t(`data.choice.${c}`, c)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
            <div className='overflow-auto rounded-md border'>
              <table className='w-full text-xs'>
                <thead className='bg-muted/60'>
                  <tr>
                    {preview.columns.map((c) => (
                      <th
                        key={c}
                        className='px-2 py-1 text-start font-semibold'
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.sample.map((row, i) => (
                    <tr key={i} className='border-t'>
                      {preview.columns.map((c) => (
                        <td key={c} className='px-2 py-1'>
                          {row[c] === null || row[c] === undefined
                            ? ''
                            : String(row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className='flex flex-wrap items-center gap-2'>
              {missing.length ? (
                <span className='text-sm text-red-600'>
                  {t('data.map_required', {
                    fields: missing.map((f) => f.label).join(', '),
                  })}
                </span>
              ) : null}
              <Button
                variant='outline'
                className='ms-auto'
                disabled={busy || !!missing.length || needsProject}
                onClick={() => void run(true)}
              >
                <FlaskConical /> {t('data.dry_run')}
              </Button>
              <Button
                disabled={
                  busy || !report?.dry_run || !!missing.length || needsProject
                }
                onClick={() => void run(false)}
              >
                <CheckCircle2 /> {t('data.apply')}
              </Button>
            </div>
            {report ? <Report report={report} /> : null}
            {report && !report.dry_run ? (
              <Button variant='ghost' onClick={() => restart()}>
                <Upload /> {t('data.another')}
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
