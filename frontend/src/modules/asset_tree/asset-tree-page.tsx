import { useState } from 'react'
import { FileUp, Plus, ScanLine, Settings } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import {
  type Item,
  type TreeNode,
  useLevels,
  useNode,
  useNodeSearch,
  useTreeWrite,
} from './api'
import { CollectionsTab } from './collections'
import { ImportWizard } from './import-wizard'
import { ItemSheet, ItemsGrid } from './items'
import { AddNodeDialog, NodePanel } from './node-panel'
import { ScanDialog } from './scan-dialog'
import { SettingsDialog } from './settings-dialog'
import { useTerms } from './terminology'
import { TreeView } from './tree-view'

const ancestors = (node: { path: string }) =>
  node.path.split('/').filter(Boolean).map(Number).slice(0, -1)

function Explorer({ projectId }: { projectId: number }) {
  const session = useSession()
  const term = useTerms(projectId)
  const { data: levels = [] } = useLevels(projectId)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { data: selected = null } = useNode(selectedId)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const { data: found = [] } = useNodeSearch(projectId, search)
  const [showRetired, setShowRetired] = useState(false)
  const [itemId, setItemId] = useState<number | null>(null)
  const [dialog, setDialog] = useState<
    'scan' | 'import' | 'settings' | 'add-root' | null
  >(null)
  const [tab, setTab] = useState('details')
  const ctx = { projectId, levels, term }

  const reveal = (node: { id: number; path: string }) => {
    setExpanded((s) => new Set([...s, ...ancestors(node)]))
    setSelectedId(node.id)
  }
  const select = (id: number | null) => {
    setSelectedId(id)
    if (id)
      void unwrap(
        api.GET('/api/v1/asset-tree/nodes/{node_id}', {
          params: { path: { node_id: id } },
        })
      ).then(reveal)
  }
  const move = useTreeWrite(
    projectId,
    ({ nodeId, parentId }: { nodeId: number; parentId: number | null }) =>
      unwrap(
        api.POST('/api/v1/asset-tree/nodes/{node_id}/move', {
          params: { path: { node_id: nodeId } },
          body: { parent_id: parentId },
        })
      )
  )
  const canUpdate = can(session, 'asset_tree.update')

  if (!levels.length)
    return (
      <div className='grid max-w-xl gap-3 rounded-md border p-4 text-sm'>
        <p>
          This project has no breakdown yet. Start from a pack (for example Site
          / Area / Asset / RSW, or Scope / Job Package / Line) and change it to
          suit.
        </p>
        {can(session, 'asset_tree.configure') ? (
          <Button className='w-fit' onClick={() => setDialog('settings')}>
            <Settings /> Set up the breakdown
          </Button>
        ) : (
          <p className='text-muted-foreground'>
            Ask someone who can configure the breakdown to set it up.
          </p>
        )}
        {dialog === 'settings' ? (
          <SettingsDialog
            projectId={projectId}
            term={term}
            onClose={() => setDialog(null)}
          />
        ) : null}
      </div>
    )

  return (
    <div className='grid gap-4 lg:grid-cols-[minmax(280px,360px)_1fr]'>
      <aside className='grid content-start gap-2 rounded-md border p-2'>
        <div className='flex gap-1'>
          <Input
            className='h-8'
            placeholder={`Search ${levels.map((l) => term(`level.${l.key}`, 2)).join(', ')}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {can(session, 'asset_tree.create') ? (
            <Button
              size='icon'
              variant='outline'
              className='size-8 shrink-0'
              aria-label='Add at the top'
              onClick={() => setDialog('add-root')}
            >
              <Plus />
            </Button>
          ) : null}
        </div>
        {search.trim() ? (
          <ul className='grid gap-0.5 text-sm'>
            {found.map((n: TreeNode) => (
              <li key={n.id}>
                <button
                  type='button'
                  className='flex w-full items-center gap-2 rounded px-1 py-0.5 text-start hover:bg-muted'
                  onClick={() => {
                    reveal(n)
                    setSearch('')
                  }}
                >
                  <span className='shrink-0 text-[10px] text-muted-foreground uppercase'>
                    {term(`level.${n.level_key}`)}
                  </span>
                  <span className='truncate'>{n.display_path}</span>
                </button>
              </li>
            ))}
            {!found.length ? (
              <li className='p-1 text-muted-foreground'>No matches.</li>
            ) : null}
          </ul>
        ) : (
          <div className='max-h-[70vh] overflow-y-auto'>
            <TreeView
              projectId={projectId}
              selectedId={selectedId}
              expanded={expanded}
              onToggle={(id) =>
                setExpanded((s) => {
                  const next = new Set(s)
                  if (next.has(id)) next.delete(id)
                  else next.add(id)
                  return next
                })
              }
              onSelect={(n) => setSelectedId(n.id)}
              onMove={
                canUpdate
                  ? (nodeId, parentId) => move.mutate({ nodeId, parentId })
                  : undefined
              }
              showRetired={showRetired}
              term={term}
            />
          </div>
        )}
        <label className='flex items-center gap-1.5 text-xs text-muted-foreground'>
          <input
            type='checkbox'
            checked={showRetired}
            onChange={(e) => setShowRetired(e.target.checked)}
          />
          Show retired
        </label>
      </aside>
      <section className='min-w-0'>
        <div className='mb-2 flex flex-wrap justify-end gap-2'>
          <Button size='sm' variant='outline' onClick={() => setDialog('scan')}>
            <ScanLine /> Scan
          </Button>
          {can(session, 'asset_tree.import') ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setDialog('import')}
            >
              <FileUp /> Import
            </Button>
          ) : null}
          {can(session, 'asset_tree.configure') ? (
            <Button
              size='sm'
              variant='outline'
              aria-label='Breakdown settings'
              onClick={() => setDialog('settings')}
            >
              <Settings />
            </Button>
          ) : null}
        </div>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value='details'>Details</TabsTrigger>
            <TabsTrigger value='items'>{term('noun.item', 2)}</TabsTrigger>
            <TabsTrigger value='collections'>
              {term('noun.collection', 2)}
            </TabsTrigger>
          </TabsList>
          <TabsContent value='details' className='pt-2'>
            {selectedId ? (
              <NodePanel ctx={ctx} nodeId={selectedId} onSelect={select} />
            ) : (
              <p className='text-sm text-muted-foreground'>
                Pick a {term('noun.node').toLowerCase()} in the tree, search for
                one, or scan a tag.
              </p>
            )}
          </TabsContent>
          <TabsContent value='items' className='pt-2'>
            <ItemsGrid
              projectId={projectId}
              node={selected}
              term={term}
              onOpen={setItemId}
            />
          </TabsContent>
          <TabsContent value='collections' className='pt-2'>
            <CollectionsTab
              projectId={projectId}
              selectedNode={selected}
              term={term}
              onSelect={(id) => {
                select(id)
                setTab('details')
              }}
            />
          </TabsContent>
        </Tabs>
      </section>
      <ItemSheet
        projectId={projectId}
        id={itemId}
        onClose={() => setItemId(null)}
        term={term}
      />
      {dialog === 'scan' ? (
        <ScanDialog
          projectId={projectId}
          term={term}
          onClose={() => setDialog(null)}
          onFound={(item: Item) => {
            select(item.node_id)
            setItemId(item.id)
          }}
        />
      ) : null}
      {dialog === 'import' ? (
        <ImportWizard
          projectId={projectId}
          levels={levels}
          term={term}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === 'settings' ? (
        <SettingsDialog
          projectId={projectId}
          term={term}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === 'add-root' ? (
        <AddNodeDialog
          ctx={ctx}
          parent={null}
          onClose={() => setDialog(null)}
          onCreated={(n) => setSelectedId(n.id)}
        />
      ) : null}
    </div>
  )
}

export default function AssetTreePage() {
  const project = useCurrentProject()
  return (
    <Page
      title='Asset hierarchy'
      description='The project breakdown, its items and scan tags, job packs and shutdown windows.'
      projectScoped
    >
      {project ? (
        <Explorer key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          Choose a project in the top bar.
        </p>
      )}
    </Page>
  )
}
