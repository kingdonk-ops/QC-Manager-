import { Link } from '@tanstack/react-router'
import { CalendarClock, Lock, ListChecks, Percent } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent } from '@/components/ui/card'
import { useDashboard } from './quality-api'

function Tile({
  icon: Icon,
  label,
  value,
  hint,
  to,
}: {
  icon: typeof Lock
  label: string
  value: React.ReactNode
  hint?: string
  to?: string
}) {
  const body = (
    <Card className='h-full transition-colors hover:bg-muted/50'>
      <CardContent className='flex items-start gap-3 p-4'>
        <Icon className='mt-1 size-5 text-muted-foreground' />
        <div className='grid gap-0.5'>
          <p className='text-2xl font-semibold tabular-nums'>{value}</p>
          <p className='text-sm'>{label}</p>
          {hint ? (
            <p className='text-xs text-muted-foreground'>{hint}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
  return to ? (
    <Link to='/$' params={{ _splat: to }}>
      {body}
    </Link>
  ) : (
    body
  )
}

/** Open call-outs, Hold points awaiting release, records due, acceptance rate. */
export function DashboardTiles({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data } = useDashboard(projectId)
  if (!data) return null
  return (
    <div className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
      <Tile
        icon={CalendarClock}
        label={t('inspections.tile.open_requests')}
        value={data.open_requests}
        hint={t('inspections.tile.today', { count: data.requests_today })}
        to='inspections/requests'
      />
      <Tile
        icon={Lock}
        label={t('inspections.tile.holds')}
        value={data.holds_awaiting_release}
        hint={t('inspections.tile.holds_open', { count: data.holds_open })}
        to='inspections/itp'
      />
      <Tile
        icon={ListChecks}
        label={t('inspections.tile.due')}
        value={data.inspections_due}
        hint={t('inspections.tile.overdue', {
          count: data.overdue,
          review: data.awaiting_review,
        })}
      />
      <Tile
        icon={Percent}
        label={t('inspections.tile.pass_rate')}
        value={data.pass_rate === null ? '—' : `${data.pass_rate}%`}
        hint={t('inspections.tile.pass_counts', {
          passed: data.passed,
          failed: data.failed,
        })}
      />
    </div>
  )
}
