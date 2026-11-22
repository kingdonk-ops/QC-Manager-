import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/layout/page'
import { NativeSelect, UserSelect } from '@/components/native-select'
import {
  type Competency,
  formatWhen,
  localToIso,
  useCompetencies,
  useDelegationAction,
  useDelegations,
  useDeleteCompetency,
  useSaveCompetency,
} from './quality-api'

function Expiry({ c }: { c: Competency }) {
  const { t } = useTranslation()
  if (!c.expires_on)
    return (
      <span className='text-muted-foreground'>
        {t('inspections.no_expiry')}
      </span>
    )
  const days = c.expires_in_days ?? 0
  const tone = !c.valid_today
    ? 'text-red-600'
    : days <= 30
      ? 'text-amber-600'
      : 'text-green-700'
  return (
    <span className={tone}>
      {c.expires_on}{' '}
      {c.valid_today
        ? t('inspections.expires_in', { count: days })
        : t('inspections.expired')}
    </span>
  )
}

function Register() {
  const { t } = useTranslation()
  const session = useSession()
  const manage = can(session, 'inspections.manage')
  const [userId, setUserId] = useState<number | null>(
    manage ? null : session.id
  )
  const { data: rows = [] } = useCompetencies(userId)
  const save = useSaveCompetency()
  const remove = useDeleteCompetency()
  const [draft, setDraft] = useState({
    user_id: null as number | null,
    qualification: '',
    level: '',
    number: '',
    issued_on: '',
    expires_on: '',
  })
  return (
    <Card>
      <CardHeader className='flex flex-row items-center gap-2'>
        <CardTitle className='text-base'>
          {t('inspections.competencies')}
        </CardTitle>
        {manage ? (
          <div className='ms-auto w-56'>
            <UserSelect
              value={userId}
              onChange={setUserId}
              placeholder={t('inspections.everyone')}
            />
          </div>
        ) : null}
      </CardHeader>
      <CardContent className='grid gap-3'>
        <div className='grid gap-1'>
          {rows.map((c) => (
            <div
              key={c.id}
              className='grid gap-1 rounded-md border p-2 text-sm sm:grid-cols-[160px_1fr_140px_220px_40px] sm:items-center'
            >
              <span>{c.user_name}</span>
              <span>
                <span className='font-medium'>{c.qualification}</span>
                {c.level ? ` · ${c.level}` : ''}
                {c.number ? (
                  <span className='text-muted-foreground'> · {c.number}</span>
                ) : null}
              </span>
              <span className='text-muted-foreground'>
                {c.issued_on ?? '—'}
              </span>
              <Expiry c={c} />
              {manage ? (
                <Button
                  size='icon'
                  variant='ghost'
                  aria-label={t('inspections.delete')}
                  onClick={() => remove.mutate(c.id)}
                >
                  <Trash2 />
                </Button>
              ) : (
                <span />
              )}
            </div>
          ))}
          {!rows.length ? (
            <p className='text-sm text-muted-foreground'>
              {t('inspections.no_competencies')}
            </p>
          ) : null}
        </div>
        {manage ? (
          <form
            className='grid gap-2 rounded-md border p-3 sm:grid-cols-3'
            onSubmit={(e) => {
              e.preventDefault()
              if (!draft.user_id) return
              save.mutate(
                {
                  body: {
                    user_id: draft.user_id,
                    qualification: draft.qualification,
                    level: draft.level || null,
                    number: draft.number || null,
                    issued_on: draft.issued_on || null,
                    expires_on: draft.expires_on || null,
                    verified: false,
                  },
                },
                {
                  onSuccess: () =>
                    setDraft({ ...draft, qualification: '', number: '' }),
                }
              )
            }}
          >
            <div className='grid gap-1.5'>
              <Label>{t('inspections.person')}</Label>
              <UserSelect
                value={draft.user_id}
                onChange={(id) => setDraft({ ...draft, user_id: id })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='comp-q'>{t('inspections.qualification')}</Label>
              <Input
                id='comp-q'
                required
                placeholder='Coating inspector'
                value={draft.qualification}
                onChange={(e) =>
                  setDraft({ ...draft, qualification: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='comp-level'>{t('inspections.level')}</Label>
              <Input
                id='comp-level'
                value={draft.level}
                onChange={(e) => setDraft({ ...draft, level: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='comp-number'>{t('inspections.number')}</Label>
              <Input
                id='comp-number'
                value={draft.number}
                onChange={(e) => setDraft({ ...draft, number: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='comp-issued'>{t('inspections.issued_on')}</Label>
              <Input
                id='comp-issued'
                type='date'
                value={draft.issued_on}
                onChange={(e) =>
                  setDraft({ ...draft, issued_on: e.target.value })
                }
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='comp-expires'>
                {t('inspections.expires_on')}
              </Label>
              <Input
                id='comp-expires'
                type='date'
                value={draft.expires_on}
                onChange={(e) =>
                  setDraft({ ...draft, expires_on: e.target.value })
                }
              />
            </div>
            <div className='sm:col-span-3'>
              <Button
                type='submit'
                size='sm'
                disabled={!draft.user_id || save.isPending}
              >
                <Plus /> {t('inspections.add_competency')}
              </Button>
            </div>
          </form>
        ) : null}
      </CardContent>
    </Card>
  )
}

function Delegations({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const { data: rows = [] } = useDelegations(projectId)
  const act = useDelegationAction()
  const [draft, setDraft] = useState({
    delegate_id: null as number | null,
    kind: 'hold_point',
    ends_at: '',
    reason: '',
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>
          {t('inspections.delegations')}
        </CardTitle>
      </CardHeader>
      <CardContent className='grid gap-3'>
        <p className='text-sm text-muted-foreground'>
          {t('inspections.delegation_help')}
        </p>
        {rows.map((d) => (
          <div
            key={d.id}
            className='flex flex-wrap items-center gap-2 rounded-md border p-2 text-sm'
          >
            <span className='font-medium'>{d.delegator_name}</span> →{' '}
            <span>{d.delegate_name}</span>
            <span className='text-muted-foreground'>
              {t(`inspections.delegation_kind.${d.kind}`)} ·{' '}
              {formatWhen(d.starts_at)} – {formatWhen(d.ends_at)}
            </span>
            <span
              className={d.active ? 'text-green-700' : 'text-muted-foreground'}
            >
              {d.active
                ? t('inspections.active')
                : d.revoked_at
                  ? t('inspections.revoked')
                  : t('inspections.inactive')}
            </span>
            {d.active ? (
              <Button
                size='sm'
                variant='outline'
                className='ms-auto'
                onClick={() => act.mutate({ revoke: d.id })}
              >
                {t('inspections.revoke')}
              </Button>
            ) : null}
          </div>
        ))}
        <form
          className='grid gap-2 rounded-md border p-3 sm:grid-cols-4 sm:items-end'
          onSubmit={(e) => {
            e.preventDefault()
            if (!draft.delegate_id) return
            act.mutate({
              create: {
                project_id: projectId,
                delegate_id: draft.delegate_id,
                kind: draft.kind as 'hold_point',
                ends_at: localToIso(draft.ends_at),
                reason: draft.reason || null,
              },
            })
          }}
        >
          <div className='grid gap-1.5'>
            <Label>{t('inspections.delegate')}</Label>
            <UserSelect
              value={draft.delegate_id}
              onChange={(id) => setDraft({ ...draft, delegate_id: id })}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='del-kind'>{t('inspections.kind')}</Label>
            <NativeSelect
              id='del-kind'
              options={[
                {
                  value: 'hold_point',
                  label: t('inspections.delegation_kind.hold_point'),
                },
                {
                  value: 'review',
                  label: t('inspections.delegation_kind.review'),
                },
              ]}
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='del-end'>{t('inspections.until')}</Label>
            <Input
              id='del-end'
              type='datetime-local'
              required
              value={draft.ends_at}
              onChange={(e) => setDraft({ ...draft, ends_at: e.target.value })}
            />
          </div>
          <Button type='submit' disabled={!draft.delegate_id || act.isPending}>
            {t('inspections.name_delegate')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

export default function CompetenciesPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.competencies')}
      description={t('inspections.competencies_description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      <div className='grid gap-4'>
        <Register />
        {project ? (
          <Delegations key={project.id} projectId={project.id} />
        ) : null}
      </div>
    </Page>
  )
}
