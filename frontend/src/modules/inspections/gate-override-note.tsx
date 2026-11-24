import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Gate, GateProceed } from './gates-api'

/**
 * The annotation of a pending gate that a dossier issue override covers. The gate is still pending: the note sits
 * beside the status and never replaces it.
 */
export function GateOverrideNote({ gate }: { gate: Gate }) {
  const { t } = useTranslation()
  if (gate.status !== 'pending' || !gate.override_ref) return null
  return (
    <p
      data-testid='gate-override-note'
      className='flex items-center gap-1 text-xs text-violet-700 dark:text-violet-400'
    >
      <ShieldAlert className='size-3' />
      {t('inspections.gates.overridden_note')}
      <span className='font-mono'>{gate.override_ref}</span>
    </p>
  )
}

/** Gates a dossier override covers, listed apart from the plain blocking gates; they are still pending. */
export function OverriddenGates({ answer }: { answer: GateProceed }) {
  const { t } = useTranslation()
  const numbers = answer.overridden_gate_numbers ?? []
  if (!numbers.length) return null
  return (
    <p data-testid='overridden-gates'>
      {t('inspections.gates.overridden_gates')}:{' '}
      <span className='font-mono'>{numbers.join(', ')}</span>
    </p>
  )
}
