export type OutcomeState = {
  conditional: boolean
  measured: string
  /** null until the person picks one: the default then follows the result. */
  severity: string | null
}

export const NO_OUTCOME: OutcomeState = {
  conditional: false,
  measured: '',
  severity: null,
}

export const SEVERITIES = ['minor', 'major', 'critical'] as const

/** Fail defaults to major and a conditional acceptance to minor. */
export function effectiveSeverity(
  result: 'pass' | 'fail',
  state: OutcomeState
): string {
  return state.severity ?? (result === 'fail' ? 'major' : 'minor')
}

/** The outcome fields of a complete or submit request. Conditional only goes with a pass. */
export function outcomeBody(result: 'pass' | 'fail', state: OutcomeState) {
  const conditional = result === 'pass' && state.conditional
  const withSeverity = result === 'fail' || conditional
  return {
    conditional,
    measured_value: state.measured.trim() || null,
    report_severity: withSeverity ? effectiveSeverity(result, state) : null,
  }
}
