import { useState } from 'react'
import { Dices } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useMonteCarlo } from './api'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className='rounded-md border p-2'>
      <p className='text-xs text-muted-foreground'>{label}</p>
      <p className='font-semibold tabular-nums'>{value}</p>
    </div>
  )
}

export function MonteCarloPanel({
  projectId,
  open,
  onClose,
}: {
  projectId: number
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const run = useMonteCarlo(projectId)
  const [iterations, setIterations] = useState('1000')
  const [distribution, setDistribution] = useState<'triangular' | 'pert'>(
    'triangular'
  )
  const [seed, setSeed] = useState('')
  const result = run.data

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className='w-full gap-0 overflow-y-auto sm:max-w-2xl'>
        <SheetHeader>
          <SheetTitle>{t('schedule.mc.title')}</SheetTitle>
          <SheetDescription>{t('schedule.mc.description')}</SheetDescription>
        </SheetHeader>
        <div className='flex flex-col gap-4 px-4 pb-6'>
          <form
            className='flex flex-wrap items-end gap-2'
            onSubmit={(e) => {
              e.preventDefault()
              run.mutate({
                iterations: Math.min(
                  20000,
                  Math.max(1, Number(iterations) || 1000)
                ),
                distribution,
                seed: seed === '' ? null : Number(seed),
              })
            }}
          >
            <div className='grid gap-1'>
              <Label htmlFor='mc-iterations'>
                {t('schedule.mc.iterations')}
              </Label>
              <Input
                id='mc-iterations'
                type='number'
                min={1}
                max={20000}
                className='h-8 w-28'
                value={iterations}
                onChange={(e) => setIterations(e.target.value)}
              />
            </div>
            <div className='grid gap-1'>
              <Label>{t('schedule.mc.distribution')}</Label>
              <Select
                value={distribution}
                onValueChange={(v) =>
                  setDistribution(v as 'triangular' | 'pert')
                }
              >
                <SelectTrigger size='sm' className='h-8 w-36'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='triangular'>Triangular</SelectItem>
                  <SelectItem value='pert'>PERT (beta)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='mc-seed'>{t('schedule.mc.seed')}</Label>
              <Input
                id='mc-seed'
                type='number'
                min={0}
                className='h-8 w-24'
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </div>
            <Button size='sm' type='submit' disabled={run.isPending}>
              <Dices />{' '}
              {run.isPending ? t('schedule.mc.running') : t('schedule.mc.run')}
            </Button>
          </form>

          {result ? (
            <>
              <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
                <Stat label='P50' value={result.p50} />
                <Stat label='P80' value={result.p80} />
                <Stat label='P90' value={result.p90} />
                <Stat
                  label={t('schedule.mc.on_time', { date: result.target_date })}
                  value={`${Math.round(result.probability_on_time * 100)}%`}
                />
              </div>
              <div className='h-64'>
                <ResponsiveContainer width='100%' height='100%'>
                  <ComposedChart
                    data={result.histogram.map((b) => ({
                      ...b,
                      cumulative: Math.round(b.cumulative * 100),
                    }))}
                  >
                    <CartesianGrid strokeDasharray='3 3' strokeOpacity={0.3} />
                    <XAxis dataKey='date' fontSize={10} />
                    <YAxis yAxisId='runs' fontSize={10} />
                    <YAxis
                      yAxisId='pct'
                      orientation='right'
                      domain={[0, 100]}
                      unit='%'
                      fontSize={10}
                    />
                    <Tooltip />
                    <Bar
                      yAxisId='runs'
                      dataKey='count'
                      name={t('schedule.mc.runs')}
                      fill='#2563eb'
                    />
                    <Line
                      yAxisId='pct'
                      dataKey='cumulative'
                      name={t('schedule.mc.cumulative')}
                      stroke='#f97316'
                      dot={false}
                    />
                    <ReferenceLine
                      yAxisId='runs'
                      x={result.planned_finish}
                      stroke='#16a34a'
                      label={{ value: t('schedule.mc.planned'), fontSize: 10 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <p className='text-xs text-muted-foreground'>
                {t('schedule.mc.summary', {
                  iterations: result.iterations,
                  planned: result.planned_finish,
                  earliest: result.earliest,
                  latest: result.latest,
                })}
              </p>
              <div>
                <h3 className='mb-2 text-sm font-semibold'>
                  {t('schedule.mc.criticality')}
                </h3>
                <ul className='space-y-1 text-sm'>
                  {result.criticality.slice(0, 15).map((c) => (
                    <li key={c.activity_id} className='flex items-center gap-2'>
                      <span className='w-14 font-mono text-xs text-muted-foreground'>
                        {c.wbs_code}
                      </span>
                      <span className='flex-1 truncate'>{c.name}</span>
                      <span className='h-2 w-24 rounded bg-muted'>
                        <span
                          className='block h-2 rounded bg-red-600'
                          style={{ width: `${c.criticality_index * 100}%` }}
                        />
                      </span>
                      <span className='w-12 text-right tabular-nums'>
                        {Math.round(c.criticality_index * 100)}%
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
