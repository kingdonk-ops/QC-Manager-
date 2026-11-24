/** English strings for the dossier issue override: the action, its dialog, the hold counts and the override history. */
export const overrideMessages: Record<string, string> = {
  'mdr.override.action': 'Override blockers',
  'mdr.override.title': 'Override issue blockers',
  'mdr.override.help':
    'Lets this dossier be issued past the blockers below. The holds stay pending and are annotated, and a documentation report is raised and linked.',
  'mdr.override.blockers': 'Blockers this override will cover',
  'mdr.override.no_blockers': 'No failing blocking check is listed.',
  'mdr.override.cannot_title': 'This override cannot be recorded',
  'mdr.override.cannot_help':
    'These checks can never be overridden and still fail. Resolve them first, then override the rest.',
  'mdr.override.reason': 'Reason',
  'mdr.override.reason_required': 'A reason is required.',
  'mdr.override.severity': 'Documentation report severity',
  'mdr.override.severity.minor': 'Minor',
  'mdr.override.severity.major': 'Major',
  'mdr.override.severity.critical': 'Critical',
  'mdr.override.submit': 'Record override',
  'mdr.override.done_title': 'Override recorded',
  'mdr.override.done_reference': 'Override reference',
  'mdr.override.done_report': 'Documentation report raised',
  'mdr.override.done_no_report': 'No documentation report is linked.',
  'mdr.override.done_gates':
    'Holds covered (still pending)',
  'mdr.override.close': 'Close',
  'mdr.override.history': 'Overrides',
  'mdr.override.history_by': 'by {{name}}',
  'mdr.override.history_report': 'Report',
  'mdr.override.history_gates': 'Holds',
  'mdr.counts.title': 'Holds and reports',
  'mdr.counts.plain': 'Plain pending holds',
  'mdr.counts.overridden': 'Overridden-pending holds',
  'mdr.counts.reports': 'Open reports',
}
