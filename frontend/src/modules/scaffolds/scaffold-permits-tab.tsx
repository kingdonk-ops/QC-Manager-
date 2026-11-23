import { Check, Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/records/status-badge'
import {
  useLinkedWorks,
  type LinkedItem,
  type LinkedPermit,
  type LinkedRollup,
  type Scaffold,
} from './api'

/** The scaffold's own state, shown beside the permit state: the one place both are read together. */
type ScaffoldState = Pick<
  Scaffold,
  'effective_tag' | 'inspection_overdue' | 'next_inspection_due'
>

const LIVE = ['issued', 'active']

/** The permit to load the item currently relies on: a live one if there is, otherwise the most recent. */
function currentLoadPermit(permits: LinkedPermit[], itemId: number) {
  const mine = permits.filter((p) => p.item_id === itemId && p.kind === 'load')
  return (
    mine.find((p) => LIVE.includes(p.status)) ??
    [...mine].sort((a, b) => b.id - a.id)[0]
  )
}

/**
 * What the temporary works tab shows for a scaffold. Every gate, breach and warning is the server's; nothing is worked
 * out here. `createHref` is the shortcut for editors (absent for viewers).
 */
export function PermitsPanel({
  scaffold,
  items,
  permits,
  rollup,
  createHref,
}: {
  scaffold: ScaffoldState
  items: LinkedItem[]
  permits: LinkedPermit[]
  rollup: LinkedRollup
  createHref?: string
}) {
  const { t } = useTranslation()
  const ids = new Set(items.map((i) => i.id))
  const breaches = rollup.breaches.filter(
    (b) => b.item_id !== null && ids.has(b.item_id)
  )
  const open = t('scaffolds.tw.open_ended')
  return (
    <div className='grid gap-3 text-sm' data-testid='scaffold-permits'>
      {breaches.length > 0 ? (
        <section
          role='alert'
          data-testid='scaffold-breach'
          className='rounded-md border border-red-600/50 bg-red-600/10 p-3'
        >
          <p className='font-semibold text-red-700 dark:text-red-400'>
            {t('scaffolds.tw.breach_title')}
          </p>
          <ul className='mt-1 grid gap-1'>
            {breaches.map((b, i) => (
              <li key={`${b.item_id}-${i}`} data-testid='scaffold-breach-reason'>
                {b.reference ? `${b.reference}: ` : ''}
                {b.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {scaffold.effective_tag === 'red' && breaches.length > 0 ? (
        <p
          data-testid='red-tag-note'
          className='rounded-md bg-red-600/10 p-2 text-red-700 dark:text-red-400'
        >
          {t('scaffolds.tw.red_tag_note')}
        </p>
      ) : null}
      <div
        data-testid='scaffold-inspection'
        data-overdue={scaffold.inspection_overdue ? 'true' : 'false'}
        className='flex flex-wrap items-center gap-2 rounded-md border p-2'
      >
        <span className='text-muted-foreground'>
          {t('scaffolds.tw.inspection')}
        </span>
        <span>
          {t('scaffolds.tw.next_due')}:{' '}
          {scaffold.next_inspection_due
            ? new Date(scaffold.next_inspection_due).toLocaleDateString()
            : t('scaffolds.tw.not_scheduled')}
        </span>
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-xs font-medium',
            scaffold.inspection_overdue
              ? 'bg-red-600 text-white'
              : 'bg-muted text-muted-foreground'
          )}
        >
          {scaffold.inspection_overdue
            ? t('scaffolds.tw.overdue')
            : t('scaffolds.tw.on_time')}
        </span>
      </div>
      {items.length === 0 ? (
        <p className='text-muted-foreground' data-testid='scaffold-no-items'>
          {t('scaffolds.tw.empty')}
        </p>
      ) : (
        <ul className='grid gap-2'>
          {items.map((item) => {
            const gate = rollup.gates.find((g) => g.item_id === item.id)
            const permit = currentLoadPermit(permits, item.id)
            const warnings = rollup.warnings.filter((w) => w.item_id === item.id)
            const breach = breaches.some((b) => b.item_id === item.id)
            return (
              <li
                key={item.id}
                data-testid='scaffold-item'
                data-breach={breach ? 'true' : 'false'}
                className={cn(
                  'grid gap-1 rounded-md border p-2',
                  breach && 'border-red-600/60 bg-red-600/5'
                )}
              >
                <div className='flex flex-wrap items-center gap-2'>
                  <span className='font-mono font-semibold'>
                    {item.reference}
                  </span>
                  <span className='flex-1'>{item.title}</span>
                  {breach ? (
                    <span
                      data-testid='scaffold-breach-tag'
                      className='rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white uppercase'
                    >
                      {t('scaffolds.tw.breach_tag')}
                    </span>
                  ) : null}
                  <StatusBadge status={item.status} />
                </div>
                <div className='flex flex-wrap items-center gap-3 text-xs'>
                  <span
                    data-testid='scaffold-load-gate'
                    data-ok={gate?.load_gate_open ? 'true' : 'false'}
                    className={cn(
                      'inline-flex items-center gap-1',
                      gate?.load_gate_open
                        ? 'text-green-700 dark:text-green-400'
                        : 'text-muted-foreground'
                    )}
                  >
                    {gate?.load_gate_open ? (
                      <Check className='size-3' />
                    ) : (
                      <X className='size-3' />
                    )}
                    {t('scaffolds.tw.load_gate')}:{' '}
                    {t(
                      gate?.load_gate_open
                        ? 'scaffolds.tw.gate_open'
                        : 'scaffolds.tw.gate_shut'
                    )}
                  </span>
                  <span data-testid='scaffold-permit'>
                    {permit
                      ? `${t('scaffolds.tw.permit')} ${permit.number} · ${permit.status} · ${t('scaffolds.tw.valid')} ${permit.valid_from ?? open} → ${permit.valid_to ?? open}`
                      : t('scaffolds.tw.no_permit')}
                  </span>
                </div>
                {warnings.length > 0 ? (
                  <ul className='list-disc ps-5 text-xs text-amber-700 dark:text-amber-400'>
                    {warnings.map((w, i) => (
                      <li key={`${w.rule}-${i}`}>{w.message}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
      <div className='flex flex-wrap gap-2'>
        <Button size='sm' variant='outline' asChild>
          <a href='/temporary-works' data-testid='scaffold-register-link'>
            {t('scaffolds.tw.register_link')}
          </a>
        </Button>
        {createHref ? (
          <Button size='sm' asChild>
            <a href={createHref} data-testid='scaffold-create-item'>
              <Plus /> {t('scaffolds.tw.new_item')}
            </a>
          </Button>
        ) : null}
      </div>
    </div>
  )
}

/**
 * The tab itself. When the temporary works module is off or the caller cannot read it (`on` false) it shows nothing
 * and makes no request.
 */
export function ScaffoldPermitsTab({
  scaffold,
  projectId,
  scaffoldId,
  on,
  canCreate,
}: {
  scaffold: ScaffoldState
  projectId: number
  scaffoldId: number
  on: boolean
  /** Whether the caller may create temporary works items (editors do, viewers do not). */
  canCreate: boolean
}) {
  const { t } = useTranslation()
  const { data } = useLinkedWorks(projectId, scaffoldId, on)
  if (!on) return null
  if (!data)
    return (
      <p className='text-sm text-muted-foreground'>
        {t('scaffolds.tw.loading')}
      </p>
    )
  return (
    <PermitsPanel
      scaffold={scaffold}
      items={data.items}
      permits={data.permits}
      rollup={data.rollup}
      createHref={
        canCreate
          ? `/temporary-works?new=scaffold&scaffold_id=${scaffoldId}`
          : undefined
      }
    />
  )
}
