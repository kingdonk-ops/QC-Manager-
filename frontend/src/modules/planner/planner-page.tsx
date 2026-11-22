import { useMemo, useState } from 'react'
import type { ColDef, ICellRendererParams } from 'ag-grid-community'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { NodeSelect } from '@/components/asset-node-picker'
import { DataGrid } from '@/components/data-grid'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import { StatusBadge } from '@/components/records/status-badge'
import {
  CONSTRAINT_CATEGORIES,
  type Constraint,
  type Pack,
  PLAN_KINDS,
  PLAN_NEXT,
  type Plan,
  plannerApi,
  useConstraints,
  useCrews,
  usePacks,
  usePlanVsActual,
  usePlannerMutation,
  usePlans,
} from './api'
import { PlanBoard } from './board'
import { parseMembers, readinessTone } from './board-lib'
import { PackSheet } from './pack-sheet'

function param(name: string) {
  const v = Number(new URLSearchParams(window.location.search).get(name))
  return Number.isFinite(v) && v > 0 ? v : null
}

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return d.toLocaleDateString('en-CA')
}

const num = (v: unknown) =>
  v === null || v === undefined ? '' : Number(v).toLocaleString()

export default function PlannerPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('planner.title')}
      description={t('planner.description')}
      projectScoped
      fixed
    >
      {project ? (
        <Planner key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('planner.no_project')}
        </p>
      )}
    </Page>
  )
}

function Planner({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: plans = [] } = usePlans(projectId)
  const [chosen, setChosen] = useState<number | null>(() => param('plan'))
  const [packId, setPackId] = useState<number | null>(() => param('pack'))
  const [creating, setCreating] = useState(false)
  const plan = plans.find((p) => p.id === chosen) ?? plans[0] ?? null
  const transition = usePlannerMutation(plannerApi.transitionPlan)

  return (
    <div className='flex min-h-0 flex-1 flex-col gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        <NativeSelect
          className='h-8 w-72'
          aria-label={t('planner.plan')}
          options={plans.map((p) => ({
            value: String(p.id),
            label: `${p.code} ${p.title}`,
          }))}
          placeholder={plans.length ? undefined : t('planner.no_plans')}
          value={plan ? String(plan.id) : ''}
          onChange={(e) => setChosen(Number(e.target.value) || null)}
        />
        {plan ? (
          <>
            <StatusBadge status={plan.status} />
            <span className='text-xs text-muted-foreground'>
              {plan.kind.replace(/_/g, ' ')} · {plan.window_start} →{' '}
              {plan.window_end} · {plan.pack_count} packs · {plan.anchor_count}{' '}
              work anchors · {num(plan.planned_hours)} h
            </span>
          </>
        ) : null}
        <div className='ms-auto flex gap-2'>
          {plan && can(session, 'planner.transition')
            ? (PLAN_NEXT[plan.status] ?? []).map((s) => (
                <Button
                  key={s}
                  size='sm'
                  variant='outline'
                  onClick={() => transition.mutate({ id: plan.id, status: s })}
                >
                  {t(`planner.to.${s}`)}
                </Button>
              ))
            : null}
          {can(session, 'planner.create') ? (
            <Button size='sm' onClick={() => setCreating(true)}>
              <Plus /> {t('planner.new_plan')}
            </Button>
          ) : null}
        </div>
      </div>
      <Tabs defaultValue='board' className='min-h-0 flex-1'>
        <TabsList>
          <TabsTrigger value='board'>{t('planner.board')}</TabsTrigger>
          <TabsTrigger value='packs'>{t('planner.packs')}</TabsTrigger>
          <TabsTrigger value='constraints'>
            {t('planner.constraints')}
          </TabsTrigger>
          <TabsTrigger value='actual'>{t('planner.actual')}</TabsTrigger>
          <TabsTrigger value='crews'>{t('planner.crews')}</TabsTrigger>
        </TabsList>
        <TabsContent value='board' className='min-h-0 overflow-auto'>
          {plan ? (
            <PlanBoard planId={plan.id} onOpenPack={setPackId} />
          ) : (
            <p className='text-sm text-muted-foreground'>
              {t('planner.no_plans')}
            </p>
          )}
        </TabsContent>
        <TabsContent value='packs'>
          {plan ? (
            <Packs projectId={projectId} plan={plan} onOpen={setPackId} />
          ) : null}
        </TabsContent>
        <TabsContent value='constraints'>
          <Constraints projectId={projectId} plan={plan} />
        </TabsContent>
        <TabsContent value='actual'>
          {plan ? <Actuals planId={plan.id} /> : null}
        </TabsContent>
        <TabsContent value='crews'>
          <Crews projectId={projectId} />
        </TabsContent>
      </Tabs>
      {creating ? (
        <NewPlan
          projectId={projectId}
          onClose={() => setCreating(false)}
          onCreated={setChosen}
        />
      ) : null}
      <PackSheet
        id={packId}
        projectId={projectId}
        onClose={() => setPackId(null)}
      />
    </div>
  )
}

