import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Camera, Info, MessageSquare } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Attachments } from '@/components/records/attachments'
import { uploadFile } from '@/components/records/files'
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Inspection,
  type InspectionItem,
  keys,
  limitHint,
  readingOutcome,
  type useFillItems,
} from './api'
import { ItemCriterion } from './criterion-summary'

export type Fill = ReturnType<typeof useFillItems>

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

export function ItemCard({
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
            {item.criterion_id ? (
              <span>
                <ItemCriterion
                  projectId={inspection.project_id}
                  criterionId={item.criterion_id}
                />
              </span>
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
