import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { statusLabel } from '@/components/records/status'
import {
  BANKING_FIELDS,
  CONTACT_TYPES,
  type Company,
  type CompanyIn,
  useDeleteCompany,
  useSaveCompany,
} from './api'

function draftOf(c: Company | null): CompanyIn {
  return {
    name: c?.name ?? '',
    type: (c?.type ?? 'other') as CompanyIn['type'],
    tax_id: c?.tax_id ?? '',
    address: c?.address ?? '',
    phone: c?.phone ?? '',
    email: c?.email ?? '',
    website: c?.website ?? '',
    banking: { ...(c?.banking ?? {}) },
    notes: c?.notes ?? '',
  }
}

export function CompanyDialog({
  company,
  onClose,
}: {
  /** The company to edit, or `null` for a new one. */
  company: Company | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const session = useSession()
  const editable = can(session, company ? 'contacts.update' : 'contacts.create')
  const save = useSaveCompany()
  const remove = useDeleteCompany()
  const [draft, setDraft] = useState<CompanyIn>(() => draftOf(company))
  const set = (patch: Partial<CompanyIn>) =>
    setDraft((d) => ({ ...d, ...patch }))
  const text = (key: keyof CompanyIn, label: string, max = 200) => (
    <div className='grid gap-1.5'>
      <Label htmlFor={`co-${key}`}>{label}</Label>
      <Input
        id={`co-${key}`}
        maxLength={max}
        value={(draft[key] as string | null) ?? ''}
        onChange={(e) => set({ [key]: e.target.value })}
      />
    </div>
  )

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {company ? company.name : t('contacts.new_company')}
          </DialogTitle>
        </DialogHeader>
        <form
          id='company-form'
          className='grid gap-4'
          onSubmit={(e) => {
            e.preventDefault()
            const body: CompanyIn = {
              ...draft,
              tax_id: draft.tax_id || null,
              address: draft.address || null,
              phone: draft.phone || null,
              email: draft.email || null,
              website: draft.website || null,
              notes: draft.notes || null,
              banking: Object.fromEntries(
                Object.entries(draft.banking ?? {}).filter(([, v]) => v)
              ),
            }
            save.mutate(
              { id: company?.id, body },
              {
                onSuccess: () => {
                  toast.success(t('contacts.company_saved'))
                  onClose()
                },
              }
            )
          }}
        >
          <fieldset disabled={!editable} className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='co-name'>{t('contacts.company_name')}</Label>
              <Input
                id='co-name'
                required
                maxLength={200}
                value={draft.name}
                onChange={(e) => set({ name: e.target.value })}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='co-type'>{t('contacts.type')}</Label>
              <Select
                value={draft.type}
                onValueChange={(v) => set({ type: v as CompanyIn['type'] })}
              >
                <SelectTrigger id='co-type' className='w-full'>
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
            </div>
            {text('tax_id', t('contacts.tax_id'), 50)}
            {text('phone', t('contacts.phone'), 50)}
            {text('email', t('contacts.email'))}
            {text('website', t('contacts.website'))}
            <div className='grid gap-1.5 sm:col-span-2'>
              <Label htmlFor='co-address'>{t('contacts.address')}</Label>
              <Textarea
                id='co-address'
                rows={2}
                value={draft.address ?? ''}
                onChange={(e) => set({ address: e.target.value })}
              />
            </div>
          </fieldset>
          <fieldset
            disabled={!editable}
            className='grid gap-3 rounded-md border p-3 sm:grid-cols-2'
          >
            <legend className='px-1 text-sm font-medium'>
              {t('contacts.banking')}
            </legend>
            {BANKING_FIELDS.map((key) => (
              <div key={key} className='grid gap-1.5'>
                <Label htmlFor={`bank-${key}`}>
                  {t(`contacts.bank.${key}`)}
                </Label>
                <Input
                  id={`bank-${key}`}
                  autoComplete='off'
                  value={draft.banking?.[key] ?? ''}
                  onChange={(e) =>
                    set({
                      banking: { ...draft.banking, [key]: e.target.value },
                    })
                  }
                />
              </div>
            ))}
          </fieldset>
          <fieldset disabled={!editable} className='grid gap-1.5'>
            <Label htmlFor='co-notes'>{t('contacts.notes')}</Label>
            <Textarea
              id='co-notes'
              rows={2}
              value={draft.notes ?? ''}
              onChange={(e) => set({ notes: e.target.value })}
            />
          </fieldset>
        </form>
        <DialogFooter className='gap-2'>
          {company && can(session, 'contacts.delete') ? (
            <Button
              type='button'
              variant='ghost'
              className='me-auto text-red-600'
              onClick={() => {
                if (window.confirm(t('contacts.confirm_delete_company')))
                  remove.mutate(company.id, { onSuccess: onClose })
              }}
            >
              <Trash2 /> {t('contacts.delete')}
            </Button>
          ) : null}
          <Button type='button' variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {editable ? (
            <Button type='submit' form='company-form' disabled={save.isPending}>
              {company ? t('common.save') : t('common.create')}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
