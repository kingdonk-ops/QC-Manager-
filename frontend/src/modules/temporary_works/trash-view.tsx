import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/records/status-badge'
import {
  useRestoreItem,
  useRestorePermit,
  useTrashItems,
  useTrashPermits,
  type DeletedItem,
  type DeletedPermit,
  type TrashView,
} from './api'
import { RetentionSetting } from './retention-setting'
import { PERM, familyKey, kindKey } from './rules'

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString() : '—'

function Row({
  title,
  detail,
  status,
  deletedAt,
  purgeOn,
  canRestore,
  pending,
  onRestore,
}: {
  title: string
  detail: string
  status: string
  deletedAt: string | null | undefined
  purgeOn?: string | null
  canRestore: boolean
  pending?: boolean
  onRestore: () => void
}) {
  const { t } = useTranslation()
  return (
    <li
      data-testid='trash-row'
      className='flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border p-3 text-sm'
    >
      <span className='font-mono font-semibold'>{title}</span>
      <span className='min-w-32 flex-1'>{detail}</span>
      <StatusBadge status={status} />
      <span className='text-xs text-muted-foreground'>
        {t('temporary_works.trash.deleted_at')}: {when(deletedAt)}
      </span>
      {purgeOn ? (
        <span
          data-testid='purge-on'
          className='text-xs text-muted-foreground'
        >
          {t('temporary_works.trash.purge_on')}: {when(purgeOn)}
        </span>
      ) : null}
      {canRestore ? (
        <Button
          size='sm'
          variant='outline'
          data-testid='restore-button'
          disabled={pending}
          onClick={onRestore}
        >
          {t('temporary_works.trash.restore')}
        </Button>
      ) : null}
    </li>
  )
}

/** The deleted items and permits of one view, each with Restore when the caller may restore. */
export function TrashLists({
  items,
  permits,
  view,
  canRestore,
  pending,
  onRestoreItem,
  onRestorePermit,
}: {
  items: DeletedItem[]
  permits: DeletedPermit[]
  view: TrashView
  canRestore: boolean
  pending?: boolean
  onRestoreItem: (id: number) => void
  onRestorePermit: (id: number) => void
}) {
  const { t } = useTranslation()
  return (
    <div className='grid gap-4' data-testid='trash-lists' data-view={view}>
      <section className='grid gap-2'>
        <h4 className='text-sm font-medium'>
          {t('temporary_works.trash.items')}
        </h4>
        {items.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('temporary_works.trash.empty')}
          </p>
        ) : (
          <ul className='grid gap-2'>
            {items.map((i) => (
              <Row
                key={i.id}
                title={i.reference}
                detail={`${i.title} · ${t(familyKey(i.family))}`}
                status={i.status}
                deletedAt={i.deleted_at}
                purgeOn={view === 'bin' ? i.purge_on : null}
                canRestore={canRestore}
                pending={pending}
                onRestore={() => onRestoreItem(i.id)}
              />
            ))}
          </ul>
        )}
      </section>
      <section className='grid gap-2'>
        <h4 className='text-sm font-medium'>
          {t('temporary_works.trash.permits')}
        </h4>
        {permits.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('temporary_works.trash.empty')}
          </p>
        ) : (
          <ul className='grid gap-2'>
            {permits.map((p) => (
              <Row
                key={p.id}
                title={p.number}
                detail={t(kindKey(p.kind))}
                status={p.status}
                deletedAt={p.deleted_at}
                purgeOn={view === 'bin' ? p.purge_on : null}
                canRestore={canRestore}
                pending={pending}
                onRestore={() => onRestorePermit(p.id)}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

/**
 * The recycle bin or the Deleted folder: a separate view each, only for people with the restore permission. The bin
 * also carries the retention setting.
 */
export function TrashPanel({
  projectId,
  view,
}: {
  projectId: number
  view: TrashView
}) {
  const { t } = useTranslation()
  const session = useSession()
  const items = useTrashItems(projectId, view)
  const permits = useTrashPermits(projectId, view)
  const restoreItem = useRestoreItem()
  const restorePermit = useRestorePermit()
  const done = () => toast.success(t('temporary_works.trash.restored'))
  return (
    <div className='grid gap-4'>
      <p className='text-sm text-muted-foreground'>
        {t(
          view === 'bin'
            ? 'temporary_works.trash.bin_help'
            : 'temporary_works.trash.folder_help'
        )}
      </p>
      {view === 'bin' ? <RetentionSetting projectId={projectId} /> : null}
      <TrashLists
        view={view}
        items={items.data?.rows ?? []}
        permits={permits.data?.rows ?? []}
        canRestore={can(session, PERM.restore)}
        pending={restoreItem.isPending || restorePermit.isPending}
        onRestoreItem={(id) => restoreItem.mutate(id, { onSuccess: done })}
        onRestorePermit={(id) =>
          restorePermit.mutate(id, { onSuccess: done })
        }
      />
    </div>
  )
}
