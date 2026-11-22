import { lazy } from 'react'
import { Layers } from 'lucide-react'
import type { ModuleManifest } from '../_types'

const prefixed = (prefix: string, entries: Record<string, string>) =>
  Object.fromEntries(
    Object.entries(entries).map(([k, v]) => [`${prefix}${k}`, v])
  )

export const manifest: ModuleManifest = {
  id: 'materials',
  name: 'Materials & Traceability',
  version: '0.1.0',
  depends: ['projects'],
  routes: [
    {
      path: '/materials',
      component: lazy(() => import('./materials-page')),
      permission: 'materials.read',
      accountTypes: ['staff'],
    },
  ],
  navItems: [
    {
      labelKey: 'nav.materials',
      to: '/materials',
      icon: Layers,
      group: 'procurement',
      permission: 'materials.read',
      accountTypes: ['staff'],
    },
  ],
  messages: {
    en: {
      'nav.materials': 'Materials & Traceability',
      ...prefixed('materials.', {
        title: 'Materials & traceability',
        description:
          'Receipts, heats and mill certificates, quarantine, issue to work and heat traceability.',
        no_project: 'Choose a project in the top bar.',
        'tab.heats': 'Heats',
        'tab.receipts': 'Receipts',
        'tab.trace': 'Traceability',
        'tab.holds': 'Holds & warnings',
        heat: 'Heat',
        heats: 'Heats',
        grade: 'Grade',
        form: 'Form',
        description_field: 'Description',
        received: 'Received',
        expected: 'Expected delivery',
        supplied_by: 'Supplied by',
        company: 'Us',
        client: 'Client (free issue)',
        planned_for: 'Planned for (work anchor)',
        find_node: 'Search the asset tree',
        certificate: 'Certificate',
        status: 'Status',
        search: 'Search heats',
        new_heat: 'New heat',
        save: 'Save',
        where_used: 'Where used',
        not_issued: 'Not issued to work yet.',
        receive_today: 'Received today',
        certificates: 'Mill certificates',
        cert_number: 'Certificate number',
        add_cert: 'Add',
        cert_help:
          'Attach the certificate PDF under Files; QA verifies it before welds on this heat can be accepted.',
        verify: 'Verify',
        reject: 'Reject',
        holds: 'Holds',
        release: 'Release',
        reason: 'Reason',
        quarantine: 'Quarantine',
        issue: 'Issue to work',
        issued: 'Material issued',
        supplier: 'Supplier',
        delivery_note: 'Delivery note',
        receive: 'Receive material',
        no_certificate: 'No certificate',
        no_trace: 'No material issued here.',
        trace_help:
          'Pick a node to see the heats, certificates and PMI of everything issued to it and below.',
        open_holds: 'Open holds',
        no_holds: 'Nothing on hold.',
        warnings: 'Client-supplied material late for its work',
        no_warnings: 'No warnings.',
        'st.expected': 'Expected',
        'st.available': 'Available',
        'st.quarantined': 'Quarantined',
        'st.rejected': 'Rejected',
      }),
    },
  },
}
