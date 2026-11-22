import { lazy } from 'react'
import { Scale } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'cvr',
  name: 'Cost-Value Reconciliation',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/cvr',
      component: lazy(() => import('./cvr-page')),
      permission: 'cvr.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.cvr',
      to: '/cvr',
      icon: Scale,
      group: 'commercial',
      permission: 'cvr.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.group.commercial': 'Commercial',
      'nav.cvr': 'Cost-Value Reconciliation',
      'cvr.title': 'Cost-Value Reconciliation',
      'cvr.description':
        'Cost against value earned per cost head, with the cashflow forecast.',
      'cvr.no_project': 'Choose a project in the top bar.',
      'cvr.code': 'Code',
      'cvr.head': 'Cost head',
      'cvr.budget': 'Budget',
      'cvr.cost': 'Cost to date',
      'cvr.value': 'Value to date',
      'cvr.margin': 'Margin',
      'cvr.forecast_cost': 'Forecast cost',
      'cvr.forecast_value': 'Forecast value',
      'cvr.forecast_margin': 'Forecast margin',
      'cvr.add': 'Add cost head',
      'cvr.cashflow': 'Cashflow forecast',
      'cvr.planned_cost': 'Planned cost',
      'cvr.actual_cost': 'Actual cost',
      'cvr.planned_value': 'Cumulative planned value',
      'cvr.actual_value': 'Cumulative actual value',
    },
  },
}
