import { useEffect } from 'react'
import { Link } from '@tanstack/react-router'
import { useProjects } from '@/modules/projects/api'
import { Building2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useProjectStore } from '@/stores/project-store'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** The workspace's current project, shared by every project-scoped module. */
export function ProjectSelector() {
  const { t } = useTranslation()
  const { data: projects = [] } = useProjects()
  const { projectId, setProjectId } = useProjectStore()

  useEffect(() => {
    if (projects.length && !projects.some((p) => p.id === projectId)) {
      setProjectId(projects[0].id)
    }
  }, [projects, projectId, setProjectId])

  if (!projects.length) {
    return (
      <span className='text-sm text-muted-foreground'>
        {t('project.none')}{' '}
        <Link to='/$' params={{ _splat: 'lobby' }} className='underline'>
          {t('project.browse')}
        </Link>
      </span>
    )
  }

  return (
    <Select
      value={projectId ? String(projectId) : undefined}
      onValueChange={(value) => setProjectId(Number(value))}
    >
      <SelectTrigger size='sm' className='h-8 max-w-72 gap-2 font-medium'>
        <Building2 className='size-4 text-muted-foreground' />
        <SelectValue placeholder={t('project.select')} />
      </SelectTrigger>
      <SelectContent>
        {projects.map((p) => (
          <SelectItem key={p.id} value={String(p.id)}>
            <span className='font-mono text-xs text-muted-foreground'>
              {p.code}
            </span>{' '}
            {p.name}
            {p.location ? (
              <span className='text-muted-foreground'> — {p.location}</span>
            ) : null}
          </SelectItem>
        ))}
        <Link
          to='/$'
          params={{ _splat: 'lobby' }}
          className='block border-t px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground'
        >
          {t('project.browse')}
        </Link>
      </SelectContent>
    </Select>
  )
}
