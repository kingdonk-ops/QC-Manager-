import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/records/status-badge'
import type { Item, Permit, Rollup } from './api'
import { PermitActions } from './permit-actions'
import {
  categoryKey,
  familyKey,
  itemActions,
  kindKey,
  permitStatusKey,
  type ItemAction,
  type PermitAction,
} from './rules'

type Gate = Rollup['gates'][number]
type Warning = Rollup['warnings'][number]

export type RowActions = {
  onItem: (item: Item, action: ItemAction) => void
  onPermit: (item: Item, permit: Permit, action: PermitAction) => void
}

/** A yes/no indicator the server already decided. */
function Indicator({
  ok,
  label,
  testId,
}: {
  ok: boolean | undefined
  label: string
  testId?: string
}) {
  return (
    <span
      data-testid={testId}
      data-ok={ok ? 'true' : 'false'}
      className={cn(
        'inline-flex items-center gap-1 text-xs',
        ok ? 'text-green-700 dark:text-green-400' : 'text-muted-foreground'
      )}
    >
      {ok ? <Check className='size-3' /> : <X className='size-3' />}
      {label}
    </span>
  )
}

export function PermitTable({
  item,
  permits,
  has,
  onPermit,
}: {
  item: Item
  permits: Permit[]
  has: (permission: string) => boolean
  onPermit: RowActions['onPermit']
}) {
  const { t } = useTranslation()
  if (permits.length === 0)
    return (
      <p className='text-sm text-muted-foreground'>
        {t('temporary_works.no_permits')}
      </p>
    )
  const open = t('temporary_works.open_ended')
  return (
    <table className='w-full text-sm' data-testid='permit-table'>
      <thead className='text-left text-muted-foreground'>
        <tr>
          <th>{t('temporary_works.permit_number')}</th>
          <th>{t('temporary_works.permit_kind')}</th>
          <th>{t('temporary_works.permit_status')}</th>
          <th>{t('temporary_works.permit_validity')}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {permits.map((p) => (
          <tr key={p.id} className='border-t align-top' data-permit={p.id}>
            <td className='font-mono'>{p.number}</td>
            <td>{t(kindKey(p.kind))}</td>
            <td>
              <span data-testid='permit-status'>
                {t(permitStatusKey(p.status))}
              </span>
            </td>
            <td>
              <div data-testid='permit-validity'>
                {p.valid_from ?? open} → {p.valid_to ?? open}
              </div>
              {p.kind === 'load' ? (
                <div className='flex flex-wrap gap-3'>
                  <Indicator
                    testId='prereq-design'
                    ok={p.design_check_accepted}
                    label={t('temporary_works.design_check_accepted')}
                  />
                  <Indicator
                    testId='prereq-inspection'
                    ok={p.inspection_passed}
                    label={t('temporary_works.inspection_passed')}
                  />
                </div>
              ) : null}
            </td>
            <td className='text-end'>
              <PermitActions
                status={p.status}
                has={has}
                onAct={(action) => onPermit(item, p, action)}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ItemRow({
  item,
  permits,
  gate,
  breach,
  warnings,
  has,
  actions,
}: {
  item: Item
  permits: Permit[]
  gate?: Gate
  breach: boolean
  warnings: Warning[]
  has: (permission: string) => boolean
  actions: RowActions
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const buttons = itemActions(item.status, item.held_from, has)
  return (
    <li
      data-testid='item-row'
      data-item={item.id}
      data-breach={breach ? 'true' : 'false'}
      className={cn(
        'rounded-md border',
        breach && 'border-red-600/60 bg-red-600/5'
      )}
    >
      <button
        type='button'
        aria-expanded={open}
        aria-label={`${open ? t('temporary_works.collapse') : t('temporary_works.expand')}: ${item.reference}`}
        onClick={() => setOpen(!open)}
        className='flex w-full flex-wrap items-center gap-x-3 gap-y-1 p-3 text-start'
      >
        {open ? (
          <ChevronDown className='size-4' />
        ) : (
          <ChevronRight className='size-4' />
        )}
        <span className='font-mono text-sm font-semibold'>{item.reference}</span>
        <span className='min-w-40 flex-1 text-sm'>{item.title}</span>
        {breach ? (
          <span
            data-testid='breach-tag'
            className='rounded bg-red-600 px-2 py-0.5 text-xs font-semibold text-white uppercase'
          >
            {t('temporary_works.breach_tag')}
          </span>
        ) : null}
        <span className='text-xs text-muted-foreground'>
          {t(familyKey(item.family))}
        </span>
        <StatusBadge status={item.status} />
        {gate ? (
          <span className='flex gap-3'>
            <Indicator
              testId='load-gate'
              ok={gate.load_gate_open}
              label={`${t('temporary_works.load_gate')}: ${t(gate.load_gate_open ? 'temporary_works.gate_open' : 'temporary_works.gate_shut')}`}
            />
            <Indicator
              testId='strike-gate'
              ok={gate.strike_gate_open}
              label={`${t('temporary_works.strike_gate')}: ${t(gate.strike_gate_open ? 'temporary_works.gate_open' : 'temporary_works.gate_shut')}`}
            />
          </span>
        ) : null}
      </button>
      {open ? (
        <div className='grid gap-3 border-t p-3' data-testid='item-details'>
          <dl className='grid grid-cols-2 gap-x-4 gap-y-1 text-sm md:grid-cols-4'>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.item.category')}
              </dt>
              <dd>{t(categoryKey(item.design_check_category))}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.required_load')}
              </dt>
              <dd>{item.required_load_on ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.required_strike')}
              </dt>
              <dd>{item.required_strike_on ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.design_due')}
              </dt>
              <dd>{item.design_due_on ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.item.designer')}
              </dt>
              <dd>{item.designer ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.item.checker')}
              </dt>
              <dd>{item.checker ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.item.coordinator_name')}
              </dt>
              <dd>{item.coordinator_name ?? '—'}</dd>
            </div>
            <div>
              <dt className='text-xs text-muted-foreground'>
                {t('temporary_works.item.location')}
              </dt>
              <dd>{item.location ?? '—'}</dd>
            </div>
          </dl>
          {item.scaffold_id ? (
            <a
              data-testid='scaffold-link'
              className='text-sm text-primary underline'
              href={`/scaffolds?id=${item.scaffold_id}`}
            >
              {t('temporary_works.linked_scaffold', { id: item.scaffold_id })}
            </a>
          ) : null}
          {warnings.length > 0 ? (
            <ul
              data-testid='item-warnings'
              className='list-disc rounded-md bg-amber-500/10 py-2 ps-6 pe-3 text-sm'
            >
              {warnings.map((w, i) => (
                <li key={`${w.rule}-${i}`}>{w.message}</li>
              ))}
            </ul>
          ) : null}
          <div>
            <h4 className='mb-1 text-sm font-medium'>
              {t('temporary_works.permits')}
            </h4>
            <PermitTable
              item={item}
              permits={permits}
              has={has}
              onPermit={actions.onPermit}
            />
          </div>
          {buttons.length > 0 ? (
            <div className='flex flex-wrap gap-2' data-testid='item-actions'>
              {buttons.map((a) => (
                <Button
                  key={a}
                  size='sm'
                  variant={a === 'delete' ? 'destructive' : 'outline'}
                  data-action={a}
                  onClick={() => actions.onItem(item, a)}
                >
                  {a === 'transition'
                    ? t('temporary_works.transition.button')
                    : a === 'add_permit'
                      ? t('temporary_works.permit.add')
                      : a === 'return'
                        ? t('temporary_works.permit.return')
                        : a === 'delete'
                          ? t('temporary_works.delete_item')
                          : t('temporary_works.edit')}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  )
}

/**
 * The register's items as expandable rows. A breaching item carries a tag and a tint. Gates, breaches and warnings
 * are the server's; this only displays them next to the item they belong to.
 */
export function ItemRows({
  items,
  permits,
  gates,
  breachIds,
  warnings,
  has,
  loading,
  filtered,
  actions,
}: {
  items: Item[]
  permits: Permit[]
  gates: Gate[]
  breachIds: Set<number>
  warnings: Warning[]
  has: (permission: string) => boolean
  loading?: boolean
  /** True when filters, not an empty register, left no rows. */
  filtered?: boolean
  actions: RowActions
}) {
  const { t } = useTranslation()
  if (loading)
    return (
      <div className='grid gap-2' data-testid='rows-loading'>
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className='h-12 w-full' />
        ))}
      </div>
    )
  if (items.length === 0)
    return (
      <p className='text-sm text-muted-foreground' data-testid='rows-empty'>
        {t(filtered ? 'temporary_works.no_results' : 'temporary_works.empty')}
      </p>
    )
  return (
    <ul className='grid gap-2'>
      {items.map((item) => (
        <ItemRow
          key={item.id}
          item={item}
          permits={permits.filter((p) => p.item_id === item.id)}
          gate={gates.find((g) => g.item_id === item.id)}
          breach={breachIds.has(item.id)}
          warnings={warnings.filter((w) => w.item_id === item.id)}
          has={has}
          actions={actions}
        />
      ))}
    </ul>
  )
}
