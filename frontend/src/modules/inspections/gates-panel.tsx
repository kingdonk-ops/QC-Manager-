import { useState } from 'react'
import { Flag, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CreateGateDialog, ReleaseDialog, WaiveDialog } from './gate-dialogs'
import {
  type Gate,
  type GateProceed,
  useCanProceed,
  useGateAction,
  useGates,
} from './gates-api'
import { type GateActionSet, gateActions, statusTone } from './gate-rules'

/** The server's answer to "may work go ahead here?", shown as it came: blocking gates and earlier unreleased holds. */
export function ProceedBanner({ answer }: { answer: GateProceed }) {
  const { t } = useTranslation()
  const holds = answer.hold_points ?? []
  return (
    <div
      data-testid='proceed-banner'
      data-allowed={answer.can_proceed ? 'true' : 'false'}
      className={`grid gap-1 rounded-md border p-3 text-sm ${
        answer.can_proceed
          ? 'border-green-600 text-green-700'
          : 'border-red-600 text-red-700'
      }`}
    >
      <p className='font-medium'>
        {answer.can_proceed
          ? t('inspections.gates.proceed_yes')
          : t('inspections.gates.proceed_no')}
      </p>
      {answer.gate_numbers.length ? (
        <p>
          {t('inspections.gates.blocking_gates')}:{' '}
          <span className='font-mono'>{answer.gate_numbers.join(', ')}</span>
        </p>
      ) : null}
      {holds.length ? (
        <p>
          {t('inspections.gates.earlier_holds')}:{' '}
          {holds.map((h) => `${h.code} ${h.title}`).join('; ')}
        </p>
      ) : null}
    </div>
  )
}

export type GateAct = 'release' | 'waive' | 'void' | 'delete'

/** The buttons a gate offers: waive never on a hold, nothing once decided. */
export function GateActions({
  actions,
  onAct,
}: {
  actions: GateActionSet
  onAct: (action: GateAct) => void
}) {
  const { t } = useTranslation()
  return (
    <div className='flex flex-wrap gap-1.5'>
      {actions.release ? (
        <Button size='sm' onClick={() => onAct('release')}>
          {t('inspections.gates.release')}
        </Button>
      ) : null}
      {actions.waive ? (
        <Button size='sm' variant='outline' onClick={() => onAct('waive')}>
          {t('inspections.gates.waive')}
        </Button>
      ) : null}
      {actions.void ? (
        <Button size='sm' variant='outline' onClick={() => onAct('void')}>
          {t('inspections.gates.void')}
        </Button>
      ) : null}
      {actions.delete ? (
        <Button size='sm' variant='ghost' onClick={() => onAct('delete')}>
          {t('inspections.gates.delete')}
        </Button>
      ) : null}
    </div>
  )
}

/** What decided a gate: who released it at which level and its digest, or who waived it and why. */
export function GateDecision({ gate }: { gate: Gate }) {
  const { t } = useTranslation()
  if (gate.status === 'released')
    return (
      <p className='text-xs text-muted-foreground'>
        {t('inspections.gates.released_by', {
          id: gate.released_by_id,
          level: gate.released_level
            ? t(`inspections.gates.authority.${gate.released_level}`)
            : '',
        })}
        {gate.release_digest
          ? ` · ${t('inspections.gates.digest')} ${gate.release_digest.slice(0, 12)}…`
          : ''}
      </p>
    )
  if (gate.status === 'waived')
    return (
      <p className='text-xs text-muted-foreground'>
        {t('inspections.gates.waived_by', {
          id: gate.waived_by_id,
          reason: gate.waiver_reason,
        })}
      </p>
    )
  return null
}

/** The actions of one gate for the current user, with the dialogs for release and waive. */
export function GateControls({ gate }: { gate: Gate }) {
  const { t } = useTranslation()
  const session = useSession()
  const act = useGateAction()
  const [dialog, setDialog] = useState<'release' | 'waive' | null>(null)
  const actions = gateActions(gate, {
    approve: can(session, 'inspections.approve'),
    delete: can(session, 'inspections.delete'),
  })
  const onAct = (a: GateAct) => {
    if (a === 'release' || a === 'waive') return setDialog(a)
    act.mutate(
      { id: gate.id, action: a },
      {
        onSuccess: () =>
          toast.success(
            t(
              a === 'void'
                ? 'inspections.gates.voided'
                : 'inspections.gates.deleted'
            )
          ),
      }
    )
  }
  return (
    <>
      <GateActions actions={actions} onAct={onAct} />
      {dialog === 'release' ? (
        <ReleaseDialog gate={gate} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === 'waive' ? (
        <WaiveDialog gate={gate} onClose={() => setDialog(null)} />
      ) : null}
    </>
  )
}

function GateCard({ gate }: { gate: Gate }) {
  const { t } = useTranslation()
  return (
    <li className='grid gap-1 rounded-md border p-3 text-sm'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='font-mono text-xs'>{gate.number}</span>
        <span className='font-medium'>{gate.title}</span>
        <span className='text-xs text-muted-foreground'>
          {t(`inspections.gates.kind.${gate.kind}`)} ·{' '}
          {gate.blocks_progress
            ? t('inspections.gates.blocks_yes')
            : t('inspections.gates.blocks_no')}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs ${statusTone(gate.status)}`}
        >
          {t(`inspections.gates.status.${gate.status}`)}
        </span>
        <span className='ms-auto'>
          <GateControls gate={gate} />
        </span>
      </div>
      <GateDecision gate={gate} />
    </li>
  )
}

/** Gates attached to one inspection record, the can-proceed banner, and create. */
export function GatesPanel({
  projectId,
  inspectionId,
}: {
  projectId: number
  inspectionId: number
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [creating, setCreating] = useState(false)
  const { data: gates = [] } = useGates(projectId, {
    inspection_id: inspectionId,
  })
  const { data: answer } = useCanProceed(projectId, 'inspection', inspectionId)
  return (
    <Card>
      <CardHeader className='flex flex-row items-center gap-2'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <Flag className='size-4' /> {t('inspections.gates.panel')}
        </CardTitle>
        {can(session, 'inspections.update') ? (
          <Button
            size='sm'
            variant='outline'
            className='ms-auto'
            onClick={() => setCreating(true)}
          >
            <Plus /> {t('inspections.gates.new')}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className='grid gap-3'>
        {answer ? <ProceedBanner answer={answer} /> : null}
        {gates.length ? (
          <ul className='grid gap-2'>
            {gates.map((g) => (
              <GateCard key={g.id} gate={g} />
            ))}
          </ul>
        ) : (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.gates.empty')}
          </p>
        )}
      </CardContent>
      {creating ? (
        <CreateGateDialog
          projectId={projectId}
          attachment={{ kind: 'inspection', id: inspectionId }}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </Card>
  )
}
