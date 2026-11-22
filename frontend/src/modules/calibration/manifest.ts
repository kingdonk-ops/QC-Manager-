import { lazy } from 'react'
import { Gauge } from 'lucide-react'
import type { ModuleManifest } from '../_types'

const TYPES: Record<string, string> = {
  pressure_gauge: 'Pressure gauge',
  dft_meter: 'DFT meter',
  thermometer: 'Thermometer',
  torque_wrench: 'Torque wrench',
  tensioning_tool: 'Tensioning tool',
  ut_thickness_gauge: 'UT thickness gauge',
  pmi_analyser: 'PMI analyser',
  surface_profile_gauge: 'Surface profile gauge',
  holiday_detector: 'Holiday detector',
  hygrometer: 'Hygrometer',
  welding_gauge: 'Welding gauge',
  multimeter: 'Multimeter',
  other: 'Other',
}
const STATUSES: Record<string, string> = {
  in_service: 'In service',
  due: 'Due',
  overdue: 'Overdue',
  sent_for_calibration: 'Sent for calibration',
  quarantined: 'Quarantined',
  out_of_service: 'Out of service',
}
const MOVES: Record<string, string> = {
  in_service: 'Return to service',
  sent_for_calibration: 'Send for calibration',
  quarantined: 'Quarantine',
  out_of_service: 'Take out of service',
}

export const manifest: ModuleManifest = {
  id: 'calibration',
  name: 'Calibration',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/calibration',
      component: lazy(() => import('./calibration-page')),
      permission: 'calibration.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.calibration',
      to: '/calibration',
      icon: Gauge,
      group: 'quality_safety',
      permission: 'calibration.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.calibration': 'Calibration',
      'calibration.title': 'Calibration register',
      'calibration.description':
        'Gauges, meters and tools with their certificates. Readings taken with overdue or quarantined equipment are refused.',
      'calibration.no_project': 'Choose a project in the top bar.',
      'calibration.total': 'Equipment',
      'calibration.new': 'New equipment',
      'calibration.export': 'Export',
      'calibration.code': 'No.',
      'calibration.code_auto': 'Numbered automatically',
      'calibration.name': 'Equipment',
      'calibration.type': 'Type',
      'calibration.serial': 'Serial',
      'calibration.manufacturer': 'Manufacturer',
      'calibration.model': 'Model',
      'calibration.location': 'Location',
      'calibration.custodian': 'Custodian',
      'calibration.interval': 'Interval (days)',
      'calibration.reminder': 'Remind (days before due)',
      'calibration.requires': 'Needs calibration',
      'calibration.notes': 'Notes',
      'calibration.last_calibrated': 'Last calibrated',
      'calibration.due': 'Due',
      'calibration.days': 'Days',
      'calibration.status': 'Status',
      'calibration.save': 'Save',
      'calibration.saved': 'Equipment saved',
      'calibration.certificates': 'Certificates',
      'calibration.history': 'History',
      'calibration.cert_number': 'Certificate',
      'calibration.calibrated_on': 'Calibrated',
      'calibration.expires_on': 'Expires',
      'calibration.facility': 'Laboratory',
      'calibration.record_cert': 'Record',
      'calibration.cert_saved': 'Calibration recorded',
      'calibration.cert_help':
        'Expiry is the calibration date plus the interval. Attach the certificate PDF under Files.',
      'calibration.superseded': 'Superseded',
      'calibration.no_certs': 'No calibration on record.',
      ...Object.fromEntries(
        Object.entries(TYPES).map(([k, v]) => [`calibration.type.${k}`, v])
      ),
      ...Object.fromEntries(
        Object.entries(STATUSES).map(([k, v]) => [`calibration.st.${k}`, v])
      ),
      ...Object.fromEntries(
        Object.entries(MOVES).map(([k, v]) => [`calibration.to.${k}`, v])
      ),
    },
  },
}
