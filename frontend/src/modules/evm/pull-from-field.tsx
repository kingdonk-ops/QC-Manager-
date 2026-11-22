import { HardHat } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { usePullFromField } from './api'

/** Updates the data date's progress from signed workface logs and verified progress. */
export function PullFromField({
  projectId,
  dataDate,
}: {
  projectId: number
  dataDate: string
}) {
  const { t } = useTranslation()
  const pull = usePullFromField(projectId)
  return (
    <Button
      size='sm'
      variant='outline'
      title={t('evm.pull_field_help')}
      disabled={pull.isPending}
      onClick={() =>
        pull.mutate(dataDate, {
          onSuccess: (res) => toast.success(t('evm.pulled', { count: res.saved })),
        })
      }
    >
      <HardHat /> {t('evm.pull_field')}
    </Button>
  )
}
