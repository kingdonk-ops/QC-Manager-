import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { StatusBadge } from '@/components/records/status-badge'
import { refusalText, useTransitionItem, type Item } from './api'
import { AreaControl, SelectControl } from './form-controls'
import { WarningsList } from './warnings-list'
import { nextSteps, statusKey, stepNeedsNote } from './rules'

type FormProps = {
  status: string
  heldFrom?: string | null
  /** The server's refusal, word for word. */
  refusal?: string | null
  pending?: boolean
  onSubmit: (move: { status: string; note: string | null }) => void
}

/**
 * Offers only the next steps for the item's status, with a note (required when stepping back or putting the item on
 * hold). It never decides whether a move is allowed: a refusal from the server is shown as it came.
 */
export function TransitionForm({
  status,
  heldFrom,
  refusal,
  pending,
  onSubmit,
}: FormProps) {
  const { t } = useTranslation()
  const steps = nextSteps(status, heldFrom)
  const [target, setTarget] = useState(steps[0] ?? '')
  const [note, setNote] = useState('')
  const needsNote = target !== '' && stepNeedsNote(status, target)
  if (steps.length === 0)
    return (
      <p className='text-sm text-muted-foreground' data-testid='tw-no-steps'>
        {t('temporary_works.transition.none')}
      </p>
    )
  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit({ status: target, note: note.trim() || null })
      }}
    >
      <div className='flex items-center gap-2 text-sm'>
        <span className='text-muted-foreground'>
          {t('temporary_works.transition.current')}
        </span>
        <StatusBadge status={status} />
      </div>
      <SelectControl
        id='tw-transition-target'
        label={t('temporary_works.transition.next')}
        options={steps.map((s) => ({ value: s, label: t(statusKey(s)) }))}
        value={target}
        onChange={setTarget}
      />
      <AreaControl
        id='tw-transition-note'
        label={t('temporary_works.transition.note')}
        value={note}
        onChange={setNote}
      />
      {needsNote ? (
        <p className='text-xs text-muted-foreground'>
          {t('temporary_works.transition.note_required')}
        </p>
      ) : null}
      {refusal ? (
        <div
          role='alert'
          data-testid='tw-refusal'
          className='rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm'
        >
          <p className='font-medium'>{t('temporary_works.transition.refused')}</p>
          <p>{refusal}</p>
        </div>
      ) : null}
      <div className='flex justify-end'>
        <Button
          type='submit'
          data-testid='tw-transition-submit'
          disabled={pending || !target || (needsNote && !note.trim())}
        >
          {t('temporary_works.transition.submit')}
        </Button>
      </div>
    </form>
  )
}

export function TransitionDialog({
  item,
  onClose,
}: {
  item: Item
  onClose: () => void
}) {
  const { t } = useTranslation()
  const move = useTransitionItem(item.id)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<
    { rule: string; message: string }[] | null
  >(null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t('temporary_works.transition.title', {
              reference: item.reference,
            })}
          </DialogTitle>
        </DialogHeader>
        {warnings ? (
          <>
            <WarningsList warnings={warnings} />
            <Button onClick={onClose}>{t('temporary_works.done')}</Button>
          </>
        ) : (
          <TransitionForm
            status={item.status}
            heldFrom={item.held_from}
            refusal={refusal}
            pending={move.isPending}
            onSubmit={(body) => {
              setRefusal(null)
              move.mutate(body, {
                onSuccess: (written) =>
                  written.warnings && written.warnings.length > 0
                    ? setWarnings(written.warnings)
                    : onClose(),
                onError: (e) => setRefusal(refusalText(e)),
              })
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
