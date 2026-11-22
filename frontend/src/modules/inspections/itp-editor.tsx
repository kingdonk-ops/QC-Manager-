import { useState } from 'react'
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import {
  type Template,
  type TemplateBody,
  useSaveTemplate,
  useTemplates,
} from './api'
import { AREAS, type Activity, PARTIES, POINTS, pointTone } from './quality-api'

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

const blankActivity = (): Activity => ({
  title: '',
  verifying_document: null,
  form_template_id: null,
  acceptance_criteria: null,
  spec_ref: null,
  required_qualification: null,
  points: { contractor: 'none', client: 'none', third_party: 'none' },
})

/** An ITP: ordered activities, each with its ITR form and a Hold/Witness/Review/Surveillance point per party. */
export function ItpEditor({
  projectId,
  template,
  onSaved,
}: {
  projectId: number
  template: Template | null
  onSaved: (t: Template) => void
}) {
  const { t } = useTranslation()
  const save = useSaveTemplate(projectId)
  const { data: templates = [] } = useTemplates(projectId)
  const forms = templates.filter((x) => x.kind !== 'itp' && x.is_formal)
  const [head, setHead] = useState({
    name: template?.name ?? '',
    trade: template?.trade ?? '',
    work_type: template?.work_type ?? '',
    item_type_key: template?.item_type_key ?? '',
    client_document_number: template?.client_document_number ?? '',
  })
  const [activities, setActivities] = useState<Activity[]>(
    template?.activities?.length ? template.activities : [blankActivity()]
  )
  const set = (i: number, patch: Partial<Activity>) =>
    setActivities(activities.map((a, j) => (j === i ? { ...a, ...patch } : a)))
  const move = (i: number, delta: number) => {
    const j = i + delta
    if (j < 0 || j >= activities.length) return
    const next = [...activities]
    ;[next[i], next[j]] = [next[j], next[i]]
    setActivities(next)
  }

  return (
    <form
      className='grid gap-4'
      onSubmit={(e) => {
        e.preventDefault()
        const body = {
          project_id: projectId,
          kind: 'itp' as const,
          name: head.name,
          trade: head.trade || null,
          work_type: head.work_type || null,
          item_type_key: head.item_type_key || null,
          client_document_number: head.client_document_number || null,
          activities: activities.filter((a) => a.title.trim()),
          area: 'qa_itp' as const,
          is_formal: true,
          linked_issue_types: template?.linked_issue_types ?? [],
          requires_client_signature: false,
          active: true,
          sections: [],
        }
        save.mutate(
          {
            id: template?.id,
            body,
          },
          {
            onSuccess: (saved) => {
              toast.success(t('inspections.template_saved'))
              onSaved(saved as Template)
            },
          }
        )
      }}
    >
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-name'>{t('inspections.template_name')}</Label>
          <Input
            id='itp-name'
            required
            value={head.name}
            onChange={(e) => setHead({ ...head, name: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-doc'>
            {t('inspections.client_document_number')}
          </Label>
          <Input
            id='itp-doc'
            value={head.client_document_number}
            onChange={(e) =>
              setHead({ ...head, client_document_number: e.target.value })
            }
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-work'>{t('inspections.work_type')}</Label>
          <Input
            id='itp-work'
            placeholder='Blast & paint'
            value={head.work_type}
            onChange={(e) => setHead({ ...head, work_type: e.target.value })}
          />
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='itp-type'>{t('inspections.item_type')}</Label>
          <Input
            id='itp-type'
            placeholder='pipe_spool'
            value={head.item_type_key}
            onChange={(e) =>
              setHead({ ...head, item_type_key: e.target.value })
            }
          />
        </div>
      </div>

      <div className='overflow-x-auto'>
        <table className='w-full min-w-[860px] text-sm'>
          <thead>
            <tr className='border-b text-start text-xs text-muted-foreground'>
              <th className='p-1 text-start'>#</th>
              <th className='p-1 text-start'>{t('inspections.activity')}</th>
              {PARTIES.map((p) => (
                <th key={p} className='p-1 text-center'>
                  {t(`inspections.party.${p}`)}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {activities.map((a, i) => (
              <tr key={i} className='border-b align-top'>
                <td className='p-1 pt-3 font-mono text-xs'>{i + 1}</td>
                <td className='grid gap-1 p-1'>
                  <Input
                    aria-label={t('inspections.activity')}
                    placeholder={t('inspections.activity')}
                    value={a.title}
                    onChange={(e) => set(i, { title: e.target.value })}
                  />
                  <div className='grid gap-1 sm:grid-cols-2'>
                    <NativeSelect
                      aria-label={t('inspections.itr_form')}
                      placeholder={t('inspections.itr_form')}
                      options={forms.map((f) => ({
                        value: String(f.id),
                        label: f.name,
                      }))}
                      value={
                        a.form_template_id ? String(a.form_template_id) : ''
                      }
                      onChange={(e) =>
                        set(i, {
                          form_template_id: e.target.value
                            ? Number(e.target.value)
                            : null,
                        })
                      }
                    />
                    <Input
                      aria-label={t('inspections.verifying_document')}
                      placeholder={t('inspections.verifying_document')}
                      value={a.verifying_document ?? ''}
                      onChange={(e) =>
                        set(i, { verifying_document: e.target.value || null })
                      }
                    />
                    <Input
                      aria-label={t('inspections.spec_ref')}
                      placeholder={t('inspections.spec_ref')}
                      value={a.spec_ref ?? ''}
                      onChange={(e) =>
                        set(i, { spec_ref: e.target.value || null })
                      }
                    />
                    <Input
                      aria-label={t('inspections.required_qualification')}
                      placeholder={t('inspections.required_qualification')}
                      value={a.required_qualification ?? ''}
                      onChange={(e) =>
                        set(i, {
                          required_qualification: e.target.value || null,
                        })
                      }
                    />
                  </div>
                  <Textarea
                    aria-label={t('inspections.acceptance')}
                    placeholder={t('inspections.acceptance')}
                    className='min-h-9'
                    value={a.acceptance_criteria ?? ''}
                    onChange={(e) =>
                      set(i, { acceptance_criteria: e.target.value || null })
                    }
                  />
                </td>
                {PARTIES.map((p) => {
                  const current = a.points?.[p] ?? 'none'
                  return (
                    <td key={p} className='p-1 text-center'>
                      <div
                        className='inline-flex gap-0.5'
                        role='radiogroup'
                        aria-label={t(`inspections.party.${p}`)}
                      >
                        {POINTS.map((pt) => (
                          <button
                            key={pt}
                            type='button'
                            role='radio'
                            aria-checked={current === pt}
                            title={t(`inspections.point.${pt}`)}
                            onClick={() =>
                              set(i, {
                                points: { ...a.points, [p]: pt },
                              })
                            }
                            className={`h-7 w-7 rounded text-xs font-semibold ${
                              current === pt
                                ? pointTone(pt)
                                : 'border text-muted-foreground'
                            }`}
                          >
                            {pt === 'none' ? '–' : pt}
                          </button>
                        ))}
                      </div>
                    </td>
                  )
                })}
                <td className='p-1'>
                  <div className='flex flex-col gap-0.5'>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      aria-label={t('inspections.move_up')}
                      onClick={() => move(i, -1)}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      aria-label={t('inspections.move_down')}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      type='button'
                      size='icon'
                      variant='ghost'
                      aria-label={t('inspections.delete')}
                      onClick={() =>
                        setActivities(activities.filter((_, j) => j !== i))
                      }
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className='text-xs text-muted-foreground'>
        {t('inspections.points_legend')}
      </p>
      <div className='flex flex-wrap gap-2'>
        <Button
          type='button'
          variant='outline'
          onClick={() => setActivities([...activities, blankActivity()])}
        >
          <Plus /> {t('inspections.add_activity')}
        </Button>
        <Button type='submit' className='ms-auto' disabled={save.isPending}>
          <Save /> {t('common.save')}
        </Button>
      </div>
    </form>
  )
}
