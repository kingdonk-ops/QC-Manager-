/** English strings for distinct signers on ITP lines: the signers panel, the additional-signatory dialog and the editor field. */
export const signatoryMessages: Record<string, string> = {
  'inspections.role.additional_signatory': 'Additional signatory',
  'inspections.signers.title': 'Signers',
  'inspections.signers.count': '{{collected}} of {{required}} signers',
  'inspections.signers.met': 'Requirement met',
  'inspections.signers.not_met': 'Requirement not yet met',
  'inspections.signers.none': 'No one has signed yet.',
  'inspections.signers.unnamed': 'Unnamed signer',
  'inspections.signers.add': 'Sign as additional signatory',
  'inspections.signers.add_title': 'Sign as additional signatory',
  'inspections.signers.add_help':
    'Adds your signature over the current content of this line. A person counts once, however many roles they sign in.',
  'inspections.signers.add_intent':
    'I, {{name}}, sign inspection {{code}} as an additional signatory and confirm its current content.',
  'inspections.signers.add_submit': 'Sign',
  'inspections.signers.added': 'Signature added',
  'inspections.signers.line_count': 'Signers {{collected}}/{{required}}',
  'inspections.signers.required_field':
    'Signatures required (different people)',
  'inspections.signers.required_help':
    'Whole number from {{min}} to {{max}}. Empty means {{min}}. Each person counts once.',
  'inspections.signers.required_range':
    'Enter a whole number from 1 to 10, or leave it empty for 1.',
}
