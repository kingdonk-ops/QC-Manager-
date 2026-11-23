import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/layout/page'
import {
  refusalText,
  useItems,
  usePermitStep,
  usePermits,
  useRollup,
  type Item,
  type Permit,
} from './api'
import {
  DeleteDialog,
  ReturnToDraftDialog,
  type Target,
} from './draft-dialogs'
import { ItemDialog } from './item-dialog'
import type { RowActions } from './item-rows'
import { PermitDialog } from './permit-dialog'
import { RegisterBody } from './register-body'
import { PERM, type ItemAction, type PermitAction } from './rules'
import { TransitionDialog } from './transition-dialog'
import { TrashPanel } from './trash-view'

type Open =
  | {
      kind: 'item'
      item?: Item
      preset?: { family?: string; scaffold_id?: number }
    }
  | { kind: 'permit'; item: Item; permit?: Permit }
  | { kind: 'transition'; item: Item }
  | { kind: 'return'; target: Target }
  | { kind: 'delete'; target: Target }

function RegisterScreen({
  projectId,
  setOpen,
}: {
  projectId: number
  setOpen: (next: Open | null) => void
}) {
  const session = useSession()
  const items = useItems(projectId)
  const permits = usePermits(projectId)
  const rollup = useRollup(projectId)
  const step = usePermitStep()
  const has = (permission: string) => can(session, permission)
  const actions: RowActions = {
    onItem: (item: Item, action: ItemAction) => {
      if (action === 'edit') setOpen({ kind: 'item', item })
      else if (action === 'transition') setOpen({ kind: 'transition', item })
      else if (action === 'add_permit') setOpen({ kind: 'permit', item })
      else
        setOpen({
          kind: action === 'return' ? 'return' : 'delete',
          target: { kind: 'item', id: item.id, label: item.reference },
        })
    },
    onPermit: (item: Item, permit: Permit, action: PermitAction) => {
      if (action === 'edit') setOpen({ kind: 'permit', item, permit })
      else if (action === 'return' || action === 'delete')
        setOpen({
          kind: action,
          target: { kind: 'permit', id: permit.id, label: permit.number },
        })
      else
        step.mutate(
          { id: permit.id, step: action },
          { onError: (e) => toast.error(refusalText(e)) }
        )
    },
  }
  return (
    <RegisterBody
      rollup={rollup.data}
      items={items.data?.rows ?? []}
      total={items.data?.total ?? 0}
      permits={permits.data?.rows ?? []}
      loading={items.isPending}
      has={has}
      actions={actions}
    />
  )
}

/** The dialogs sit at page level so the New item button works from any tab. */
function Dialogs({
  projectId,
  open,
  setOpen,
}: {
  projectId: number
  open: Open | null
  setOpen: (next: Open | null) => void
}) {
  const close = () => setOpen(null)
  return (
    <>
      {open?.kind === 'item' ? (
        <ItemDialog
          projectId={projectId}
          item={open.item}
          preset={open.preset}
          onClose={close}
        />
      ) : null}
      {open?.kind === 'permit' ? (
        <PermitDialog item={open.item} permit={open.permit} onClose={close} />
      ) : null}
      {open?.kind === 'transition' ? (
        <TransitionDialog item={open.item} onClose={close} />
      ) : null}
      {open?.kind === 'return' ? (
        <ReturnToDraftDialog target={open.target} onClose={close} />
      ) : null}
      {open?.kind === 'delete' ? (
        <DeleteDialog target={open.target} onClose={close} />
      ) : null}
    </>
  )
}

/**
 * A scaffold's record links here with `?new=scaffold&scaffold_id=7` to start an item for that scaffold, so the two
 * modules share nothing but the address.
 */
function startFromAddress(): Open | null {
  const params = new URLSearchParams(window.location.search)
  if (params.get('new') !== 'scaffold') return null
  const id = Number(params.get('scaffold_id'))
  return {
    kind: 'item',
    preset: {
      family: 'scaffold',
      scaffold_id: Number.isInteger(id) && id > 0 ? id : undefined,
    },
  }
}

export default function TemporaryWorksPage() {
  const { t } = useTranslation()
  const session = useSession()
  const project = useCurrentProject()
  const [open, setOpen] = useState<Open | null>(() =>
    can(session, PERM.create) ? startFromAddress() : null
  )
  const canRestore = can(session, PERM.restore)
  return (
    <Page
      title={t('temporary_works.title')}
      description={t('temporary_works.description')}
      projectScoped
      actions={
        project && can(session, PERM.create) ? (
          <Button size='sm' onClick={() => setOpen({ kind: 'item' })}>
            <Plus /> {t('temporary_works.new_item')}
          </Button>
        ) : null
      }
    >
      {project ? (
        <Tabs defaultValue='register' key={project.id}>
          <TabsList>
            <TabsTrigger value='register'>
              {t('temporary_works.register')}
            </TabsTrigger>
            {canRestore ? (
              <TabsTrigger value='bin'>
                {t('temporary_works.recycle_bin')}
              </TabsTrigger>
            ) : null}
            {canRestore ? (
              <TabsTrigger value='deleted'>
                {t('temporary_works.deleted_folder')}
              </TabsTrigger>
            ) : null}
          </TabsList>
          <TabsContent value='register'>
            <RegisterScreen projectId={project.id} setOpen={setOpen} />
          </TabsContent>
          {canRestore ? (
            <TabsContent value='bin'>
              <TrashPanel projectId={project.id} view='bin' />
            </TabsContent>
          ) : null}
          {canRestore ? (
            <TabsContent value='deleted'>
              <TrashPanel projectId={project.id} view='deleted' />
            </TabsContent>
          ) : null}
          <Dialogs projectId={project.id} open={open} setOpen={setOpen} />
        </Tabs>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('temporary_works.no_project')}
        </p>
      )}
    </Page>
  )
}
