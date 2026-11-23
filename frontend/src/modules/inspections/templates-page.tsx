import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowLeft, Copy, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/layout/page'
import { type Template, useTemplateAction, useTemplates } from './api'
import { ChecklistEditor } from './checklist-editor'
import { ItpEditor } from './itp-editor'
import { PointBadges } from './signoff'
import { TemplatesLayout } from './templates-layout'

function Templates({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'inspections.update')
  const { data: templates = [] } = useTemplates(projectId)
  const action = useTemplateAction(projectId)
  const [selected, setSelected] = useState<number | 'new' | 'new-itp' | null>(
    null
  )
  const current =
    selected === 'new' || selected === 'new-itp'
      ? null
      : templates.find((tpl) => tpl.id === selected)
  const itp = selected === 'new-itp' || current?.kind === 'itp'

  return (
    <TemplatesLayout
      toolbar={
        editable ? (
          <>
            <Button size='sm' onClick={() => setSelected('new')}>
              <Plus /> {t('inspections.new_template')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={() => setSelected('new-itp')}
            >
              <Plus /> {t('inspections.new_itp')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              onClick={() => action.mutate({ action: 'starter' })}
            >
              <Sparkles /> {t('inspections.starters')}
            </Button>
          </>
        ) : null
      }
      list={templates.map((tpl) => (
        <button
          key={tpl.id}
          onClick={() => setSelected(tpl.id)}
          className={cn(
            'grid gap-0.5 rounded-md border px-3 py-2 text-start text-sm hover:bg-muted',
            selected === tpl.id && 'border-primary bg-muted'
          )}
        >
          <span className='font-medium'>{tpl.name}</span>
          <span className='text-xs text-muted-foreground'>
            {[
              tpl.kind === 'itp' ? 'ITP' : t(`inspections.areas.${tpl.area}`),
              tpl.is_formal ? t('inspections.formal_short') : null,
              tpl.trade,
              `v${tpl.version}`,
              `${tpl.item_count} ${t('inspections.items')}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </button>
      ))}
    >
      <>
        {selected === null ? (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.pick_template')}
          </p>
        ) : !editable && current ? (
          <Card>
            <CardHeader>
              <CardTitle>{current.name}</CardTitle>
            </CardHeader>
            <CardContent className='grid gap-3'>
              {current.sections.map((s) => (
                <div key={s.title}>
                  <p className='font-medium'>{s.title}</p>
                  <ul className='list-disc ps-5 text-sm'>
                    {(s.items ?? []).map((i) => (
                      <li key={i.text}>{i.text}</li>
                    ))}
                  </ul>
                </div>
              ))}
              {(current.activities ?? []).length ? (
                <ol className='grid list-decimal gap-1 ps-5 text-sm'>
                  {(current.activities ?? []).map((a, i) => (
                    <li key={i}>
                      <span className='me-2'>{a.title}</span>
                      <PointBadges points={a.points ?? {}} />
                    </li>
                  ))}
                </ol>
              ) : null}
            </CardContent>
          </Card>
        ) : (
          <div className='grid gap-3'>
            {current ? (
              <div className='flex flex-wrap items-center gap-2'>
                <Badge variant='secondary'>v{current.version}</Badge>
                <Button
                  size='sm'
                  variant='outline'
                  className='ms-auto'
                  onClick={() =>
                    action.mutate(
                      { id: current.id, action: 'duplicate' },
                      {
                        onSuccess: (copy) => setSelected((copy as Template).id),
                      }
                    )
                  }
                >
                  <Copy /> {t('inspections.duplicate')}
                </Button>
                {can(session, 'inspections.delete') ? (
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() =>
                      action.mutate(
                        { id: current.id, action: 'delete' },
                        { onSuccess: () => setSelected(null) }
                      )
                    }
                  >
                    <Trash2 /> {t('inspections.delete')}
                  </Button>
                ) : null}
              </div>
            ) : null}
            {itp ? (
              <ItpEditor
                key={`${selected}-${current?.version ?? 0}`}
                projectId={projectId}
                template={current ?? null}
                onSaved={(saved) => setSelected(saved.id)}
              />
            ) : (
              <ChecklistEditor
                key={`${selected}-${current?.version ?? 0}`}
                projectId={projectId}
                template={current ?? null}
                onSaved={(saved) => setSelected(saved.id)}
              />
            )}
          </div>
        )}
      </>
    </TemplatesLayout>
  )
}

export default function TemplatesPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.templates')}
      description={t('inspections.templates_description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      {project ? (
        <Templates key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_project')}
        </p>
      )}
    </Page>
  )
}
