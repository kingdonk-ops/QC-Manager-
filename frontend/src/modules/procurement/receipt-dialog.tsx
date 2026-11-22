import { useState } from 'react'
import { PackageCheck, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
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
import { Textarea } from '@/components/ui/textarea'
import { Attachments } from '@/components/records/attachments'
import { Field } from '@/components/records/fields'
import {
  type PurchaseOrderDetail,
  type ReceiptResult,
  usePoActions,
} from './api'

const today = () => new Date().toISOString().slice(0, 10)

/** Enter what arrived against what's outstanding; then attach delivery photos to the receipt. */
export function ReceiptDialog({
  po,
  projectId,
  open,
  onClose,
}: {
  po: PurchaseOrderDetail
  projectId: number
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { receive } = usePoActions(projectId, po.id)
  const lines = po.lines ?? []
  const [qty, setQty] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      lines.map((l) => [l.id, String(Number(l.outstanding_quantity ?? 0))])
    )
  )
  const [date, setDate] = useState(today)
  const [notes, setNotes] = useState('')
  const [done, setDone] = useState<ReceiptResult>()

  const entered = lines
    .map((l) => ({ line_id: l.id, quantity: Number(qty[l.id] || 0) }))
    .filter((l) => l.quantity > 0)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {t('po.receive')} · {po.code}
          </DialogTitle>
          <DialogDescription>
            {done
              ? t('po.received_as', {
                  code: done.receipt.code,
                  status: t(`po.st.${done.status}`),
                })
              : t('po.receive_hint')}
          </DialogDescription>
        </DialogHeader>

        {done ? (
          <div className='space-y-3'>
            {done.warnings.map((w) => (
              <p key={w} className='flex gap-2 text-sm text-amber-600'>
                <TriangleAlert className='size-4 shrink-0' /> {w}
              </p>
            ))}
            <p className='text-sm font-medium'>{t('po.photos')}</p>
            <Attachments
              projectId={projectId}
              entityType='goods_receipt'
              entityId={done.receipt.id}
            />
          </div>
        ) : (
          <div className='space-y-3'>
            <table className='w-full text-sm'>
              <thead className='text-left text-xs text-muted-foreground'>
                <tr>
                  <th className='py-1'>{t('po.item')}</th>
                  <th className='text-right'>{t('po.ordered')}</th>
                  <th className='text-right'>{t('po.outstanding')}</th>
                  <th className='w-32 text-right'>{t('po.receiving')}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => {
                  const over =
                    Number(qty[l.id] || 0) > Number(l.outstanding_quantity ?? 0)
                  return (
                    <tr key={l.id} className='border-t'>
                      <td className='py-1.5'>
                        {l.description}
                        {l.unit ? (
                          <span className='text-muted-foreground'>
                            {' '}
                            ({l.unit})
                          </span>
                        ) : null}
                      </td>
                      <td className='text-right tabular-nums'>
                        {Number(l.quantity)}
                      </td>
                      <td className='text-right tabular-nums'>
                        {Number(l.outstanding_quantity ?? 0)}
                      </td>
                      <td className='py-1 ps-2'>
                        <Input
                          type='number'
                          min={0}
                          step='any'
                          aria-label={l.description}
                          className={cn(
                            'h-8 text-right',
                            over && 'border-amber-500 text-amber-600'
                          )}
                          value={qty[l.id] ?? ''}
                          onChange={(e) =>
                            setQty({ ...qty, [l.id]: e.target.value })
                          }
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className='grid gap-3 sm:grid-cols-[10rem_1fr]'>
              <Field label={t('po.received_date')}>
                <Input
                  type='date'
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </Field>
              <Field label={t('po.quality_notes')}>
                <Textarea
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </Field>
            </div>
          </div>
        )}

        <DialogFooter>
          {done ? (
            <Button onClick={onClose}>{t('po.done')}</Button>
          ) : (
            <>
              <Button variant='outline' onClick={onClose}>
                {t('common.cancel')}
              </Button>
              <Button
                disabled={receive.isPending || entered.length === 0}
                onClick={() =>
                  receive.mutate(
                    {
                      received_date: date || null,
                      quality_notes: notes || null,
                      lines: entered,
                    },
                    {
                      onSuccess: (result) => {
                        if (result.warnings.length)
                          toast.warning(t('po.over_receipt'))
                        else toast.success(t('po.recorded'))
                        setDone(result)
                      },
                    }
                  )
                }
              >
                <PackageCheck /> {t('po.record_receipt')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
