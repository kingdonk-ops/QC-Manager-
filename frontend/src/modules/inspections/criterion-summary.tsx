import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useCriteria } from './criteria-api'
import { criterionLabel } from './criterion-label'

type Summarised = {
  project_id: number
  criterion_id?: number | null
  measured_value?: string | null
  conditional?: boolean
  report_id?: number | null
}

/** The criterion clause, measured value, conditional flag and linked report of one record. */
export function CriterionSummary({ inspection }: { inspection: Summarised }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: criteria = [] } = useCriteria(inspection.project_id)
  const criterion = criteria.find((c) => c.id === inspection.criterion_id)
  if (
    !inspection.criterion_id &&
    !inspection.measured_value &&
    !inspection.conditional &&
    !inspection.report_id
  )
    return null
  return (
    <div
      data-testid='criterion-summary'
      className='flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border p-2 text-sm'
    >
      {inspection.criterion_id ? (
        <span>
          <span className='text-muted-foreground'>
            {t('inspections.criterion.clause')}:
          </span>{' '}
          {criterion ? criterionLabel(criterion) : `#${inspection.criterion_id}`}
        </span>
      ) : null}
      {inspection.measured_value ? (
        <span>
          <span className='text-muted-foreground'>
            {t('inspections.criterion.measured_value')}:
          </span>{' '}
          {inspection.measured_value}
          {criterion?.unit ? ` ${criterion.unit}` : ''}
        </span>
      ) : null}
      {inspection.conditional ? (
        <Badge variant='outline'>{t('inspections.criterion.conditional')}</Badge>
      ) : null}
      {inspection.report_id ? (
        <Button
          type='button'
          variant='link'
          className='h-auto px-1 text-sm'
          onClick={() =>
            void navigate({ to: `/ncr?id=${inspection.report_id}` as never })
          }
        >
          {t('inspections.criterion.open_report', { id: inspection.report_id })}
        </Button>
      ) : null}
    </div>
  )
}

/** The code of the criterion an item is judged against. */
export function ItemCriterion({
  projectId,
  criterionId,
}: {
  projectId: number
  criterionId: number
}) {
  const { t } = useTranslation()
  const { data: criteria = [] } = useCriteria(projectId)
  const found = criteria.find((c) => c.id === criterionId)
  return (
    <Badge variant='outline' title={t('inspections.criterion.clause')}>
      {found ? criterionLabel(found) : `#${criterionId}`}
    </Badge>
  )
}
