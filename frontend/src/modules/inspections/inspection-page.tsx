import { useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  FileText,
  Info,
  MessageSquare,
  RotateCcw,
  XCircle,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { Attachments } from '@/components/records/attachments'
import { uploadFile } from '@/components/records/files'
import { StatusBadge } from '@/components/records/status-badge'
import { useModuleParams } from '../_runtime'
import {
  type FollowUp,
  type Inspection,
  type InspectionItem,
  keys,
  limitHint,
  readingOutcome,
  useComplete,
  useFillItems,
  useInspection,
  useSetStatus,
} from './api'
import { PassRate } from './inspections-page'

type Fill = ReturnType<typeof useFillItems>

const RESULT_STYLE: Record<string, string> = {
  pass: 'border-green-600 bg-green-600 text-white hover:bg-green-600/90',
  fail: 'border-red-600 bg-red-600 text-white hover:bg-red-600/90',
  na: 'border-slate-500 bg-slate-500 text-white hover:bg-slate-500/90',
}

function ResultButtons({
  item,
  fill,
  locked,
  numeric,
}: {
  item: InspectionItem
  fill: Fill
  locked: boolean
  numeric?: boolean
}) {
  const { t } = useTranslation()
  const choices = numeric
    ? (['na'] as const)
    : (['pass', 'fail', 'na'] as const)
  return (
    <div className={cn('grid gap-2', numeric ? 'grid-cols-1' : 'grid-cols-3')}>
      {choices.map((choice) => {
        const active = item.result === choice
        return (
          <Button
            key={choice}
            type='button'
            variant='outline'
            disabled={locked || fill.isPending}
            aria-pressed={active}
            className={cn(
              'h-12 text-base font-semibold',
              active && RESULT_STYLE[choice]
            )}
            onClick={() =>
              fill.mutate([{ id: item.id, result: active ? null : choice }])
            }
          >
            {t(`inspections.result.${choice}`)}
          </Button>
        )
      })}
    </div>
  )
}

function ReadingInput({
  item,
  fill,
  locked,
}: {
  item: InspectionItem
  fill: Fill
  locked: boolean
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState(
    item.reading === null ? '' : String(item.reading)
  )
  const typed = value.trim() === '' ? null : Number(value)
  const live = readingOutcome(item, typed)
  const commit = () => {
    if (typed !== null && Number.isNaN(typed)) return
    if (typed === item.reading) return
    fill.mutate([
      {
        id: item.id,
        reading: typed,
        ...(item.result === 'na' && typed !== null ? { result: null } : {}),
      },
    ])
  }
  const hint = limitHint(item)
  return (
    <div className='grid gap-1.5'>
      <div className='flex items-center gap-2'>
        <Input
          type='number'
          inputMode='decimal'
          step='any'
          aria-label={item.text}
          className={cn(
            'h-12 flex-1 text-lg tabular-nums',
            live === 'fail' && 'border-red-600',
            live === 'pass' && 'border-green-600'
          )}
          placeholder={hint || t('inspections.reading')}
          value={value}
          disabled={locked}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === 'Enter' && commit()}
        />
        {item.unit ? (
          <span className='w-12 text-sm text-muted-foreground'>
            {item.unit}
          </span>
        ) : null}
      </div>
      <p className='text-xs text-muted-foreground'>
        {hint ? `${t('inspections.acceptance')}: ${hint}` : null}
        {live ? (
          <span
            className={cn(
              'ms-2 font-medium',
              live === 'pass' ? 'text-green-600' : 'text-red-600'
            )}
          >
            {live === 'pass'
              ? t('inspections.within_limits')
              : t('inspections.outside_limits')}
          </span>
        ) : null}
      </p>
    </div>
  )
}

function PhotoButton({
  item,
  projectId,
  inspectionId,
  locked,
}: {
  item: InspectionItem
  projectId: number
  inspectionId: number
  locked: boolean
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const upload = async (files: FileList) => {
    setBusy(true)
    try {
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.set('file', file)
        form.set('project_id', String(projectId))
        form.set('entity_type', 'inspection_item')
        form.set('entity_id', String(item.id))
        form.set('category', 'photo')
        await uploadFile(form)
      }
      toast.success(t('inspections.photo_added'))
      void queryClient.invalidateQueries({ queryKey: keys.one(inspectionId) })
      void queryClient.invalidateQueries({
        queryKey: ['files', projectId, 'inspection_item', item.id],
      })
    } catch (error) {
      handleServerError(error)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }
  return (
    <>
      <input
        ref={input}
        type='file'
        accept='image/*'
        capture='environment'
        multiple
        hidden
        onChange={(e) => e.target.files?.length && void upload(e.target.files)}
      />
      <Button
        type='button'
        variant='outline'
        className='h-10'
        disabled={locked || busy}
        onClick={() => input.current?.click()}
      >
        <Camera /> {t('inspections.photo')}
        {item.photo_count ? (
          <Badge variant='secondary' className='ms-1'>
            {item.photo_count}
          </Badge>
        ) : null}
      </Button>
    </>
  )
}

function ItemCard({
  item,
  inspection,
  fill,
  locked,
}: {
  item: InspectionItem
  inspection: Inspection
  fill: Fill
  locked: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [showNotes, setShowNotes] = useState(Boolean(item.notes))
  const [showPhotos, setShowPhotos] = useState(false)
  const [notes, setNotes] = useState(item.notes ?? '')
  const numeric = item.response_type === 'numeric'
  const failed = item.outcome === 'fail'
  const needsPhoto = failed && item.requires_photo_on_fail && !item.photo_count

  return (
    <Card
      className={cn(
        'gap-3 py-4',
        failed && 'border-red-500/60',
        item.outcome === 'pass' && 'border-green-500/40'
      )}
    >
      <CardContent className='grid gap-3 px-4'>
        <div className='flex items-start gap-2'>
          <span className='mt-0.5 text-xs text-muted-foreground tabular-nums'>
            {item.position}.
          </span>
          <div className='grid flex-1 gap-1'>
            <p className='leading-snug font-medium'>{item.text}</p>
            {item.guidance ? (
              <p className='flex gap-1 text-xs text-muted-foreground'>
                <Info className='mt-0.5 size-3 shrink-0' /> {item.guidance}
              </p>
            ) : null}
          </div>
          {item.outcome ? <StatusBadge status={item.outcome} /> : null}
        </div>

        {numeric ? (
          <div className='grid grid-cols-[1fr_auto] items-start gap-2'>
            <ReadingInput item={item} fill={fill} locked={locked} />
            <div className='w-20'>
              <ResultButtons item={item} fill={fill} locked={locked} numeric />
            </div>
          </div>
        ) : (
          <ResultButtons item={item} fill={fill} locked={locked} />
        )}

        <div className='flex flex-wrap items-center gap-2'>
          <PhotoButton
            item={item}
            projectId={inspection.project_id}
            inspectionId={inspection.id}
            locked={locked}
          />
          <Button
            type='button'
            variant='ghost'
            className='h-10'
            onClick={() => setShowNotes(!showNotes)}
          >
            <MessageSquare /> {t('inspections.notes')}
          </Button>
          {item.photo_count ? (
            <Button
              type='button'
              variant='ghost'
              className='h-10'
              onClick={() => setShowPhotos(!showPhotos)}
            >
              {showPhotos
                ? t('inspections.hide_photos')
                : t('inspections.show_photos')}
            </Button>
          ) : null}
          {needsPhoto ? (
            <span className='text-xs font-medium text-red-600'>
              {t('inspections.photo_required')}
            </span>
          ) : item.requires_photo_on_fail && !failed ? (
            <span className='text-xs text-muted-foreground'>
              {t('inspections.photo_on_fail')}
            </span>
          ) : null}
          {item.task_id ? (
            <Badge variant='outline'>{t('inspections.task_raised')}</Badge>
          ) : null}
          {item.ncr_id ? (
            <Button
              type='button'
              variant='link'
              className='h-auto px-1 text-xs'
              onClick={() =>
                void navigate({ to: `/ncr?id=${item.ncr_id}` as never })
              }
            >
              {t('inspections.ncr_raised')}
            </Button>
          ) : null}
        </div>
        {showNotes ? (
          <Textarea
            aria-label={t('inspections.notes')}
            value={notes}
            disabled={locked}
            placeholder={t('inspections.notes_placeholder')}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() =>
              notes !== (item.notes ?? '') &&
              fill.mutate([{ id: item.id, notes: notes || null }])
            }
          />
        ) : null}
        {showPhotos ? (
          <Attachments
            projectId={inspection.project_id}
            entityType='inspection_item'
            entityId={item.id}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}

function CompleteDialog({
  inspection,
  open,
  onClose,
}: {
  inspection: Inspection
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const complete = useComplete(inspection.id)
  const failed = inspection.items.filter(
    (i) => i.outcome === 'fail' && !i.task_id && !i.ncr_id
  )
  const [choices, setChoices] = useState<Record<number, FollowUp>>(() =>
    Object.fromEntries(
      failed.map((i) => [
        i.id,
        { item_id: i.id, action: 'task', severity: 'minor' } as FollowUp,
      ])
    )
  )
  const [assignee, setAssignee] = useState<number | null>(null)
  const [due, setDue] = useState('')
  const set = (id: number, patch: Partial<FollowUp>) =>
    setChoices({ ...choices, [id]: { ...choices[id], ...patch } })
  const canNcr = can(session, 'ncr.read')

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{t('inspections.complete_title')}</DialogTitle>
          <DialogDescription>
            {t('inspections.complete_description')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid grid-cols-4 gap-2 text-center'>
          <Stat label={t('inspections.score')}>
            <PassRate value={inspection.pass_rate} />
          </Stat>
          <Stat label={t('inspections.result.pass')}>
            <span className='text-green-600'>{inspection.passed}</span>
          </Stat>
          <Stat label={t('inspections.result.fail')}>
            <span className='text-red-600'>{inspection.failed}</span>
          </Stat>
          <Stat label={t('inspections.result.na')}>
            {inspection.not_applicable}
          </Stat>
        </div>
        {inspection.unanswered ? (
          <p className='text-sm text-amber-600'>
            {t('inspections.unanswered_warning', {
              count: inspection.unanswered,
            })}
          </p>
        ) : null}
        {failed.length ? (
          <div className='grid gap-3'>
            <p className='text-sm font-medium'>{t('inspections.follow_ups')}</p>
            {failed.map((item) => (
              <div
                key={item.id}
                className='grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_auto_auto]'
              >
                <p className='text-sm'>
                  <span className='text-muted-foreground'>
                    {item.position}.
                  </span>{' '}
                  {item.text}
                  {item.reading !== null ? (
                    <span className='text-red-600'>
                      {' '}
                      ({item.reading} {item.unit})
                    </span>
                  ) : null}
                </p>
                <NativeSelect
                  className='sm:w-36'
                  aria-label={t('inspections.follow_up')}
                  options={[
                    { value: 'task', label: t('inspections.raise_task') },
                    ...(canNcr
                      ? [{ value: 'ncr', label: t('inspections.raise_ncr') }]
                      : []),
                    { value: 'none', label: t('inspections.no_action') },
                  ]}
                  value={choices[item.id]?.action ?? 'task'}
                  onChange={(e) =>
                    set(item.id, {
                      action: e.target.value as FollowUp['action'],
                    })
                  }
                />
                {choices[item.id]?.action === 'ncr' ? (
                  <NativeSelect
                    className='sm:w-32'
                    aria-label={t('inspections.severity')}
                    options={[
                      { value: 'minor', label: 'Minor' },
                      { value: 'major', label: 'Major' },
                      { value: 'critical', label: 'Critical' },
                    ]}
                    value={choices[item.id]?.severity ?? 'minor'}
                    onChange={(e) => set(item.id, { severity: e.target.value })}
                  />
                ) : (
                  <span />
                )}
              </div>
            ))}
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='grid gap-1.5'>
                <Label>{t('inspections.assign_to')}</Label>
                <UserSelect value={assignee} onChange={setAssignee} />
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='complete-due'>{t('inspections.due')}</Label>
                <Input
                  id='complete-due'
                  type='date'
                  value={due}
                  onChange={(e) => setDue(e.target.value)}
                />
              </div>
            </div>
          </div>
        ) : (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.no_failures')}
          </p>
        )}
        <DialogFooter>
          <Button
            className='h-11 w-full sm:w-auto'
            disabled={complete.isPending}
            onClick={() =>
              complete.mutate(
                {
                  follow_ups: Object.values(choices),
                  default_assignee_id: assignee,
                  default_due_date: due || null,
                  allow_unanswered: inspection.unanswered > 0,
                },
                {
                  onSuccess: () => {
                    toast.success(t('inspections.completed_toast'))
                    onClose()
                  },
                }
              )
            }
          >
            <CheckCircle2 /> {t('inspections.complete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Stat({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className='rounded-md border px-2 py-2'>
      <p className='text-lg font-semibold tabular-nums'>{children}</p>
      <p className='text-xs text-muted-foreground'>{label}</p>
    </div>
  )
}

function FillForm({ inspection }: { inspection: Inspection }) {
  const { t } = useTranslation()
  const session = useSession()
  const fill = useFillItems(inspection.id)
  const setStatus = useSetStatus(inspection.id)
  const [completing, setCompleting] = useState(false)
  const locked =
    !can(session, 'inspections.update') ||
    inspection.status === 'completed' ||
    inspection.status === 'closed'
  const sections = useMemo(() => {
    const out: { title: string; items: InspectionItem[] }[] = []
    for (const item of inspection.items) {
      const last = out[out.length - 1]
      if (last && last.title === item.section) last.items.push(item)
      else out.push({ title: item.section, items: [item] })
    }
    return out
  }, [inspection.items])
  const answered = inspection.total - inspection.unanswered
  const canTransition = can(session, 'inspections.transition')

  return (
    <div className='mx-auto grid w-full max-w-3xl gap-4 pb-24'>
      <div className='flex flex-wrap items-center gap-2 text-sm text-muted-foreground'>
        <StatusBadge status={inspection.status} />
        {inspection.template_name ? (
          <span>
            {inspection.template_name} v{inspection.template_version}
          </span>
        ) : null}
        {[inspection.location, inspection.area, inspection.trade]
          .filter(Boolean)
          .map((part) => (
            <span key={part}>· {part}</span>
          ))}
        {inspection.inspector_name ? (
          <span>· {inspection.inspector_name}</span>
        ) : null}
      </div>

      {sections.map((section) => (
        <section key={section.title} className='grid gap-3'>
          <h3 className='text-sm font-semibold tracking-wide text-muted-foreground uppercase'>
            {section.title}
          </h3>
          {section.items.map((item) => (
            <ItemCard
              key={`${item.id}-${item.reading}-${inspection.status}`}
              item={item}
              inspection={inspection}
              fill={fill}
              locked={locked}
            />
          ))}
        </section>
      ))}

      <div className='fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 px-4 py-3 backdrop-blur md:static md:rounded-md md:border'>
        <div className='mx-auto flex max-w-3xl flex-wrap items-center gap-3'>
          <div className='flex items-center gap-3 text-sm'>
            <PassRate value={inspection.pass_rate} />
            <span className='flex items-center gap-1 text-green-600'>
              <CheckCircle2 className='size-4' /> {inspection.passed}
            </span>
            <span className='flex items-center gap-1 text-red-600'>
              <XCircle className='size-4' /> {inspection.failed}
            </span>
            <span className='text-muted-foreground'>
              {answered}/{inspection.total}
            </span>
          </div>
          <div className='ms-auto flex gap-2'>
            {inspection.status === 'completed' && canTransition ? (
              <>
                <Button
                  variant='outline'
                  onClick={() => setStatus.mutate('in_progress')}
                >
                  <RotateCcw /> {t('inspections.reopen')}
                </Button>
                <Button onClick={() => setStatus.mutate('closed')}>
                  {t('inspections.close')}
                </Button>
              </>
            ) : null}
            {(inspection.status === 'in_progress' ||
              inspection.status === 'planned') &&
            canTransition ? (
              <Button
                className='h-11'
                disabled={inspection.status === 'planned'}
                onClick={() => setCompleting(true)}
              >
                <CheckCircle2 /> {t('inspections.complete')}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
      {completing ? (
        <CompleteDialog
          inspection={inspection}
          open
          onClose={() => setCompleting(false)}
        />
      ) : null}
    </div>
  )
}

export default function InspectionPage() {
  const { t } = useTranslation()
  const { inspectionId } = useModuleParams()
  const id = Number(inspectionId)
  const { data: inspection, isLoading } = useInspection(id)

  return (
    <Page
      title={
        inspection
          ? `${inspection.code} · ${inspection.title}`
          : t('inspections.inspection')
      }
      actions={
        <>
          <Button size='sm' variant='ghost' asChild>
            <Link to='/$' params={{ _splat: 'inspections' }}>
              <ArrowLeft /> {t('inspections.register')}
            </Link>
          </Button>
          {inspection ? (
            <Button size='sm' variant='outline' asChild>
              <a
                href={`/api/v1/inspections/${inspection.id}/report.pdf`}
                target='_blank'
                rel='noreferrer'
              >
                <FileText /> PDF
              </a>
            </Button>
          ) : null}
        </>
      }
    >
      {inspection ? (
        <FillForm inspection={inspection} />
      ) : isLoading ? null : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.not_found')}
        </p>
      )}
    </Page>
  )
}
