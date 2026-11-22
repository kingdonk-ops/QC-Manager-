import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import { ExportTab } from './export-tab'
import { ImportTab } from './import-tab'
import { RulesTab } from './rules-tab'
import { UnmatchedTab } from './unmatched-tab'

function initialTab() {
  const tab = new URLSearchParams(window.location.search).get('tab')
  return tab && ['import', 'unmatched', 'rules', 'export'].includes(tab)
    ? tab
    : 'import'
}

export default function P6Page() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const importer = can(session, 'schedule.import')
  return (
    <Page title={t('p6.title')} description={t('p6.description')} projectScoped>
      {project ? (
        <Tabs
          key={project.id}
          defaultValue={importer ? initialTab() : 'export'}
        >
          <TabsList>
            {importer ? (
              <>
                <TabsTrigger value='import'>{t('p6.tab.import')}</TabsTrigger>
                <TabsTrigger value='unmatched'>
                  {t('p6.tab.unmatched')}
                </TabsTrigger>
                <TabsTrigger value='rules'>{t('p6.tab.rules')}</TabsTrigger>
              </>
            ) : null}
            <TabsTrigger value='export'>{t('p6.tab.export')}</TabsTrigger>
          </TabsList>
          {importer ? (
            <>
              <TabsContent value='import'>
                <ImportTab projectId={project.id} />
              </TabsContent>
              <TabsContent value='unmatched'>
                <UnmatchedTab projectId={project.id} />
              </TabsContent>
              <TabsContent value='rules'>
                <RulesTab projectId={project.id} />
              </TabsContent>
            </>
          ) : null}
          <TabsContent value='export'>
            <ExportTab projectId={project.id} />
          </TabsContent>
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>{t('p6.no_project')}</p>
      )}
    </Page>
  )
}
