import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  refusalText,
  useDeleteItem,
  useDeletePermit,
  useReturnItem,
  useReturnPermit,
  type Deleted,
} from './api'
import { AreaControl } from './form-controls'
import { destinationKey } from './rules'

export type Target = { kind: 'item' | 'permit'; id: number; label: string }

/** A mandatory reason. The button stays disabled until one is typed. */
export function ReasonForm({
  pending,
  refusal,
  onSubmit,
}: {
  pending?: boolean
  refusal?: string | null
  onSubmit: (reason: string) => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  return (
    <form
      className='grid gap-3'
      onSubmit={(e) => {
        e.preventDefault()
        if (reason.trim()) onSubmit(reason.trim())
      }}
    >
      <AreaControl
        id='tw-return-reason'
        label={t('temporary_works.return.reason')}
        value={reason}
        onChange={setReason}
      />
      {refusal ? (
        <p role='alert' data-testid='tw-return-refusal' className='text-sm text-destructive'>
          {refusal}
        </p>
      ) : null}
      <div className='flex justify-end'>
        <Button
          type='submit'
          data-testid='tw-return-submit'
          disabled={pending || !reason.trim()}
        >
          {t('temporary_works.return.submit')}
        </Button>
      </div>
    </form>
  )
}

function useReturnFor(target: Target) {
  const item = useReturnItem(target.kind === 'item' ? target.id : 0)
  const permit = useReturnPermit(target.kind === 'permit' ? target.id : 0)
  return target.kind === 'item' ? item : permit
}

/** Sends an item or a permit back to draft. Needs the return-to-draft permission, held by whoever opens this. */
export function ReturnToDraftDialog({
  target,
  onClose,
}: {
  target: Target
  onClose: () => void
}) {
  const { t } = useTranslation()
  const back = useReturnFor(target)
  const [refusal, setRefusal] = useState<string | null>(null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t('temporary_works.return.title', {
              what: t(`temporary_works.return.${target.kind}`),
            })}{' '}
            {target.label}
          </DialogTitle>
          <DialogDescription>{t('temporary_works.return.help')}</DialogDescription>
        </DialogHeader>
        <ReasonForm
          pending={back.isPending}
          refusal={refusal}
          onSubmit={(reason) => {
            setRefusal(null)
            back.mutate(
              { reason },
              { onSuccess: onClose, onError: (e) => setRefusal(refusalText(e)) }
            )
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

function useDeleteFor(target: Target) {
  const item = useDeleteItem(target.kind === 'item' ? target.id : 0)
  const permit = useDeletePermit(target.kind === 'permit' ? target.id : 0)
  return target.kind === 'item' ? item : permit
}

/** Where a deleted record went, as the server's answer says: the recycle bin or the Deleted folder. */
export function DeletedNotice({ result }: { result: Deleted }) {
  const { t } = useTranslation()
  return (
    <p
      role='status'
      data-testid='tw-deleted-notice'
      data-destination={result.destination}
      className='rounded-md border bg-muted/40 p-3 text-sm'
    >
      {t(destinationKey(result.destination))}
    </p>
  )
}

/**
 * Deletes a draft. The confirmation explains the two destinations; once deleted, the server's answer says which one
 * the record went to. Only offered while the record is in draft.
 */
export function DeleteDialog({
  target,
  onClose,
}: {
  target: Target
  onClose: () => void
}) {
  const { t } = useTranslation()
  const remove = useDeleteFor(target)
  const [result, setResult] = useState<Deleted | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t('temporary_works.delete.title', {
              what: t(`temporary_works.return.${target.kind}`),
            })}{' '}
            {target.label}
          </DialogTitle>
          <DialogDescription>
            {t('temporary_works.delete.help')}
          </DialogDescription>
        </DialogHeader>
        {result ? <DeletedNotice result={result} /> : null}
        {refusal ? (
          <p role='alert' data-testid='tw-delete-refusal' className='text-sm text-destructive'>
            {refusal}
          </p>
        ) : null}
        <DialogFooter>
          {result ? (
            <Button onClick={onClose}>{t('temporary_works.done')}</Button>
          ) : (
            <Button
              variant='destructive'
              data-testid='tw-delete-submit'
              disabled={remove.isPending}
              onClick={() => {
                setRefusal(null)
                remove.mutate(undefined, {
                  onSuccess: (r) => setResult(r),
                  onError: (e) => setRefusal(refusalText(e)),
                })
              }}
            >
              {t('temporary_works.delete.submit')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
