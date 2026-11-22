import { useState } from 'react'
import { useProjects } from '@/modules/projects/api'
import { Link2, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
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
import { Textarea } from '@/components/ui/textarea'
import { RecordSheet } from '@/components/records/record-sheet'
import { statusLabel } from '@/components/records/status'
import {
  CONTACT_TYPES,
  type Contact,
  type ContactIn,
  useCompanies,
  useDeleteContact,
  useLinkProject,
  useSaveContact,
} from './api'

const NONE = 'none'

type Draft = Omit<ContactIn, 'tags'> & { tags: string }

function draftOf(c: Contact | null): Draft {
  return {
    first_name: c?.first_name ?? '',
    last_name: c?.last_name ?? '',
    company_id: c?.company_id ?? null,
    type: (c?.type ?? 'other') as ContactIn['type'],
    job_title: c?.job_title ?? '',
    email: c?.email ?? '',
    phone: c?.phone ?? '',
    mobile: c?.mobile ?? '',
    tags: (c?.tags ?? []).join(', '),
    notes: c?.notes ?? '',
  }
}

function Field({
  id,
  label,
  children,
}: {
  id: string
  label: string
  children: React.ReactNode
}) {
  return (
    <div className='grid gap-1.5'>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

function ProjectRoles({ contact }: { contact: Contact }) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, 'contacts.update')
  const current = useCurrentProject()
  const { data: projects = [] } = useProjects()
  const link = useLinkProject()
  const [projectId, setProjectId] = useState<number | null>(current?.id ?? null)
  const [role, setRole] = useState('')

  return (
    <div className='grid gap-3'>
      {contact.projects?.length ? (
        <ul className='grid gap-1.5'>
          {contact.projects.map((p) => (
            <li
              key={p.project_id}
              className='flex items-center gap-2 rounded-md border px-3 py-2 text-sm'
            >
              <span className='font-mono text-xs'>{p.project_code}</span>
              <span className='flex-1 truncate'>{p.project_name}</span>
              {p.role ? <Badge variant='outline'>{p.role}</Badge> : null}
              {editable ? (
                <button
                  type='button'
                  aria-label={t('contacts.unlink')}
                  className='text-muted-foreground hover:text-red-600'
                  onClick={() =>
                    link.mutate({
                      contactId: contact.id,
                      projectId: p.project_id,
                      role: null,
                      unlink: true,
                    })
                  }
                >
                  <X className='size-4' />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className='text-sm text-muted-foreground'>
          {t('contacts.no_projects')}
        </p>
      )}
      {editable ? (
        <form
          className='grid gap-2 rounded-md border p-3'
          onSubmit={(e) => {
            e.preventDefault()
            if (!projectId) return
            link.mutate(
              { contactId: contact.id, projectId, role: role || null },
              { onSuccess: () => setRole('') }
            )
          }}
        >
          <h4 className='text-sm font-medium'>{t('contacts.link_project')}</h4>
          <Select
            value={projectId ? String(projectId) : undefined}
            onValueChange={(v) => setProjectId(Number(v))}
          >
            <SelectTrigger
              className='w-full'
              aria-label={t('contacts.project')}
            >
              <SelectValue placeholder={t('contacts.project')} />
            </SelectTrigger>
            <SelectContent>
              {projects.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.code} {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder={t('contacts.role_placeholder')}
            value={role}
            maxLength={150}
            onChange={(e) => setRole(e.target.value)}
          />
          <Button
            type='submit'
            size='sm'
            className='w-fit'
            disabled={!projectId || link.isPending}
          >
            <Link2 /> {t('contacts.link')}
          </Button>
        </form>
      ) : null}
    </div>
  )
}

export function ContactSheet({
  contact,
  open,
  onClose,
}: {
  contact: Contact | null
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, contact ? 'contacts.update' : 'contacts.create')
  const { data: companies = [] } = useCompanies()
  const save = useSaveContact()
  const remove = useDeleteContact()
  const [draft, setDraft] = useState<Draft>(() => draftOf(contact))
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))

  const submit = () => {
    const body: ContactIn = {
      ...draft,
      job_title: draft.job_title || null,
      email: draft.email || null,
      phone: draft.phone || null,
      mobile: draft.mobile || null,
      notes: draft.notes || null,
      tags: draft.tags
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    }
    save.mutate(
      { id: contact?.id, body },
      {
        onSuccess: () => {
          toast.success(t('contacts.saved'))
          onClose()
        },
      }
    )
  }

  return (
    <RecordSheet
      open={open}
      onClose={onClose}
      title={contact ? contact.full_name : t('contacts.new')}
      subtitle={contact?.company_name ?? undefined}
      badges={
        contact ? (
          <>
            <Badge variant='secondary'>{statusLabel(contact.type)}</Badge>
            {contact.tags.map((tag) => (
              <Badge key={tag} variant='outline'>
                {tag}
              </Badge>
            ))}
          </>
        ) : null
      }
      tabs={
        contact
          ? { [t('contacts.projects')]: <ProjectRoles contact={contact} /> }
          : undefined
      }
    >
      <form
        className='grid gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <fieldset disabled={!editable} className='grid grid-cols-2 gap-3'>
          <Field id='c-first' label={t('contacts.first_name')}>
            <Input
              id='c-first'
              required
              maxLength={100}
              value={draft.first_name}
              onChange={(e) => set({ first_name: e.target.value })}
            />
          </Field>
          <Field id='c-last' label={t('contacts.last_name')}>
            <Input
              id='c-last'
              maxLength={100}
              value={draft.last_name ?? ''}
              onChange={(e) => set({ last_name: e.target.value })}
            />
          </Field>
          <Field id='c-company' label={t('contacts.company')}>
            <Select
              value={draft.company_id ? String(draft.company_id) : NONE}
              onValueChange={(v) =>
                set({ company_id: v === NONE ? null : Number(v) })
              }
            >
              <SelectTrigger id='c-company' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t('contacts.no_company')}</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id='c-type' label={t('contacts.type')}>
            <Select
              value={draft.type}
              onValueChange={(v) => set({ type: v as ContactIn['type'] })}
            >
              <SelectTrigger id='c-type' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONTACT_TYPES.map((v) => (
                  <SelectItem key={v} value={v}>
                    {statusLabel(v)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field id='c-job' label={t('contacts.job_title')}>
            <Input
              id='c-job'
              maxLength={150}
              value={draft.job_title ?? ''}
              onChange={(e) => set({ job_title: e.target.value })}
            />
          </Field>
          <Field id='c-email' label={t('contacts.email')}>
            <Input
              id='c-email'
              type='email'
              maxLength={200}
              value={draft.email ?? ''}
              onChange={(e) => set({ email: e.target.value })}
            />
          </Field>
          <Field id='c-phone' label={t('contacts.phone')}>
            <Input
              id='c-phone'
              maxLength={50}
              value={draft.phone ?? ''}
              onChange={(e) => set({ phone: e.target.value })}
            />
          </Field>
          <Field id='c-mobile' label={t('contacts.mobile')}>
            <Input
              id='c-mobile'
              maxLength={50}
              value={draft.mobile ?? ''}
              onChange={(e) => set({ mobile: e.target.value })}
            />
          </Field>
          <div className='col-span-2'>
            <Field id='c-tags' label={t('contacts.tags')}>
              <Input
                id='c-tags'
                placeholder={t('contacts.tags_hint')}
                value={draft.tags}
                onChange={(e) => set({ tags: e.target.value })}
              />
            </Field>
          </div>
          <div className='col-span-2'>
            <Field id='c-notes' label={t('contacts.notes')}>
              <Textarea
                id='c-notes'
                rows={3}
                value={draft.notes ?? ''}
                onChange={(e) => set({ notes: e.target.value })}
              />
            </Field>
          </div>
        </fieldset>
        {editable ? (
          <div className='flex items-center gap-2'>
            <Button type='submit' disabled={save.isPending}>
              {contact ? t('common.save') : t('common.create')}
            </Button>
            {contact && can(session, 'contacts.delete') ? (
              <Button
                type='button'
                variant='ghost'
                className='ms-auto text-red-600'
                onClick={() => {
                  if (window.confirm(t('contacts.confirm_delete')))
                    remove.mutate(contact.id, { onSuccess: onClose })
                }}
              >
                <Trash2 /> {t('contacts.delete')}
              </Button>
            ) : null}
          </div>
        ) : null}
      </form>
    </RecordSheet>
  )
}
