import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { TemplateItem } from './api'
import type { Criterion } from './criteria-api'
import {
  applyCriterion,
  criterionLabel,
  criterionName,
  presentItem,
} from './criterion-label'
import { CriterionSelect, ItemLimits } from './criterion-picker'

const range = {
  id: 7,
  project_id: 1,
  code: 'GAP-1',
  title: 'Joint gap',
  rule_type: 'range',
  nominal: null,
  lower_limit: '50',
  upper_limit: '55',
  unit: 'mm',
  active: true,
} as unknown as Criterion

const blank: TemplateItem = {
  text: 'Gap',
  response_type: 'numeric',
  unit: null,
  min_value: null,
  max_value: null,
  requires_photo_on_fail: false,
  guidance: null,
}

describe('applyCriterion', () => {
  it('copies limits and unit and keeps the reference', () => {
    expect(applyCriterion(blank, range)).toMatchObject({
      criterion_id: 7,
      min_value: 50,
      max_value: 55,
      unit: 'mm',
    })
  })

  it('clearing drops the reference only', () => {
    const picked = applyCriterion(blank, range)
    expect(applyCriterion(picked, null)).toMatchObject({
      criterion_id: null,
      min_value: 50,
    })
  })
})

const freeText = {
  ...range,
  id: 8,
  code: 'NOTE-1',
  rule_type: 'free_text',
  lower_limit: null,
  upper_limit: null,
} as unknown as Criterion

describe('items saved with a criterion through the template API', () => {
  const saved: TemplateItem = {
    ...blank,
    response_type: 'pass_fail',
    criterion_id: 7,
  }

  it('present as numeric readings with the criterion limits and unit', () => {
    expect(presentItem(saved, [range])).toMatchObject({
      response_type: 'numeric',
      criterion_id: 7,
      min_value: 50,
      max_value: 55,
      unit: 'mm',
    })
  })

  it('stay as they are when the criterion is not numeric, not loaded, or absent', () => {
    const textual = { ...saved, criterion_id: 8 }
    expect(presentItem(textual, [freeText])).toBe(textual)
    expect(presentItem(saved, [])).toBe(saved)
    const plain = { ...blank, response_type: 'pass_fail' as const }
    expect(presentItem(plain, [range])).toBe(plain)
  })

  it('choosing a numeric criterion on a pass or fail item makes it numeric', () => {
    const plain = { ...blank, response_type: 'pass_fail' as const }
    expect(applyCriterion(plain, range).response_type).toBe('numeric')
    expect(applyCriterion(plain, freeText).response_type).toBe('pass_fail')
  })

  it('show the linked criterion in the picker and let it be cleared', async () => {
    function Linked() {
      const [item, setItem] = useState<TemplateItem>(
        presentItem(saved, [range])
      )
      return (
        <div>
          <CriterionSelect
            criteria={[range]}
            value={item.criterion_id}
            onChange={(c) => setItem(applyCriterion(item, c))}
          />
          <ItemLimits item={item} onChange={setItem} />
        </div>
      )
    }
    const screen = await render(<Linked />)
    await expect
      .element(screen.getByLabelText('inspections.criteria.picker'))
      .toHaveValue('7')
    await expect
      .element(screen.getByLabelText('inspections.max'))
      .toHaveValue(55)
    await screen.getByLabelText('inspections.criteria.picker').selectOptions('')
    await expect
      .element(screen.getByLabelText('inspections.max'))
      .not.toHaveAttribute('readonly')
  })
})

describe('criterionName', () => {
  it('names the code and title, falls back to the number, and is empty without one', () => {
    expect(criterionName([range], 7)).toBe('GAP-1 · Joint gap')
    expect(criterionName([], 7)).toBe('#7')
    expect(criterionName([range], null)).toBeNull()
  })
})

describe('criterionLabel', () => {
  it('names the code, title and tolerance', () => {
    expect(criterionLabel(range)).toBe('GAP-1 · Joint gap (≥ 50 · ≤ 55 mm)')
  })
})

function Harness() {
  const [item, setItem] = useState<TemplateItem>(blank)
  return (
    <div>
      <CriterionSelect
        criteria={[range]}
        value={item.criterion_id}
        onChange={(c) => setItem(applyCriterion(item, c))}
      />
      <ItemLimits item={item} onChange={setItem} />
    </div>
  )
}

describe('picker with the limit fields', () => {
  it('fills and locks the limits, then unlocks them when cleared', async () => {
    const screen = await render(<Harness />)
    await screen
      .getByLabelText('inspections.criteria.picker')
      .selectOptions('7')
    await expect
      .element(screen.getByLabelText('inspections.min'))
      .toHaveValue(50)
    await expect
      .element(screen.getByLabelText('inspections.max'))
      .toHaveValue(55)
    await expect
      .element(screen.getByLabelText('inspections.unit'))
      .toHaveValue('mm')
    await expect
      .element(screen.getByLabelText('inspections.min'))
      .toHaveAttribute('readonly')

    await screen.getByLabelText('inspections.criteria.picker').selectOptions('')
    await expect
      .element(screen.getByLabelText('inspections.min'))
      .not.toHaveAttribute('readonly')
  })
})
