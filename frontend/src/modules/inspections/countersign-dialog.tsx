import { useState } from 'react'
import { PenLine } from 'lucide-react'
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
import { Intent } from './signoff-dialogs'

/**
 * Signing as an additional signatory: the signer accepts the statement, the request is sent, and the server's
 * refusal (for example the same person and role twice) is shown as it came.
 */
export function AdditionalSignatoryDialog({
  name,
  code,
  pending,
  error,
  onSubmit,
  onClose,
}: {
  name: string
  code: string
  pending?: boolean
  error?: string | null
  onSubmit: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [accept, setAccept] = useState(false)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.signers.add_title')}</DialogTitle>
          <DialogDescription>
            {t('inspections.signers.add_help')}
          </DialogDescription>
        </DialogHeader>
        <Intent
          text={t('inspections.signers.add_intent', { name, code })}
          accepted={accept}
          onChange={setAccept}
        />
        {error ? (
          <p
            role='alert'
            data-testid='signer-error'
            className='text-sm text-red-600'
          >
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            data-testid='signer-submit'
            disabled={!accept || pending}
            onClick={onSubmit}
          >
            <PenLine /> {t('inspections.signers.add_submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
