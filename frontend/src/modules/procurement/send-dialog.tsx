import { useState } from 'react'
import { Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
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
import { Textarea } from '@/components/ui/textarea'
import { Field } from '@/components/records/fields'
import { type PurchaseOrderDetail, usePoActions } from './api'

/** Email the PO as a PDF to the supplier; a draft becomes sent. */
export function SendDialog({
  po,
  projectId,
  open,
  onClose,
  format,
}: {
  po: PurchaseOrderDetail
  projectId: number
  open: boolean
  onClose: () => void
  format: (v?: string | number | null) => string
}) {
  const { t } = useTranslation()
  const { send } = usePoActions(projectId, po.id)
  const fallback = po.supplier?.contact_email || po.supplier?.email || ''
  const [to, setTo] = useState('')
  const [message, setMessage] = useState('')

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('po.send')} · {po.code}
          </DialogTitle>
          <DialogDescription>
            {t('po.send_summary', {
              supplier: po.supplier_name ?? '—',
              total: `${po.currency} ${format(po.gross_total)}`,
            })}
          </DialogDescription>
        </DialogHeader>
        {po.needs_approval ? (
          <p className='text-sm text-amber-600'>{t('po.needs_approval')}</p>
        ) : null}
        <Field label={t('po.send_to')}>
          <Input
            placeholder={fallback || t('po.no_email')}
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </Field>
        <Field label={t('po.message')}>
          <Textarea
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
        </Field>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={send.isPending || (!to && !fallback)}
            onClick={() =>
              send.mutate(
                {
                  to: to
                    .split(/[,;\s]+/)
                    .map((s) => s.trim())
                    .filter(Boolean),
                  message: message || null,
                },
                {
                  onSuccess: (sent) => {
                    toast.success(t('po.sent_to', { to: sent.sent_to }))
                    onClose()
                  },
                }
              )
            }
          >
            <Send /> {t('po.send')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
