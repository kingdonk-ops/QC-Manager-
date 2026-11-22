import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { api, unwrap } from '@/api/client'
import { useProjectStore } from '@/stores/project-store'
import { useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/layout/page'
import { useProjects } from '../projects/api'

export default function OverviewPage() {
  const { t } = useTranslation()
  const session = useSession()
  const { data: projects = [] } = useProjects()
  const setProjectId = useProjectStore((s) => s.setProjectId)
  const { data: teams = [] } = useQuery({
    queryKey: ['teams', 'mine'],
    queryFn: () => unwrap(api.GET('/api/v1/teams/mine')),
  })

  return (
    <Page title={t('overview.title', { name: session.name.split(' ')[0] })}>
      <div className='grid gap-4 md:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              {t('overview.projects')}
            </CardTitle>
          </CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            {projects.length === 0 ? (
              <p className='text-muted-foreground'>{t('overview.none')}</p>
            ) : null}
            {projects.map((p) => (
              <Link
                key={p.id}
                to='/$'
                params={{ _splat: 'projects' }}
                onClick={() => setProjectId(p.id)}
                className='flex items-center justify-between rounded-md border px-3 py-2 hover:bg-accent'
              >
                <span>
                  <span className='font-mono text-xs text-muted-foreground'>
                    {p.code}
                  </span>{' '}
                  {p.name}
                </span>
                <Badge variant='outline'>{p.status}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>{t('overview.teams')}</CardTitle>
          </CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            {teams.length === 0 ? (
              <p className='text-muted-foreground'>{t('overview.none')}</p>
            ) : null}
            {teams.map((team) => (
              <div
                key={team.id}
                className='flex items-center justify-between rounded-md border px-3 py-2'
              >
                <span>{team.name}</span>
                <Badge variant='secondary'>{team.my_role}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}
