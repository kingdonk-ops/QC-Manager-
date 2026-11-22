import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  ACTION_STATUSES,
  BAND_STYLE,
  type Dashboard,
  band,
  useActions,
  useAddAction,
  useUpdateAction,
} from './api'

export function RiskBadge({
  score,
  riskBand,
}: {
  score?: number | null
  riskBand?: string | null
}) {
  if (!score) return <span className='text-muted-foreground'>—</span>
  const b = riskBand ?? band(score)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium tabular-nums',
        BAND_STYLE[b]
      )}
    >
      {score} · {b}
    </span>
  )
}

/** Two rows of 1-5 buttons, large enough for a thumb, with the resulting score. */
export function RiskPicker({
  severity,
  likelihood,
  onChange,
  disabled,
}: {
  severity: number | null
  likelihood: number | null
  onChange: (v: { severity: number; likelihood: number }) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const row = (
    label: string,
    value: number | null,
    set: (n: number) => void
  ) => (
    <div className='grid gap-1'>
      <Label>{label}</Label>
      <div
        className='grid grid-cols-5 gap-1'
        role='radiogroup'
        aria-label={label}
      >
        {[1, 2, 3, 4, 5].map((n) => (
          <Button
            key={n}
            type='button'
            role='radio'
            aria-checked={value === n}
            variant={value === n ? 'default' : 'outline'}
            className='h-10'
            disabled={disabled}
            onClick={() => set(n)}
          >
            {n}
          </Button>
        ))}
      </div>
    </div>
  )
  return (
    <div className='grid gap-2'>
      {row(t('safety.severity'), severity, (n) =>
        onChange({ severity: n, likelihood: likelihood ?? 1 })
      )}
      {row(t('safety.likelihood'), likelihood, (n) =>
        onChange({ severity: severity ?? 1, likelihood: n })
      )}
      {severity && likelihood ? (
        <p className='text-sm'>
          {t('safety.risk_score')}: <RiskBadge score={severity * likelihood} />
        </p>
      ) : null}
    </div>
  )
}

/** The 5×5 heat map: severity down, likelihood across, cell colour by band. */
export function RiskMatrix({
  cells,
  show,
}: {
  cells: Dashboard['risk_matrix']
  show: 'incidents' | 'observations'
}) {
  const { t } = useTranslation()
  const at = (s: number, l: number) =>
    cells.find((c) => c.severity === s && c.likelihood === l)
  return (
    <div className='grid gap-1'>
      <table
        className='w-full table-fixed border-separate border-spacing-1 text-center text-sm'
        aria-label={t('safety.risk_matrix')}
      >
        <thead>
          <tr>
            <th className='w-20 text-xs font-normal text-muted-foreground'>
              {t('safety.sev_lik')}
            </th>
            {[1, 2, 3, 4, 5].map((l) => (
              <th key={l} className='text-xs font-medium'>
                {l}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[5, 4, 3, 2, 1].map((s) => (
            <tr key={s}>
              <th className='text-xs font-medium'>{s}</th>
              {[1, 2, 3, 4, 5].map((l) => {
                const cell = at(s, l)
                const count = cell ? cell[show] : 0
                return (
                  <td
                    key={l}
                    title={`${s} × ${l} = ${s * l} (${band(s * l)})`}
                    className={cn(
                      'h-11 rounded font-semibold tabular-nums',
                      BAND_STYLE[band(s * l)],
                      !count && 'font-normal opacity-60'
                    )}
                  >
                    {count || ''}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className='text-xs text-muted-foreground'>{t('safety.matrix_hint')}</p>
    </div>
  )
}

export function ActionList({
  projectId,
  parentType,
  parentId,
}: {
  projectId: number
  parentType: 'incident' | 'observation'
  parentId: number
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'safety.update')
  const { data: actions = [] } = useActions(projectId, parentType, parentId)
  const add = useAddAction()
  const update = useUpdateAction()
  const blank = { description: '', assignee_id: null as number | null, due: '' }
  const [draft, setDraft] = useState(blank)

  return (
    <div className='grid gap-3'>
      {actions.length === 0 ? (
        <p className='text-sm text-muted-foreground'>
          {t('safety.no_actions')}
        </p>
      ) : null}
      {actions.map((a) => (
        <div key={a.id} className='grid gap-2 rounded-md border p-3 text-sm'>
          <p>{a.description}</p>
          <div className='flex flex-wrap items-center gap-3 text-xs text-muted-foreground'>
            <span>
              {t('safety.assignee')}: {a.assignee_name ?? '—'}
            </span>
            <span className={cn(a.overdue && 'font-medium text-red-600')}>
              {t('safety.due')}: {a.due_date ?? '—'}
            </span>
            {a.verified_at ? (
              <span className='text-green-700 dark:text-green-400'>
                {t('safety.verified_by', {
                  name: a.verified_by_name ?? '',
                  date: a.verified_at.slice(0, 10),
                })}
              </span>
            ) : null}
            <StatusBadge status={a.status} />
          </div>
          {editable ? (
            <NativeSelect
              className='h-8 w-40'
              aria-label={t('safety.action_status')}
              values={ACTION_STATUSES}
              value={a.status}
              onChange={(e) =>
                update.mutate({ id: a.id, status: e.target.value })
              }
            />
          ) : null}
        </div>
      ))}
      {editable ? (
        <form
          className='grid gap-2 rounded-md border border-dashed p-3'
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(
              {
                parent_type: parentType,
                parent_id: parentId,
                description: draft.description,
                assignee_id: draft.assignee_id,
                due_date: draft.due || null,
              },
              { onSuccess: () => setDraft(blank) }
            )
          }}
        >
          <Input
            required
            placeholder={t('safety.action_description')}
            aria-label={t('safety.action_description')}
            value={draft.description}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <div className='grid gap-2 sm:grid-cols-2'>
            <UserSelect
              value={draft.assignee_id}
              onChange={(id) => setDraft({ ...draft, assignee_id: id })}
              placeholder={t('safety.assignee')}
            />
            <Input
              type='date'
              aria-label={t('safety.due')}
              value={draft.due}
              onChange={(e) => setDraft({ ...draft, due: e.target.value })}
            />
          </div>
          <Button
            size='sm'
            type='submit'
            className='w-fit'
            disabled={add.isPending}
          >
            <Plus /> {t('safety.add_action')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}