function NewPlan({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const { t } = useTranslation()
  const today = new Date().toLocaleDateString('en-CA')
  const [draft, setDraft] = useState({
    title: '',
    kind: 'look_ahead',
    window_start: today,
    window_end: addDays(today, 13),
    client_ref: '',
  })
  const create = usePlannerMutation(plannerApi.createPlan)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{t('planner.new_plan')}</DialogTitle>
        </DialogHeader>
        <form
          id='new-plan'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                title: draft.title,
                kind: draft.kind as never,
                window_start: draft.window_start,
                window_end: draft.window_end,
                client_ref: draft.client_ref || null,
              },
              {
                onSuccess: (p) => {
                  onCreated(p.id)
                  onClose()
                },
              }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='plan-title'>{t('planner.plan_title')}</Label>
            <Input
              id='plan-title'
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </div>
          <div className='grid grid-cols-2 gap-3'>
            <div className='grid gap-1.5'>
              <Label htmlFor='plan-kind'>{t('planner.kind')}</Label>
              <NativeSelect
                id='plan-kind'
                values={PLAN_KINDS}
                value={draft.kind}
                onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='plan-ref'>{t('planner.client_ref')}</Label>
              <Input
                id='plan-ref'
                value={draft.client_ref}
                onChange={(e) =>
                  setDraft({ ...draft, client_ref: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='plan-start'>{t('planner.start')}</Label>
              <Input
                id='plan-start'
                type='date'
                required
                value={draft.window_start}
                onChange={(e) =>
                  setDraft({ ...draft, window_start: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='plan-end'>{t('planner.end')}</Label>
              <Input
                id='plan-end'
                type='date'
                required
                value={draft.window_end}
                onChange={(e) =>
                  setDraft({ ...draft, window_end: e.target.value })
                }
              />
            </div>
          </div>
        </form>
        <DialogFooter>
          <Button type='submit' form='new-plan' disabled={create.isPending}>
            {t('planner.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Packs({
  projectId,
  plan,
  onOpen,
}: {
  projectId: number
  plan: Plan
  onOpen: (id: number) => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: packs = [] } = usePacks(projectId, plan.id)
  const { data: crews = [] } = useCrews(projectId)
  const [draft, setDraft] = useState({ title: '', crew_id: '' })
  const create = usePlannerMutation(plannerApi.createPack)
  const columns = useMemo<ColDef<Pack>[]>(
    () => [
      { field: 'code', headerName: t('planner.code'), width: 90 },
      { field: 'title', headerName: t('planner.pack_title'), flex: 1 },
      { field: 'crew_name', headerName: t('planner.crew'), width: 160 },
      {
        field: 'status',
        width: 120,
        headerName: t('planner.status'),
        cellRenderer: (p: ICellRendererParams<Pack>) => (
          <StatusBadge status={p.value} />
        ),
      },
      {
        field: 'readiness',
        width: 140,
        headerName: t('planner.readiness'),
        cellRenderer: (p: ICellRendererParams<Pack>) => (
          <Badge
            variant='outline'
            title={(p.data?.findings ?? []).map((f) => f.message).join('\n')}
            className={cn('border-transparent', readinessTone(p.value))}
          >
            {p.value}
            {p.data?.findings?.length ? ` (${p.data.findings.length})` : ''}
          </Badge>
        ),
      },
      { field: 'planned_start', headerName: t('planner.start'), width: 110 },
      { field: 'planned_end', headerName: t('planner.end'), width: 110 },
      {
        field: 'planned_hours',
        headerName: t('planner.hours'),
        width: 90,
        type: 'rightAligned',
        valueFormatter: (p) => num(p.value),
      },
    ],
    [t]
  )
  return (
    <div className='grid gap-2'>
      {can(session, 'planner.create') ? (
        <form
          className='flex flex-wrap gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                plan_id: plan.id,
                title: draft.title,
                crew_id: draft.crew_id ? Number(draft.crew_id) : null,
                lines: [],
              },
              {
                onSuccess: (p) => {
                  setDraft({ title: '', crew_id: '' })
                  onOpen(p.id)
                },
              }
            )
          }}
        >
          <Input
            className='h-8 w-72'
            required
            placeholder={t('planner.pack_title')}
            aria-label={t('planner.pack_title')}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
          <NativeSelect
            className='h-8 w-48'
            aria-label={t('planner.crew')}
            placeholder={t('planner.no_crew')}
            options={crews.map((c) => ({
              value: String(c.id),
              label: `${c.code} ${c.name}`,
            }))}
            value={draft.crew_id}
            onChange={(e) => setDraft({ ...draft, crew_id: e.target.value })}
          />
          <Button size='sm' type='submit' disabled={create.isPending}>
            <Plus /> {t('planner.new_pack')}
          </Button>
        </form>
      ) : null}
      <div className='h-[480px]'>
        <DataGrid<Pack>
          rowData={packs}
          columnDefs={columns}
          getRowId={(p) => String(p.data.id)}
          rowClass='cursor-pointer'
          onRowClicked={(e) => e.data && onOpen(e.data.id)}
        />
      </div>
    </div>
  )
}

function Constraints({
  projectId,
  plan,
}: {
  projectId: number
  plan: Plan | null
}) {
  const { t } = useTranslation()
  const session = useSession()
  const [status, setStatus] = useState('open')
  const { data: rows = [] } = useConstraints(projectId, status)
  const [draft, setDraft] = useState({
    category: 'materials',
    description: '',
    node_id: null as number | null,
    node_label: '' as string | null,
    owner_id: null as number | null,
    due_date: '',
  })
  const create = usePlannerMutation(plannerApi.createConstraint)
  const resolve = usePlannerMutation(plannerApi.resolveConstraint)
  return (
    <div className='grid gap-3'>
      {can(session, 'planner.create') ? (
        <form
          className='grid gap-2 rounded-md border p-3 sm:grid-cols-6'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                plan_id: plan?.id ?? null,
                category: draft.category as never,
                description: draft.description,
                node_id: draft.node_id,
                owner_id: draft.owner_id,
                due_date: draft.due_date || null,
              },
              {
                onSuccess: () =>
                  setDraft({ ...draft, description: '', node_id: null }),
              }
            )
          }}
        >
          <NativeSelect
            aria-label={t('planner.category')}
            values={CONSTRAINT_CATEGORIES}
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          />
          <Input
            className='sm:col-span-2'
            required
            placeholder={t('planner.constraint')}
            aria-label={t('planner.constraint')}
            value={draft.description}
            onChange={(e) =>
              setDraft({ ...draft, description: e.target.value })
            }
          />
          <NodeSelect
            projectId={projectId}
            value={draft.node_id}
            label={draft.node_label}
            placeholder={t('planner.where')}
            onChange={(id, n) =>
              setDraft({
                ...draft,
                node_id: id,
                node_label: n ? n.display_path : null,
              })
            }
          />
          <UserSelect
            value={draft.owner_id}
            placeholder={t('planner.owner')}
            onChange={(id) => setDraft({ ...draft, owner_id: id })}
          />
          <div className='flex gap-2'>
            <Input
              type='date'
              aria-label={t('planner.due')}
              value={draft.due_date}
              onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
            />
            <Button type='submit' disabled={create.isPending}>
              {t('planner.log')}
            </Button>
          </div>
        </form>
      ) : null}
      <NativeSelect
        className='h-8 w-40'
        aria-label={t('planner.status')}
        options={[
          { value: 'open', label: 'Open' },
          { value: 'resolved', label: 'Resolved' },
          { value: '', label: 'All' },
        ]}
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      />
      <ul className='divide-y rounded-md border text-sm'>
        {rows.length === 0 ? (
          <li className='p-3 text-muted-foreground'>
            {t('planner.no_constraints')}
          </li>
        ) : null}
        {rows.map((c: Constraint) => (
          <li key={c.id} className='flex flex-wrap items-center gap-2 p-2'>
            <span className='font-mono text-xs'>{c.code}</span>
            <StatusBadge status={c.overdue ? 'overdue' : c.status} />
            <Badge variant='outline'>{c.category}</Badge>
            <span className='min-w-48 flex-1'>{c.description}</span>
            <span className='text-xs text-muted-foreground'>
              {c.owner_name ?? '—'} {c.due_date ? `· due ${c.due_date}` : ''}
            </span>
            {c.status === 'open' && can(session, 'planner.update') ? (
              <Button
                size='sm'
                variant='outline'
                className='h-7'
                onClick={() => {
                  const resolution = window.prompt(t('planner.resolution'))
                  if (resolution !== null)
                    resolve.mutate({ id: c.id, resolution })
                }}
              >
                {t('planner.resolve')}
              </Button>
            ) : null}
            {c.resolution ? (
              <span className='w-full text-xs text-muted-foreground'>
                {c.resolution}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Actuals({ planId }: { planId: number }) {
  const { t } = useTranslation()
  const { data } = usePlanVsActual(planId)
  if (!data) return null
  return (
    <div className='overflow-x-auto rounded-md border'>
      <table className='w-full text-sm'>
        <thead className='bg-muted/50 text-xs text-muted-foreground'>
          <tr>
            <th className='p-2 text-left'>{t('planner.work_anchor')}</th>
            <th className='p-2 text-right'>{t('planner.planned_qty')}</th>
            <th className='p-2 text-right'>{t('planner.actual_qty')}</th>
            <th className='p-2 text-right'>%</th>
            <th className='p-2 text-right'>{t('planner.earned')}</th>
            <th className='p-2 text-right'>{t('planner.planned_hours')}</th>
            <th className='p-2 text-right'>{t('planner.actual_hours')}</th>
            <th className='p-2 text-right'>{t('planner.days')}</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.anchor_id} className='border-t'>
              <td className='p-2'>
                <div className='font-medium'>{r.anchor_code}</div>
                <div className='text-xs text-muted-foreground'>
                  {r.anchor_path}
                </div>
              </td>
              <td className='p-2 text-right'>
                {num(r.planned_qty)} {r.uom}
              </td>
              <td className='p-2 text-right'>{num(r.actual_qty)}</td>
              <td className='p-2 text-right'>
                {r.percent_qty == null ? '—' : `${r.percent_qty}%`}
              </td>
              <td className='p-2 text-right'>
                {num(r.earned_qty)}
                {r.budget_qty != null ? ` / ${num(r.budget_qty)}` : ''}
              </td>
              <td className='p-2 text-right'>{num(r.planned_hours)}</td>
              <td
                className={cn(
                  'p-2 text-right',
                  Number(r.actual_hours) > Number(r.planned_hours) &&
                    Number(r.planned_hours) > 0 &&
                    'text-red-600'
                )}
              >
                {num(r.actual_hours)}
              </td>
              <td className='p-2 text-right'>{r.assigned_days}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className='border-t font-medium'>
          <tr>
            <td className='p-2'>{t('planner.total')}</td>
            <td className='p-2 text-right'>{num(data.planned_qty)}</td>
            <td className='p-2 text-right'>{num(data.actual_qty)}</td>
            <td />
            <td />
            <td className='p-2 text-right'>{num(data.planned_hours)}</td>
            <td className='p-2 text-right'>{num(data.actual_hours)}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function Crews({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: crews = [] } = useCrews(projectId)
  const [draft, setDraft] = useState({
    code: '',
    name: '',
    trade: '',
    supervisor_id: null as number | null,
    members: '',
  })
  const create = usePlannerMutation(plannerApi.createCrew)
  return (
    <div className='grid gap-3 lg:grid-cols-[1fr_22rem]'>
      <ul className='divide-y rounded-md border text-sm'>
        {crews.map((c) => (
          <li key={c.id} className='p-2'>
            <div className='flex items-center gap-2'>
              <span className='font-medium'>{c.code}</span>
              <span>{c.name}</span>
              <span className='text-xs text-muted-foreground'>
                {c.trade} · {c.headcount} · {c.supervisor_name ?? '—'}
              </span>
            </div>
            <div className='text-xs text-muted-foreground'>
              {c.members.map((m) => String(m.name)).join(', ')}
            </div>
          </li>
        ))}
        {crews.length === 0 ? (
          <li className='p-3 text-muted-foreground'>{t('planner.no_crews')}</li>
        ) : null}
      </ul>
      {can(session, 'planner.create') ? (
        <form
          className='grid content-start gap-2 rounded-md border p-3'
          onSubmit={(e) => {
            e.preventDefault()
            create.mutate(
              {
                project_id: projectId,
                code: draft.code,
                name: draft.name,
                trade: draft.trade || null,
                supervisor_id: draft.supervisor_id,
                members: parseMembers(draft.members),
                shift_hours: 10,
                active: true,
              },
              {
                onSuccess: () =>
                  setDraft({
                    code: '',
                    name: '',
                    trade: '',
                    supervisor_id: null,
                    members: '',
                  }),
              }
            )
          }}
        >
          <h4 className='text-sm font-semibold'>{t('planner.new_crew')}</h4>
          <div className='grid grid-cols-2 gap-2'>
            <Input
              required
              placeholder={t('planner.code')}
              aria-label={t('planner.code')}
              value={draft.code}
              onChange={(e) => setDraft({ ...draft, code: e.target.value })}
            />
            <Input
              placeholder={t('planner.trade')}
              aria-label={t('planner.trade')}
              value={draft.trade}
              onChange={(e) => setDraft({ ...draft, trade: e.target.value })}
            />
          </div>
          <Input
            required
            placeholder={t('planner.crew_name')}
            aria-label={t('planner.crew_name')}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <UserSelect
            value={draft.supervisor_id}
            placeholder={t('planner.supervisor')}
            onChange={(id) => setDraft({ ...draft, supervisor_id: id })}
          />
          <Textarea
            rows={5}
            placeholder={t('planner.members_help')}
            aria-label={t('planner.members')}
            value={draft.members}
            onChange={(e) => setDraft({ ...draft, members: e.target.value })}
          />
          <Button type='submit' disabled={create.isPending}>
            {t('planner.add_crew')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}
