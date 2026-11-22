import { useState } from 'react'
import { Copy, FileDown, Pencil, Plus, Sheet, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Page } from '@/components/layout/page'
import {
  type Template,
  useCopyTemplate,
  useDeleteTemplate,
  useDownload,
  useTemplates,
} from './api'
import { TemplateEditor } from './template-editor'

export default function TemplatesPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const { data: templates = [], isLoading } = useTemplates()
  const [editing, setEditing] = useState<Template | 'new' | null>(null)
  const copy = useCopyTemplate()
  const remove = useDeleteTemplate()
  const download = useDownload()

  const generate = (id: number, format: 'pdf' | 'xlsx') =>
    download.mutate({
      url: '/api/v1/reporting/generate',
      body: { template_id: id, project_id: project?.id, format },
    })

  if (editing)
    return (
      <Page
        title={editing === 'new' ? t('reporting.new_template') : editing.name}
        description={t('reporting.builder_description')}
      >
        <TemplateEditor
          template={editing === 'new' ? null : editing}
          onDone={() => setEditing(null)}
        />
      </Page>
    )

  return (
    <Page
      title={t('reporting.templates')}
      description={t('reporting.templates_description')}
      projectScoped
      actions={
        can(session, 'reporting.create') ? (
          <Button size='sm' onClick={() => setEditing('new')}>
            <Plus /> {t('reporting.new_template')}
          </Button>
        ) : null
      }
    >
      {isLoading ? (
        <p className='text-sm text-muted-foreground'>{t('common.loading')}</p>
      ) : null}
      <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-3'>
        {templates.map((tpl) => (
          <Card key={tpl.id} className='gap-2'>
            <CardHeader>
              <CardTitle className='flex items-center gap-2 text-base'>
                {tpl.name}
                {tpl.builtin_key ? (
                  <Badge variant='secondary'>{t('reporting.builtin')}</Badge>
                ) : null}
              </CardTitle>
              <CardDescription>{tpl.description}</CardDescription>
            </CardHeader>
            <CardContent className='flex flex-col gap-3'>
              <div className='flex flex-wrap gap-1'>
                {tpl.sections.map((s, i) => (
                  <Badge key={i} variant='outline' className='font-normal'>
                    {s.title || t(`reporting.section_${s.type}`)}
                  </Badge>
                ))}
              </div>
              <div className='flex flex-wrap gap-2'>
                {can(session, 'reporting.export') ? (
                  <>
                    <Button
                      size='sm'
                      onClick={() => generate(tpl.id, 'pdf')}
                      disabled={download.isPending}
                    >
                      <FileDown /> PDF
                    </Button>
                    <Button
                      size='sm'
                      variant='outline'
                      onClick={() => generate(tpl.id, 'xlsx')}
                      disabled={download.isPending}
                    >
                      <Sheet /> Excel
                    </Button>
                  </>
                ) : null}
                {can(session, 'reporting.create') ? (
                  <Button
                    size='sm'
                    variant='ghost'
                    onClick={() => copy.mutate(tpl.id)}
                  >
                    <Copy /> {t('reporting.copy')}
                  </Button>
                ) : null}
                {!tpl.builtin_key && can(session, 'reporting.update') ? (
                  <Button
                    size='sm'
                    variant='ghost'
                    onClick={() => setEditing(tpl)}
                  >
                    <Pencil /> {t('reporting.edit')}
                  </Button>
                ) : null}
                {!tpl.builtin_key && can(session, 'reporting.delete') ? (
                  <Button
                    size='sm'
                    variant='ghost'
                    className='hover:text-red-600'
                    aria-label={t('reporting.delete')}
                    onClick={() => remove.mutate(tpl.id)}
                  >
                    <Trash2 />
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {!project ? (
        <p className='text-xs text-muted-foreground'>
          {t('reporting.templates_project_hint')}
        </p>
      ) : null}
    </Page>
  )
}
