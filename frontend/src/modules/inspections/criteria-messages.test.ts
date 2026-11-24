import { describe, expect, it } from 'vitest'
import { criteriaMessages } from './criteria-messages'

describe('follow-up select wording', () => {
  it('keeps the option for a criterion-linked failure short enough for the select', () => {
    const label = criteriaMessages['inspections.criterion.auto_report_option']
    expect(label).toBeTruthy()
    // The select is 12rem wide: about 20 characters at the dialog's text size.
    expect(label.length).toBeLessThanOrEqual(20)
  })
})
