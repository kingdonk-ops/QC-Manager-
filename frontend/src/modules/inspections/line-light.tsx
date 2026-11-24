import { useTranslation } from 'react-i18next'
import { lightTone } from './gate-rules'
import type { ItpLine } from './quality-api'

/** The traffic light of one ITP line from the server's gate state: review, passed, released, blocked or pending. */
export function LineLight({ line }: { line: ItpLine }) {
  const { t } = useTranslation()
  const state = line.gate_state ?? 'review'
  const label = t(`inspections.gates.light.${state}`)
  const reason = line.gate_reason ? `${label}: ${line.gate_reason}` : label
  return (
    <span
      className='inline-flex items-center gap-1 text-xs'
      title={reason}
      data-testid='line-light'
      data-state={state}
      data-satisfied={line.gate_satisfied ? 'true' : 'false'}
    >
      <span
        role='img'
        aria-label={reason}
        className={`inline-block size-2.5 rounded-full ${lightTone(state)}`}
      />
      {label}
    </span>
  )
}
