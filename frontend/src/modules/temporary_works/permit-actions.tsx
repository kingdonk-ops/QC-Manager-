import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { permitActions, type PermitAction } from './rules'

/**
 * The buttons a permit offers: edit and delete only on a draft, issue, activate and close only to holders of the issue
 * permission, return to draft only to holders of its own permission. `has` answers whether a permission is held.
 */
export function PermitActions({
  status,
  has,
  pending,
  onAct,
}: {
  status: string
  has: (permission: string) => boolean
  pending?: boolean
  onAct: (action: PermitAction) => void
}) {
  const { t } = useTranslation()
  const actions = permitActions(status, has)
  if (actions.length === 0) return null
  return (
    <div className='flex flex-wrap gap-1' data-testid='permit-actions'>
      {actions.map((action) => (
        <Button
          key={action}
          size='sm'
          variant={action === 'issue' || action === 'activate' ? 'default' : 'outline'}
          disabled={pending}
          data-action={action}
          onClick={() => onAct(action)}
        >
          {t(`temporary_works.permit.${action}`)}
        </Button>
      ))}
    </div>
  )
}
