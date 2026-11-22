import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useProjects } from '@/modules/projects/api'
import { CheckCircle2, FileUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { statusLabel } from '@/components/records/status'
import {
  type ImportOptions,
  type ImportPreview,
  type ImportReport,
  contactKeys,
  previewImport,
  runImport,
} from './api'

const IGNORE = '__ignore__'
const NO_PROJECT = 'none'
const STEPS = ['upload', 'mapping', 'options', 'review', 'done'] as const
type Step = (typeof STEPS)[number]

function Report({ report }: { report: ImportReport }) {
  const { t } = useTranslation()
  const stats: [string, number][] = [
    [t('contacts.import.rows'), report.rows],
    [
      report.dry_run
        ? t('contacts.import.would_create')
        : t('contacts.import.created'),
      report.created,
    ],
    [
      report.dry_run
        ? t('contacts.import.would_update')
        : t('contacts.import.updated'),
      report.updated,
    ],
    [t('contacts.import.skipped'), report.skipped],
  ]
  return (
    <div className='grid gap-3'>
      <div className='grid grid-cols-4 gap-2'>
        {stats.map(([label, n]) => (
          <div key={label} className='rounded-md border p-2 text-center'>
            <div className='text-lg font-semibold tabular-nums'>{n}</div>
            <div className='text-xs text-muted-foreground'>{label}</div>
          </div>
        ))}
      </div>
      {report.duplicates?.length ? (
        <details className='rounded-md border p-2 text-sm'>
          <summary className='cursor-pointer font-medium'>
            {t('contacts.import.duplicates', {
              count: report.duplicates.length,
            })}
          </summary>
          <ul className='mt-1 max-h-32 list-disc overflow-y-auto ps-5 text-xs'>
            {report.duplicates.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {report.errors?.length ? (
        <details
          open
          className='rounded-md border border-red-500/40 p-2 text-sm'
        >
          <summary className='cursor-pointer font-medium text-red-600'>
            {t('contacts.import.errors', { count: report.errors.length })}
          </summary>
          <ul className='mt-1 max-h-32 list-disc overflow-y-auto ps-5 text-xs'>
            {report.errors.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

export function ImportWizard({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const current = useCurrentProject()
  const { data: projects = [] } = useProjects()
  const [step, setStep] = useState<Step>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [options, setOptions] = useState<ImportOptions>({
    mapping: {},
    on_duplicate: 'skip',
    dry_run: true,
    project_id: null,
    project_role: '',
  })
  const [report, setReport] = useState<ImportReport | null>(null)

  const attempt = async (work: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await work()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const upload = () =>
    attempt(async () => {
      if (!file) return
      const p = await previewImport(file)
      setPreview(p)
      setOptions((o) => ({ ...o, mapping: p.mapping }))
      setStep('mapping')
    })

  const run = (dry: boolean) =>
    attempt(async () => {
      if (!file) return
      const r = await runImport(file, { ...options, dry_run: dry })
      setReport(r)
      if (dry) setStep('review')
      else {
        setStep('done')
        toast.success(
          t('contacts.import.finished', {
            created: r.created,
            updated: r.updated,
          })
        )
        void queryClient.invalidateQueries({ queryKey: contactKeys.all })
      }
    })

  const mapped = Object.values(options.mapping).filter(Boolean).length
  const hasName =
    Boolean(options.mapping.first_name) || Boolean(options.mapping.full_name)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{t('contacts.import.title')}</DialogTitle>
          <DialogDescription>
            {t(`contacts.import.step_${step}`)}
          </DialogDescription>
        </DialogHeader>
        <ol className='flex gap-1' aria-label={t('contacts.import.progress')}>
          {STEPS.map((s, i) => (
            <li
              key={s}
              className={cn(
                'h-1 flex-1 rounded',
                i <= STEPS.indexOf(step) ? 'bg-primary' : 'bg-muted'
              )}
            />
          ))}
        </ol>

        {step === 'upload' ? (
          <label className='grid cursor-pointer place-items-center gap-2 rounded-lg border border-dashed p-8 text-sm text-muted-foreground hover:bg-muted/50'>
            <FileUp className='size-8' />
            {file ? (
              <span className='font-medium text-foreground'>{file.name}</span>
            ) : (
              t('contacts.import.choose')
            )}
            <input
              type='file'
              accept='.csv,.xlsx,.xlsm,.tsv,.txt'
              className='sr-only'
              data-testid='import-file'
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        ) : null}

        {step === 'mapping' && preview ? (
          <div className='grid gap-3'>
            <p className='text-sm'>
              {t('contacts.import.found', {
                rows: preview.rows,
                columns: preview.columns.length,
              })}
            </p>
            <div className='grid gap-2 sm:grid-cols-2'>
              {preview.fields.map((field) => (
                <div
                  key={field}
                  className='grid grid-cols-[8rem_1fr] items-center gap-2'
                >
                  <Label htmlFor={`map-${field}`}>{statusLabel(field)}</Label>
                  <Select
                    value={options.mapping[field] ?? IGNORE}
                    onValueChange={(v) => {
                      const mapping = { ...options.mapping }
                      if (v === IGNORE) delete mapping[field]
                      else mapping[field] = v
                      setOptions({ ...options, mapping })
                    }}
                  >
                    <SelectTrigger
                      id={`map-${field}`}
                      size='sm'
                      className='w-full'
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={IGNORE}>
                        {t('contacts.import.ignore')}
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
            </div>
            {!hasName ? (
              <p className='text-sm text-amber-600'>
                {t('contacts.import.need_name')}
              </p>
            ) : null}
            {preview.sample.length ? (
              <div className='max-h-48 overflow-auto rounded-md border'>
                <table className='w-full text-xs'>
                  <thead className='sticky top-0 bg-muted'>
                    <tr>
                      {preview.columns.map((c) => (
                        <th
                          key={c}
                          className='px-2 py-1 text-start font-medium whitespace-nowrap'
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
                          <td key={c} className='px-2 py-1 whitespace-nowrap'>
                            {String(row[c] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}

        {step === 'options' ? (
          <div className='grid gap-4'>
            <div className='grid gap-2'>
              <Label>{t('contacts.import.duplicates_label')}</Label>
              <RadioGroup
                value={options.on_duplicate}
                onValueChange={(v) =>
                  setOptions({
                    ...options,
                    on_duplicate: v as ImportOptions['on_duplicate'],
                  })
                }
              >
                <label className='flex items-start gap-2 text-sm'>
                  <RadioGroupItem value='skip' className='mt-0.5' />
                  {t('contacts.import.skip')}
                </label>
                <label className='flex items-start gap-2 text-sm'>
                  <RadioGroupItem value='update' className='mt-0.5' />
                  {t('contacts.import.update')}
                </label>
              </RadioGroup>
            </div>
            <div className='grid gap-2 sm:grid-cols-2'>
              <div className='grid gap-1.5'>
                <Label htmlFor='import-project'>
                  {t('contacts.import.project')}
                </Label>
                <Select
                  value={
                    options.project_id ? String(options.project_id) : NO_PROJECT
                  }
                  onValueChange={(v) =>
                    setOptions({
                      ...options,
                      project_id: v === NO_PROJECT ? null : Number(v),
                    })
                  }
                >
                  <SelectTrigger id='import-project' className='w-full'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_PROJECT}>
                      {t('contacts.import.no_project')}
                    </SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.code} {p.name}
                        {p.id === current?.id ? ' ·' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='import-role'>{t('contacts.import.role')}</Label>
                <Input
                  id='import-role'
                  maxLength={150}
                  disabled={!options.project_id}
                  value={options.project_role}
                  onChange={(e) =>
                    setOptions({ ...options, project_role: e.target.value })
                  }
                />
              </div>
            </div>
          </div>
        ) : null}

        {(step === 'review' || step === 'done') && report ? (
          <div className='grid gap-2'>
            {step === 'done' ? (
              <p className='flex items-center gap-2 text-sm font-medium text-green-700 dark:text-green-400'>
                <CheckCircle2 className='size-4' />
                {t('contacts.import.complete')}
              </p>
            ) : null}
            <Report report={report} />
          </div>
        ) : null}

        {error ? <p className='text-sm text-red-600'>{error}</p> : null}

        <DialogFooter className='gap-2'>
          {step === 'mapping' || step === 'options' || step === 'review' ? (
            <Button
              variant='outline'
              className='me-auto'
              disabled={busy}
              onClick={() =>
                setStep(STEPS[Math.max(0, STEPS.indexOf(step) - 1)])
              }
            >
              {t('contacts.import.back')}
            </Button>
          ) : null}
          {step === 'upload' ? (
            <Button disabled={!file || busy} onClick={upload}>
              {t('contacts.import.next')}
            </Button>
          ) : null}
          {step === 'mapping' ? (
            <Button
              disabled={!mapped || !hasName}
              onClick={() => setStep('options')}
            >
              {t('contacts.import.next')}
            </Button>
          ) : null}
          {step === 'options' ? (
            <Button disabled={busy} onClick={() => run(true)}>
              {t('contacts.import.dry_run')}
            </Button>
          ) : null}
          {step === 'review' ? (
            <Button disabled={busy} onClick={() => run(false)}>
              {t('contacts.import.confirm')}
            </Button>
          ) : null}
          {step === 'done' ? (
            <Button onClick={onClose}>{t('contacts.import.close')}</Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
