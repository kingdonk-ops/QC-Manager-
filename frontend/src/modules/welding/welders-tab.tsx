import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  stateTone,
  useAct,
  useMatrix,
  useWelders,
  useWps,
  weldingApi,
} from './api'

const today = () => new Date().toISOString().slice(0, 10)

/** Welders × processes, coloured by the best qualification's state today. */
function QualificationMatrix({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data } = useMatrix(projectId)
  if (!data) return null
  return (
    <div className='overflow-x-auto'>
      <table className='text-sm'>
        <thead>
          <tr className='text-left text-xs text-muted-foreground'>
            <th className='pe-4'>{t('welding.welder')}</th>
            {data.processes.map((p) => (
              <th key={p} className='px-2'>
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.welder_id} className='border-t'>
              <td className='py-1 pe-4'>
                <strong>{r.stamp}</strong> {r.name}{' '}
                {r.status !== 'active' ? (
                  <StatusBadge status={r.status} />
                ) : null}
              </td>
              {data.processes.map((p) => {
                const cell = r.cells[p]
                return (
                  <td key={p} className='px-1'>
                    <span
                      title={
                        cell
                          ? `${t('welding.expires')}: ${cell.expires_on ?? '–'} · ${t('welding.continuity')}: ${cell.continuity_until ?? '–'}`
                          : undefined
                      }
                      className={cn(
                        'block rounded px-2 py-0.5 text-center text-xs',
                        stateTone(cell?.state)
                      )}
                    >
                      {cell ? t(`welding.state.${cell.state}`) : '—'}
                    </span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function WeldersTab({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: welders = [] } = useWelders(projectId)
  const { data: wps = [] } = useWps(projectId)
  const [welder, setWelder] = useState({ stamp: '', name: '' })
  const [qual, setQual] = useState({
    welder: '',
    process: 'GTAW',
    qualified_on: today(),
    expires_on: '',
  })
  const addWelder = useAct(() =>
    weldingApi.createWelder({ project_id: projectId, ...welder })
  )
  const addQual = useAct(() =>
    weldingApi.addQualification(Number(qual.welder), {
      process: qual.process,
      qualified_on: qual.qualified_on,
      expires_on: qual.expires_on || null,
      positions: [],
      material_groups: [],
    })
  )
  const [wpsForm, setWpsForm] = useState({ code: '', process: 'GTAW' })
  const addWps = useAct(() =>
    weldingApi.createWps({
      project_id: projectId,
      code: wpsForm.code,
      process: wpsForm.process,
      revision: '0',
      positions: [],
      joint_types: [],
      pwht: false,
    })
  )
  const approve = useAct((id: number) => weldingApi.wpsStatus(id, 'approved'))

  return (
    <div className='grid gap-4'>
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>{t('welding.matrix')}</CardTitle>
        </CardHeader>
        <CardContent>
          <QualificationMatrix projectId={projectId} />
        </CardContent>
      </Card>
      <div className='grid gap-4 lg:grid-cols-3'>
        {can(session, 'welding.create') ? (
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('welding.new_welder')}
              </CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2'>
              <Input
                placeholder={t('welding.stamp')}
                value={welder.stamp}
                onChange={(e) =>
                  setWelder({ ...welder, stamp: e.target.value })
                }
              />
              <Input
                placeholder={t('welding.name')}
                value={welder.name}
                onChange={(e) => setWelder({ ...welder, name: e.target.value })}
              />
              <Button
                size='sm'
                disabled={!welder.stamp || !welder.name}
                onClick={() =>
                  addWelder.mutate(undefined, {
                    onSuccess: () => setWelder({ stamp: '', name: '' }),
                  })
                }
              >
                {t('welding.add')}
              </Button>
            </CardContent>
          </Card>
        ) : null}
        {can(session, 'welding.approve') ? (
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('welding.new_qualification')}
              </CardTitle>
            </CardHeader>
            <CardContent className='grid gap-2'>
              <NativeSelect
                placeholder={t('welding.welder')}
                options={welders.map((w) => ({
                  value: String(w.id),
                  label: `${w.stamp} ${w.name}`,
                }))}
                value={qual.welder}
                onChange={(e) => setQual({ ...qual, welder: e.target.value })}
              />
              <Input
                placeholder={t('welding.process')}
                value={qual.process}
                onChange={(e) => setQual({ ...qual, process: e.target.value })}
              />
              <div className='grid grid-cols-2 gap-2'>
                <Input
                  type='date'
                  value={qual.qualified_on}
                  onChange={(e) =>
                    setQual({ ...qual, qualified_on: e.target.value })
                  }
                />
                <Input
                  type='date'
                  title={t('welding.expires')}
                  value={qual.expires_on}
                  onChange={(e) =>
                    setQual({ ...qual, expires_on: e.target.value })
                  }
                />
              </div>
              <Button
                size='sm'
                disabled={!qual.welder}
                onClick={() => addQual.mutate(undefined)}
              >
                {t('welding.add')}
              </Button>
            </CardContent>
          </Card>
        ) : null}
        <Card>
          <CardHeader>
            <CardTitle className='text-base'>
              {t('welding.wps_register')}
            </CardTitle>
          </CardHeader>
          <CardContent className='grid gap-2 text-sm'>
            {wps.map((w) => (
              <div key={w.id} className='flex items-center gap-2'>
                <span className='font-mono'>
                  {w.code} rev {w.revision}
                </span>
                <span className='text-muted-foreground'>{w.process}</span>
                <StatusBadge status={w.status} className='ms-auto' />
                {w.status === 'draft' && can(session, 'welding.approve') ? (
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => approve.mutate(w.id)}
                  >
                    {t('welding.approve')}
                  </Button>
                ) : null}
              </div>
            ))}
            {can(session, 'welding.create') ? (
              <div className='flex gap-2 border-t pt-2'>
                <Input
                  placeholder='WPS'
                  value={wpsForm.code}
                  onChange={(e) =>
                    setWpsForm({ ...wpsForm, code: e.target.value })
                  }
                />
                <Input
                  placeholder={t('welding.process')}
                  value={wpsForm.process}
                  onChange={(e) =>
                    setWpsForm({ ...wpsForm, process: e.target.value })
                  }
                />
                <Button
                  size='sm'
                  disabled={!wpsForm.code}
                  onClick={() => addWps.mutate(undefined)}
                >
                  {t('welding.add')}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
