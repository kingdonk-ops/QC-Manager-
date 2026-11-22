import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/layout/page'
import { useDeleteHours, useHours, useSetHours } from './api'
import { SafetyNav } from './dashboard-page'

function HoursRegister({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'safety.update')
  const { data: rows = [] } = useHours(projectId)
  const save = useSetHours()
  const remove = useDeleteHours()
  const [draft, setDraft] = useState({
    month: new Date().toISOString().slice(0, 7),
    hours: '',
    headcount: '',
  })
  const total = rows.reduce((sum, r) => sum + r.hours, 0)

  return (
    <div className='grid max-w-3xl gap-4'>
      {editable ? (
        <Card>
          <CardContent>
            <form
              className='grid items-end gap-3 sm:grid-cols-[1fr_1fr_1fr_auto]'
              onSubmit={(e) => {
                e.preventDefault()
                save.mutate(
                  {
                    project_id: projectId,
                    month: draft.month,
                    hours: Number(draft.hours),
                    headcount: draft.headcount ? Number(draft.headcount) : null,
                  },
                  {
                    onSuccess: () =>
                      setDraft({ ...draft, hours: '', headcount: '' }),
                  }
                )
              }}
            >
              <div className='grid gap-1.5'>
                <Label htmlFor='hours-month'>{t('safety.month')}</Label>
                <Input
                  id='hours-month'
                  type='month'
                  required
                  value={draft.month}
                  onChange={(e) =>
                    setDraft({ ...draft, month: e.target.value })
                  }
                />
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='hours-hours'>{t('safety.hours_worked')}</Label>
                <Input
                  id='hours-hours'
                  type='number'
                  inputMode='decimal'
                  min={0}
                  step='any'
                  required
                  value={draft.hours}
                  onChange={(e) =>
                    setDraft({ ...draft, hours: e.target.value })
                  }
                />
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='hours-heads'>{t('safety.headcount')}</Label>
                <Input
                  id='hours-heads'
                  type='number'
                  min={0}
                  value={draft.headcount}
                  onChange={(e) =>
                    setDraft({ ...draft, headcount: e.target.value })
                  }
                />
              </div>
              <Button type='submit' disabled={save.isPending}>
                {t('safety.save')}
              </Button>
            </form>
            <p className='pt-2 text-xs text-muted-foreground'>
              {t('safety.hours_hint')}
            </p>
          </CardContent>
        </Card>
      ) : null}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('safety.month')}</TableHead>
            <TableHead className='text-end'>
              {t('safety.hours_worked')}
            </TableHead>
            <TableHead className='text-end'>{t('safety.headcount')}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.id}>
              <TableCell>{r.month.slice(0, 7)}</TableCell>
              <TableCell className='text-end tabular-nums'>
                {r.hours.toLocaleString()}
              </TableCell>
              <TableCell className='text-end tabular-nums'>
                {r.headcount ?? '—'}
              </TableCell>
              <TableCell className='w-10'>
                {editable ? (
                  <button
                    aria-label={t('safety.delete')}
                    onClick={() => remove.mutate(r.id)}
                  >
                    <Trash2 className='size-4 text-muted-foreground hover:text-red-600' />
                  </button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}
          <TableRow className='font-semibold'>
            <TableCell>{t('common.total')}</TableCell>
            <TableCell className='text-end tabular-nums'>
              {total.toLocaleString()}
            </TableCell>
            <TableCell />
            <TableCell />
          </TableRow>
        </TableBody>
      </Table>
    </div>
  )
}

export default function HoursPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('safety.hours')}
      description={t('safety.hours_description')}
      projectScoped
      actions={<SafetyNav />}
    >
      {project ? (
        <HoursRegister key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('safety.no_project')}
        </p>
      )}
    </Page>
  )
}
