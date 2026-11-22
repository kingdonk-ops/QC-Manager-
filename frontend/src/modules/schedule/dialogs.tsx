import { useState } from 'react'
import { Star, Trash2, Upload } from 'lucide-react'
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
import {
  type Baseline,
  type CalendarSettings,
  type ImportReport,
  useCreateBaseline,
  useDeleteBaseline,
  useGenerate,
  useImport,
  useSaveCalendar,
  useSetCurrentBaseline,
} from './api'
import { parseSections } from './sections'

type DialogProps = { projectId: number; open: boolean; onClose: () => void }

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function ImportDialog({ projectId, open, onClose }: DialogProps) {
  const { t } = useTranslation()
  const run = useImport(projectId)
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState(true)
  const [preview, setPreview] = useState<ImportReport | null>(null)

  const choose = (f: File | null) => {
    setFile(f)
    setPreview(null)
    if (f)
      run.mutate(
        { file: f, dryRun: true, replace },
        { onSuccess: (report) => setPreview(report) }
      )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('schedule.import.title')}</DialogTitle>
          <DialogDescription>
            {t('schedule.import.description')}
          </DialogDescription>
        </DialogHeader>
        <Input
          type='file'
          accept='.xer,.xml'
          aria-label={t('schedule.import.file')}
          onChange={(e) => choose(e.target.files?.[0] ?? null)}
        />
        {preview ? (
          <dl className='grid grid-cols-2 gap-x-4 gap-y-1 rounded-md border p-3 text-sm'>
            <dt className='text-muted-foreground'>
              {t('schedule.import.format')}
            </dt>
            <dd>{preview.format.toUpperCase().replace('_', ' ')}</dd>
            {preview.project_name ? (
              <>
                <dt className='text-muted-foreground'>
                  {t('schedule.import.project')}
                </dt>
                <dd>{preview.project_name}</dd>
              </>
            ) : null}
            <dt className='text-muted-foreground'>
              {t('schedule.import.activities')}
            </dt>
            <dd>{preview.activities}</dd>
            <dt className='text-muted-foreground'>
              {t('schedule.import.milestones')}
            </dt>
            <dd>{preview.milestones}</dd>
            <dt className='text-muted-foreground'>
              {t('schedule.import.summaries')}
            </dt>
            <dd>{preview.summaries}</dd>
            <dt className='text-muted-foreground'>
              {t('schedule.import.links')}
            </dt>
            <dd>{preview.dependencies}</dd>
            <dt className='text-muted-foreground'>
              {t('schedule.import.calendar')}
            </dt>
            <dd>
              {preview.working_days.map((d) => WEEKDAYS[d]).join(', ')}
              {preview.holidays ? ` · ${preview.holidays} holidays` : ''}
            </dd>
          </dl>
        ) : null}
        <label className='flex items-center gap-2 text-sm'>
          <Checkbox
            checked={replace}
            onCheckedChange={(v) => setReplace(v === true)}
          />
          {t('schedule.import.replace')}
        </label>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel', 'Cancel')}
          </Button>
          <Button
            disabled={!file || !preview || run.isPending}
            onClick={() =>
              file &&
              run.mutate(
                { file, dryRun: false, replace },
                {
                  onSuccess: (report) => {
                    toast.success(
                      t('schedule.import.done', { count: report.created })
                    )
                    setFile(null)
                    setPreview(null)
                    onClose()
                  },
                }
              )
            }
          >
            <Upload /> {t('schedule.import.go')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function BaselineDialog({
  projectId,
  open,
  onClose,
  baselines,
}: DialogProps & { baselines: Baseline[] }) {
  const { t } = useTranslation()
  const create = useCreateBaseline(projectId)
  const setCurrent = useSetCurrentBaseline(projectId)
  const remove = useDeleteBaseline(projectId)
  const [name, setName] = useState('')

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('schedule.baselines.title')}</DialogTitle>
          <DialogDescription>
            {t('schedule.baselines.description')}
          </DialogDescription>
        </DialogHeader>
        <ul className='divide-y rounded-md border text-sm'>
          {baselines.length === 0 ? (
            <li className='p-3 text-muted-foreground'>
              {t('schedule.baselines.none')}
            </li>
          ) : null}
          {baselines.map((b) => (
            <li key={b.id} className='flex items-center gap-2 p-2'>
              <button
                aria-label={t('schedule.baselines.make_current')}
                title={t('schedule.baselines.make_current')}
                onClick={() => setCurrent.mutate(b.id)}
                className={
                  b.is_current ? 'text-amber-500' : 'text-muted-foreground'
                }
              >
                <Star
                  className='size-4'
                  fill={b.is_current ? 'currentColor' : 'none'}
                />
              </button>
              <span className='flex-1'>
                <span className='font-medium'>{b.name}</span>
                <span className='ms-2 text-xs text-muted-foreground'>
                  {b.created_at?.slice(0, 10)} ·{' '}
                  {t('schedule.baselines.finish')} {b.finish_date ?? '–'}
                </span>
              </span>
              <button
                aria-label={t('common.delete', 'Delete')}
                className='text-muted-foreground hover:text-red-600'
                onClick={() => remove.mutate(b.id)}
              >
                <Trash2 className='size-4' />
              </button>
            </li>
          ))}
        </ul>
        <form
          className='flex gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              { name, make_current: true },
              { onSuccess: () => setName('') }
            )
          }}
        >
          <Input
            className='h-8'
            placeholder={t('schedule.baselines.name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
          />
          <Button size='sm' type='submit' disabled={create.isPending}>
            {t('schedule.baselines.save')}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function CalendarDialog({
  projectId,
  open,
  onClose,
  calendar,
}: DialogProps & { calendar: CalendarSettings }) {
  const { t } = useTranslation()
  const save = useSaveCalendar(projectId)
  const [days, setDays] = useState<number[]>(calendar.working_days)
  const [holidays, setHolidays] = useState(calendar.holidays.join('\n'))
  const [start, setStart] = useState(calendar.start_date ?? '')
  const [dataDate, setDataDate] = useState(calendar.data_date ?? '')

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('schedule.calendar.title')}</DialogTitle>
          <DialogDescription>
            {t('schedule.calendar.description')}
          </DialogDescription>
        </DialogHeader>
        <form
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            const list = holidays
              .split(/[\s,;]+/)
              .map((h) => h.trim())
              .filter((h) => /^\d{4}-\d{2}-\d{2}$/.test(h))
            save.mutate(
              {
                working_days: days,
                holidays: list,
                start_date: start || null,
                data_date: dataDate || null,
              },
              { onSuccess: onClose }
            )
          }}
        >
          <div className='grid gap-1'>
            <Label>{t('schedule.calendar.working_days')}</Label>
            <div className='flex flex-wrap gap-3'>
              {WEEKDAYS.map((label, i) => (
                <label key={label} className='flex items-center gap-1 text-sm'>
                  <Checkbox
                    checked={days.includes(i)}
                    onCheckedChange={(v) =>
                      setDays(
                        v === true
                          ? [...days, i].sort()
                          : days.filter((d) => d !== i)
                      )
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1'>
              <Label htmlFor='cal-start'>{t('schedule.calendar.start')}</Label>
              <Input
                id='cal-start'
                type='date'
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='cal-data'>
                {t('schedule.calendar.data_date')}
              </Label>
              <Input
                id='cal-data'
                type='date'
                value={dataDate}
                onChange={(e) => setDataDate(e.target.value)}
              />
            </div>
          </div>
          <div className='grid gap-1'>
            <Label htmlFor='cal-holidays'>
              {t('schedule.calendar.holidays')}
            </Label>
            <Textarea
              id='cal-holidays'
              rows={5}
              placeholder='2026-12-25'
              value={holidays}
              onChange={(e) => setHolidays(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              type='submit'
              disabled={save.isPending || days.length === 0}
            >
              {t('common.save', 'Save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function GenerateDialog({
  projectId,
  open,
  onClose,
  cvrAvailable,
}: DialogProps & { cvrAvailable: boolean }) {
  const { t } = useTranslation()
  const generate = useGenerate(projectId)
  const [source, setSource] = useState<'sections' | 'cvr'>('sections')
  const [text, setText] = useState('')
  const [total, setTotal] = useState('60')
  const [start, setStart] = useState('')
  const [replace, setReplace] = useState(false)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('schedule.generate.title')}</DialogTitle>
          <DialogDescription>
            {t('schedule.generate.description')}
          </DialogDescription>
        </DialogHeader>
        <form
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            let sections: ReturnType<typeof parseSections> = []
            if (source === 'sections') {
              try {
                sections = parseSections(text)
              } catch {
                toast.error(t('schedule.generate.bad_json'))
                return
              }
              if (!sections.length) {
                toast.error(t('schedule.generate.empty'))
                return
              }
            }
            generate.mutate(
              {
                source,
                sections,
                total_duration: Math.max(1, Number(total) || 1),
                start_date: start || null,
                replace,
              },
              { onSuccess: onClose }
            )
          }}
        >
          {cvrAvailable ? (
            <div className='flex gap-4 text-sm'>
              <label className='flex items-center gap-1'>
                <input
                  type='radio'
                  checked={source === 'sections'}
                  onChange={() => setSource('sections')}
                />
                {t('schedule.generate.from_sections')}
              </label>
              <label className='flex items-center gap-1'>
                <input
                  type='radio'
                  checked={source === 'cvr'}
                  onChange={() => setSource('cvr')}
                />
                {t('schedule.generate.from_cvr')}
              </label>
            </div>
          ) : null}
          {source === 'sections' ? (
            <Textarea
              rows={7}
              aria-label={t('schedule.generate.sections')}
              className='font-mono text-xs'
              placeholder={
                '01, Preliminaries, 10000\n02, Insulation, 60000\n03, Cladding, 30000'
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          ) : null}
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1'>
              <Label htmlFor='gen-total'>{t('schedule.generate.total')}</Label>
              <Input
                id='gen-total'
                type='number'
                min={1}
                value={total}
                onChange={(e) => setTotal(e.target.value)}
              />
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='gen-start'>{t('schedule.calendar.start')}</Label>
              <Input
                id='gen-start'
                type='date'
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
          </div>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={replace}
              onCheckedChange={(v) => setReplace(v === true)}
            />
            {t('schedule.generate.replace')}
          </label>
          <DialogFooter>
            <Button type='submit' disabled={generate.isPending}>
              {t('schedule.generate.go')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
