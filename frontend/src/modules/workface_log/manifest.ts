import { lazy } from 'react'
import { NotebookPen } from 'lucide-react'
import type { ModuleManifest } from '../_types'

export const manifest: ModuleManifest = {
  id: 'workface_log',
  name: 'Daily Workface Log',
  version: '0.1.0',
  depends: ['projects', 'planner'],
  routes: [
    {
      path: '/workface-log',
      component: lazy(() => import('./log-page')),
      permission: 'workface_log.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.workface_log',
      to: '/workface-log',
      icon: NotebookPen,
      group: 'project_management',
      order: 30,
      permission: 'workface_log.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.workface_log': 'Daily Log',
      'workface_log.title': 'Daily Workface Log',
      'workface_log.description':
        'Each crew’s day: hours by work anchor or delay code, quantities installed, plant, weather and sign-off.',
      'workface_log.no_project': 'Choose a project in the top bar.',
      'workface_log.back': 'Back to the day',
      'workface_log.date': 'Date',
      'workface_log.crew': 'Crew',
      'workface_log.pick_crew': 'Pick a crew',
      'workface_log.shift': 'Shift',
      'workface_log.start': 'Start log',
      'workface_log.total': 'Total hours',
      'workface_log.productive': 'Productive',
      'workface_log.delays': 'Delays',
      'workface_log.overhead': 'Overhead',
      'workface_log.headcount': 'Headcount',
      'workface_log.planned_anchors': 'planned work anchors',
      'workface_log.delayed': 'delayed',
      'workface_log.open': 'Open',
      'workface_log.nothing': 'No crew planned or logged this day.',
      'workface_log.work_anchor': 'Work anchor',
      'workface_log.hours': 'Hours',
      'workface_log.installed': 'Installed',
    },
  },
}
