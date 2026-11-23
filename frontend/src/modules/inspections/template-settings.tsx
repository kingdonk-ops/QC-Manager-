import { useTranslation } from 'react-i18next'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/native-select'
import type { TemplateBody } from './api'
import { AREAS } from './quality-api'

type Settings = Pick<
  TemplateBody,
  | 'area'
  | 'is_formal'
  | 'audit_scope'
  | 'requires_client_signature'
  | 'required_qualification'
>

/** Area, formal, audit and signing settings of an inspection template (presets set them in one go). */
export function TemplateSettingsFields({
  value,
  onChange,
}: {
  value: Settings
  onChange: (next: Settings) => void
}) {
  const { t } = useTranslation()
  const presets: Record<string, Settings> = {
    qa: {
      area: 'qa_itp',
      is_formal: true,
      audit_scope: null,
      requires_client_signature: false,
    },
    hs: {
      area: 'health_safety',
      is_formal: false,
      audit_scope: null,
      requires_client_signature: false,
    },
    prestart: {
      area: 'safety_prestart',
      is_formal: false,
      audit_scope: null,
      requires_client_signature: false,
    },
    equipment: {
      area: 'equipment_check',
      is_formal: false,
      audit_scope: null,
      requires_client_signature: false,
    },
    repair: {
      area: 'repair_fault',
      is_formal: false,
      audit_scope: null,
      requires_client_signature: false,
    },
    internal_audit: {
      area: 'general',
      is_formal: true,
      audit_scope: 'internal',
      requires_client_signature: false,
    },
    external_audit: {
      area: 'general',
      is_formal: true,
      audit_scope: 'external',
      requires_client_signature: false,
    },
  }
  return (
    <div className='grid gap-3 rounded-md border p-3 sm:grid-cols-3'>
      <div className='grid gap-1.5'>
        <Label htmlFor='tpl-preset'>{t('inspections.preset')}</Label>
        <NativeSelect
          id='tpl-preset'
          placeholder='—'
          options={Object.keys(presets).map((k) => ({
            value: k,
            label: t(`inspections.presets.${k}`),
          }))}
          value=''
          onChange={(e) =>
            e.target.value && onChange({ ...value, ...presets[e.target.value] })
          }
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='tpl-area'>{t('inspections.template_area')}</Label>
        <NativeSelect
          id='tpl-area'
          options={AREAS.map((a) => ({
            value: a,
            label: t(`inspections.areas.${a}`),
          }))}
          value={value.area ?? 'general'}
          onChange={(e) =>
            onChange({ ...value, area: e.target.value as Settings['area'] })
          }
        />
      </div>
      <div className='grid gap-1.5'>
        <Label htmlFor='tpl-audit'>{t('inspections.audit')}</Label>
        <NativeSelect
          id='tpl-audit'
          options={[
            { value: '', label: t('inspections.not_audit') },
            { value: 'internal', label: t('inspections.internal_audit') },
            { value: 'external', label: t('inspections.external_audit') },
          ]}
          value={value.audit_scope ?? ''}
          onChange={(e) =>
            onChange({
              ...value,
              audit_scope: (e.target.value || null) as Settings['audit_scope'],
            })
          }
        />
      </div>
      <label className='flex items-center gap-2 text-sm'>
        <Checkbox
          checked={!!value.is_formal}
          onCheckedChange={(v) => onChange({ ...value, is_formal: v === true })}
        />
        {t('inspections.formal')}
      </label>
      <label className='flex items-center gap-2 text-sm'>
        <Checkbox
          checked={!!value.requires_client_signature}
          onCheckedChange={(v) =>
            onChange({ ...value, requires_client_signature: v === true })
          }
        />
        {t('inspections.requires_client_signature')}
      </label>
      <div className='grid gap-1.5'>
        <Label htmlFor='tpl-qualification'>
          {t('inspections.required_qualification')}
        </Label>
        <Input
          id='tpl-qualification'
          value={value.required_qualification ?? ''}
          onChange={(e) =>
            onChange({
              ...value,
              required_qualification: e.target.value || null,
            })
          }
        />
      </div>
      <p className='text-xs text-muted-foreground sm:col-span-3'>
        {value.is_formal
          ? t('inspections.formal_help')
          : t('inspections.informal_help')}
      </p>
    </div>
  )
}
