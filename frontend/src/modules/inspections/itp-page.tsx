import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, Lock, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/layout/page'
import { NativeSelect } from '@/components/native-select'
import { useTemplates } from './api'
import { useAnchorOptions, useApplyItp, useInstances } from './quality-api'

function ApplyDialog({
  projectId,
  onClose,
}: {
  projectId: number
  onClose: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: templates = [] } = useTemplates(projectId)
  const { data: anchors } = useAnchorOptions(projectId)
  const apply = useApplyItp()
  const [templateId, setTemplateId] = useState('')
  const [anchor, setAnchor] = useState('')
  const itps = templates.filter((tpl) => tpl.kind === 'itp')
  const [kind, id] = anchor.split(':')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.apply_itp')}</DialogTitle>
          <DialogDescription>
            {t('inspections.apply_itp_help')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-template'>{t('inspections.itp_template')}</Label>
          <NativeSelect
            id='itp-template'
            placeholder={t('inspections.choose_template')}
            options={itps.map((tpl) => ({
              value: String(tpl.id),
              label: `${tpl.name} (v${tpl.version}, ${tpl.item_count})`,
            }))}
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-anchor'>{t('inspections.anchor')}</Label>
          <NativeSelect
            id='itp-anchor'
            placeholder={t('inspections.choose_anchor')}
            options={[
              ...(anchors?.nodes ?? [])
                .filter((n) => n.anchor)
                .map((n) => ({ value: `node:${n.id}`, label: n.label })),
              ...(anchors?.items ?? []).map((i) => ({
                value: `item:${i.id}`,
                label: `${t('inspections.item')}: ${i.label}`,
              })),
            ]}
            value={anchor}
            onChange={(e) => setAnchor(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={!templateId || !anchor || apply.isPending}
            onClick={() =>
              apply.mutate(
                {
                  template_id: Number(templateId),
                  node_id: kind === 'node' ? Number(id) : null,
                  item_id: kind === 'item' ? Number(id) : null,
                },
                {
                  onSuccess: (made) => {
                    onClose()
                    void navigate({
                      to: `/inspections/itp/${made.id}` as never,
                    })
                  },
                }
              )
            }
          >
            {t('inspections.apply')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Instances({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: rows = [] } = useInstances(projectId)
  const [applying, setApplying] = useState(false)
  return (
    <div className='grid gap-3'>
      {can(session, 'inspections.create') ? (
        <div>
          <Button size='sm' onClick={() => setApplying(true)}>
            <Plus /> {t('inspections.apply_itp')}
          </Button>
        </div>
      ) : null}
      {rows.length ? (
        <div className='grid gap-2'>
          {rows.map((r) => (
            <Link
              key={r.id}
              to='/$'
              params={{ _splat: `inspections/itp/${r.id}` }}
              className='grid gap-2 rounded-md border p-3 hover:bg-muted sm:grid-cols-[110px_1fr_200px_120px] sm:items-center'
            >
              <span className='font-mono text-sm'>{r.code}</span>
              <span>
                <span className='font-medium'>{r.template_name}</span>
                <span className='block text-xs text-muted-foreground'>
                  {r.anchor_label}
                </span>
              </span>
              <span className='grid gap-1'>
                <span className='h-2 overflow-hidden rounded bg-muted'>
                  <span
                    className='block h-full bg-green-600'
                    style={{ width: `${r.progress}%` }}
                  />
                </span>
                <span className='text-xs text-muted-foreground'>
                  {r.lines_done}/{r.lines_total} · {r.progress}%
                </span>
              </span>
              <span className='flex items-center gap-1 text-sm'>
                {r.holds_open ? (
                  <>
                    <Lock className='size-4 text-red-600' />{' '}
                    {t('inspections.holds_open_n', { count: r.holds_open })}
                  </>
                ) : (
                  <span className='text-muted-foreground'>—</span>
                )}
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_itps')}
        </p>
      )}
      {applying ? (
        <ApplyDialog projectId={projectId} onClose={() => setApplying(false)} />
      ) : null}
    </div>
  )
}

export default function ItpPage() {
  const { t } = useTranslation()
  const project = useCurrentProject()
  return (
    <Page
      title={t('inspections.itps')}
      description={t('inspections.itps_description')}
      projectScoped
      actions={
        <Button size='sm' variant='ghost' asChild>
          <Link to='/$' params={{ _splat: 'inspections' }}>
            <ArrowLeft /> {t('inspections.register')}
          </Link>
        </Button>
      }
    >
      {project ? (
        <Instances key={project.id} projectId={project.id} />
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('inspections.no_project')}
        </p>
      )}
    </Page>
  )
}
