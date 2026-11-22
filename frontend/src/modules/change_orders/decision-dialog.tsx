import { useState } from 'react'
import { Check, X } from 'lucide-react'
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
import { Textarea } from '@/components/ui/textarea'
import type { ChangeOrderDetail } from './api'

/** Approve or reject a submitted change order, with a comment the requester sees. */
export function DecisionDialog({
  open,
  onClose,
  co,
  onDecide,
  pending,
  format,
}: {
  open: boolean
  onClose: () => void
  co: ChangeOrderDetail
  onDecide: (status: 'approved' | 'rejected', comment: string) => void
  pending: boolean
  format: (v?: string | number | null) => string
}) {
  const { t } = useTranslation()
  const [comment, setComment] = useState('')
  const applies = co.cvr_apply !== 'none'

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('co.decide')} · {co.code}
          </DialogTitle>
          <DialogDescription>
            {t('co.decision_summary', {
              delta: format(co.total_delta),
              days: co.time_impact_days,
            })}
          </DialogDescription>
        </DialogHeader>
        {applies ? (
          <p className='text-sm text-muted-foreground'>
            {t('co.decision_cvr', { target: t(`co.apply.${co.cvr_apply}`) })}
          </p>
        ) : null}
        <Textarea
          rows={3}
          placeholder={t('co.decision_comment')}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <DialogFooter>
          <Button
            variant='outline'
            className='text-red-600'
            disabled={pending}
            onClick={() => onDecide('rejected', comment)}
          >
            <X /> {t('co.reject')}
          </Button>
          <Button
            disabled={pending}
            onClick={() => onDecide('approved', comment)}
          >
            <Check /> {t('co.approve')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
