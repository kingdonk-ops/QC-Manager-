import { useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/native-select'
import { CriterionPicker } from './criterion-picker'
import {
  ATTACHMENT_KINDS,
  AUTHORITIES,
  GATE_KINDS,
  attachmentPairValid,
  authoritySatisfies,
  canSubmitWaiver,
  defaultBlocking,
} from './gate-rules'
import {
  type Gate,
  type GateBody,
  useCreateGate,
  useGateAction,
} from './gates-api'

export type Attachment = { kind: string; id: number }

const authorityOptions = (t: TFunction) =>
  AUTHORITIES.map((a) => ({
    value: a,
    label: t(`inspections.gates.authority.${a}`),
  }))

/** Create a gate. With `attachment` the target is fixed (from a record's panel); otherwise it can be chosen. */
export function CreateGateDialog({
  projectId,
  attachment,
  onClose,
}: {
  projectId: number
  attachment?: Attachment
  onClose: () => void
}) {
  const { t } = useTranslation()
  const create = useCreateGate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [kind, setKind] = useState<(typeof GATE_KINDS)[number]>('hold')
  const [authority, setAuthority] =
    useState<(typeof AUTHORITIES)[number]>('contractor_qa')
  const [attachKind, setAttachKind] = useState(attachment?.kind ?? '')
  const [attachId, setAttachId] = useState(
    attachment ? String(attachment.id) : ''
  )
  const [packageRef, setPackageRef] = useState('')
  const [approvalRef, setApprovalRef] = useState('')
  const [criterionId, setCriterionId] = useState<number | null>(null)
  // null until toggled: the server then defaults the flag from the kind.
  const [blocks, setBlocks] = useState<boolean | null>(null)
  const pairOk = attachmentPairValid(attachKind, attachId)
  const blocking = blocks ?? defaultBlocking(kind)

  const submit = () => {
    const body: GateBody = {
      project_id: projectId,
      title: title.trim(),
      kind,
      authority,
      description: description.trim() || null,
      criterion_id: criterionId,
      attachment_kind: attachKind
        ? (attachKind as GateBody['attachment_kind'])
        : null,
      attachment_id: attachId ? Number(attachId) : null,
      package_ref: packageRef.trim() || null,
      approval_ref: approvalRef.trim() || null,
      supplementary: {},
      ...(blocks === null ? {} : { blocks_progress: blocks }),
    }
    create.mutate(body, {
      onSuccess: () => {
        toast.success(t('inspections.gates.created'))
        onClose()
      },
    })
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>{t('inspections.gates.new')}</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='gate-title'>{t('inspections.gates.title')}</Label>
            <Input
              id='gate-title'
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='gate-kind'>{t('inspections.gates.kind')}</Label>
              <NativeSelect
                id='gate-kind'
                options={GATE_KINDS.map((k) => ({
                  value: k,
                  label: t(`inspections.gates.kind.${k}`),
                }))}
                value={kind}
                onChange={(e) => setKind(e.target.value as typeof kind)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='gate-authority'>
                {t('inspections.gates.authority')}
              </Label>
              <NativeSelect
                id='gate-authority'
                options={authorityOptions(t)}
                value={authority}
                onChange={(e) =>
                  setAuthority(e.target.value as typeof authority)
                }
              />
            </div>
          </div>
          <label className='flex items-center gap-2 text-sm'>
            <Checkbox
              checked={blocking}
              onCheckedChange={(v) => setBlocks(v === true)}
            />
            {t('inspections.gates.blocks')}
          </label>
          {attachment ? null : (
            <div className='grid gap-3 sm:grid-cols-2'>
              <div className='grid gap-1.5'>
                <Label htmlFor='gate-attach-kind'>
                  {t('inspections.gates.attachment_kind')}
                </Label>
                <NativeSelect
                  id='gate-attach-kind'
                  placeholder={t('inspections.gates.none')}
                  options={ATTACHMENT_KINDS.map((k) => ({
                    value: k,
                    label: t(`inspections.gates.attachment.${k}`),
                  }))}
                  value={attachKind}
                  onChange={(e) => setAttachKind(e.target.value)}
                />
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='gate-attach-id'>
                  {t('inspections.gates.attachment_id')}
                </Label>
                <Input
                  id='gate-attach-id'
                  type='number'
                  min={1}
                  value={attachId}
                  onChange={(e) => setAttachId(e.target.value)}
                />
              </div>
              {pairOk ? null : (
                <p className='text-sm text-red-600 sm:col-span-2'>
                  {t('inspections.gates.attachment_pair')}
                </p>
              )}
            </div>
          )}
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='grid gap-1.5'>
              <Label htmlFor='gate-package'>
                {t('inspections.gates.package_ref')}
              </Label>
              <Input
                id='gate-package'
                value={packageRef}
                onChange={(e) => setPackageRef(e.target.value)}
              />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='gate-approval'>
                {t('inspections.gates.approval_ref')}
              </Label>
              <Input
                id='gate-approval'
                value={approvalRef}
                onChange={(e) => setApprovalRef(e.target.value)}
              />
            </div>
          </div>
          <div className='grid gap-1.5'>
            <Label>{t('inspections.gates.criterion')}</Label>
            <CriterionPicker
              projectId={projectId}
              value={criterionId}
              onChange={(c) => setCriterionId(c?.id ?? null)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='gate-details'>
              {t('inspections.gates.details')}
            </Label>
            <Textarea
              id='gate-details'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!title.trim() || !pairOk || create.isPending}
            onClick={submit}
          >
            {t('inspections.gates.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Release a pending gate under an asserted authority level. The server checks it against the requirement. */
export function ReleaseDialog({
  gate,
  onClose,
}: {
  gate: Gate
  onClose: () => void
}) {
  const { t } = useTranslation()
  const act = useGateAction()
  const [authority, setAuthority] = useState<(typeof AUTHORITIES)[number]>(
    (AUTHORITIES as readonly string[]).includes(gate.authority)
      ? (gate.authority as (typeof AUTHORITIES)[number])
      : 'contractor_qa'
  )
  const [justification, setJustification] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('inspections.gates.release_title', { number: gate.number })}
          </DialogTitle>
          <DialogDescription>
            {t('inspections.gates.release_help')}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-1.5'>
          <Label htmlFor='release-authority'>
            {t('inspections.gates.asserted')}
          </Label>
          <NativeSelect
            id='release-authority'
            options={authorityOptions(t)}
            value={authority}
            onChange={(e) => setAuthority(e.target.value as typeof authority)}
          />
          {authoritySatisfies(authority, gate.authority) ? null : (
            <p className='text-xs text-amber-600'>
              {t('inspections.gates.below_required')}
            </p>
          )}
        </div>
        <div className='grid gap-1.5'>
          <Label htmlFor='release-justification'>
            {t('inspections.gates.justification')}
          </Label>
          <Textarea
            id='release-justification'
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={act.isPending}
            onClick={() =>
              act.mutate(
                {
                  id: gate.id,
                  action: 'release',
                  body: {
                    authority,
                    justification: justification.trim() || null,
                  },
                },
                {
                  onSuccess: () => {
                    toast.success(t('inspections.gates.released'))
                    onClose()
                  },
                }
              )
            }
          >
            {t('inspections.gates.release')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The reason box and button of a waiver: the button stays disabled until a reason is typed. */
export function WaiveForm({
  pending,
  onSubmit,
}: {
  pending?: boolean
  onSubmit: (reason: string) => void
}) {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  return (
    <>
      <div className='grid gap-1.5'>
        <Label htmlFor='waive-reason'>{t('inspections.gates.reason')}</Label>
        <Textarea
          id='waive-reason'
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      <DialogFooter>
        <Button
          data-testid='waive-submit'
          disabled={!canSubmitWaiver(reason) || pending}
          onClick={() => onSubmit(reason.trim())}
        >
          {t('inspections.gates.waive')}
        </Button>
      </DialogFooter>
    </>
  )
}

export function WaiveDialog({
  gate,
  onClose,
}: {
  gate: Gate
  onClose: () => void
}) {
  const { t } = useTranslation()
  const act = useGateAction()
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('inspections.gates.waive_title', { number: gate.number })}
          </DialogTitle>
          <DialogDescription>
            {t('inspections.gates.waive_help')}
          </DialogDescription>
        </DialogHeader>
        <WaiveForm
          pending={act.isPending}
          onSubmit={(reason) =>
            act.mutate(
              { id: gate.id, action: 'waive', body: { reason } },
              {
                onSuccess: () => {
                  toast.success(t('inspections.gates.waived'))
                  onClose()
                },
              }
            )
          }
        />
      </DialogContent>
    </Dialog>
  )
}
