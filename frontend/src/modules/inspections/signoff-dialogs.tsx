/**
 * The dialogs of the sign-off panel: client co-sign, submit, review and hold release, with the signature pad
 * and the findings and intent pieces they share.
 */
import { useEffect, useRef, useState } from 'react'
import { PenLine, Send, ShieldCheck, Undo2, Unlock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
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
import { NativeSelect, UserSelect } from '@/components/native-select'
import { uploadFile } from '@/components/records/files'
import { type Inspection } from './api'
import { OutcomeFields } from './outcome-fields'
import { NO_OUTCOME, outcomeBody } from './outcome-state'
import {
  type Finding,
  useCosign,
  useEligibility,
  useHoldRelease,
  useReview,
  useSubmit,
} from './quality-api'

export function Findings({ findings }: { findings: Finding[] }) {
  if (!findings.length) return null
  return (
    <ul className='grid gap-1 text-sm'>
      {findings.map((f) => (
        <li
          key={f.code}
          className={f.blocking ? 'text-red-600' : 'text-amber-600'}
        >
          <span className='font-mono text-xs'>{f.code}</span> {f.message}
        </li>
      ))}
    </ul>
  )
}

export function Intent({
  text,
  accepted,
  onChange,
}: {
  text: string
  accepted: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className='flex items-start gap-2 rounded-md border bg-muted/40 p-3 text-sm'>
      <Checkbox
        checked={accepted}
        onCheckedChange={(v) => onChange(v === true)}
        className='mt-0.5'
      />
      <span>{text}</span>
    </label>
  )
}

/** A small canvas to draw a signature on (mouse, pen or finger). */
function SignaturePad({ onChange }: { onChange: (dataUrl: string) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (ctx) {
      ctx.lineWidth = 2
      ctx.lineCap = 'round'
      ctx.strokeStyle = '#111'
    }
  }, [])
  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    return [
      ((e.clientX - r.left) * e.currentTarget.width) / r.width,
      ((e.clientY - r.top) * e.currentTarget.height) / r.height,
    ] as const
  }
  return (
    <canvas
      ref={ref}
      width={480}
      height={160}
      aria-label='Signature'
      className='w-full touch-none rounded-md border bg-white'
      onPointerDown={(e) => {
        drawing.current = true
        const ctx = e.currentTarget.getContext('2d')
        const [x, y] = point(e)
        ctx?.beginPath()
        ctx?.moveTo(x, y)
      }}
      onPointerMove={(e) => {
        if (!drawing.current) return
        const ctx = e.currentTarget.getContext('2d')
        const [x, y] = point(e)
        ctx?.lineTo(x, y)
        ctx?.stroke()
      }}
      onPointerUp={(e) => {
        drawing.current = false
        onChange(e.currentTarget.toDataURL('image/png'))
      }}
    />
  )
}

type DialogProps = { inspection: Inspection; onClose: () => void }

export function CosignDialog({ inspection, onClose }: DialogProps) {
  const { t } = useTranslation()
  const session = useSession()
  const cosign = useCosign(inspection.id)
  const isClient = can(session, 'inspections.respond')
  const [mode, setMode] = useState<'portal' | 'on_device' | 'scan'>(
    isClient ? 'portal' : 'on_device'
  )
  const [clientId, setClientId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [image, setImage] = useState('')
  const [scan, setScan] = useState<File | null>(null)
  const [accept, setAccept] = useState(false)
  const ready =
    mode === 'portal'
      ? accept
      : !!clientId && (mode === 'on_device' ? !!image : !!scan)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{t('inspections.client_cosign')}</DialogTitle>
          <DialogDescription>{t('inspections.cosign_help')}</DialogDescription>
        </DialogHeader>
        <NativeSelect
          aria-label={t('inspections.cosign_mode')}
          options={[
            ...(isClient
              ? [{ value: 'portal', label: t('inspections.mode.portal') }]
              : []),
            { value: 'on_device', label: t('inspections.mode.on_device') },
            { value: 'scan', label: t('inspections.mode.scan') },
          ]}
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        />
        {mode === 'portal' ? (
          <Intent
            text={t('inspections.cosign_intent', {
              name: session.name,
              code: inspection.code,
            })}
            accepted={accept}
            onChange={setAccept}
          />
        ) : (
          <div className='grid gap-3'>
            <div className='grid gap-1.5'>
              <Label>{t('inspections.client_account')}</Label>
              <UserSelect value={clientId} onChange={setClientId} />
            </div>
            <div className='grid gap-1.5'>
              <Label htmlFor='cosign-name'>
                {t('inspections.signer_name')}
              </Label>
              <Input
                id='cosign-name'
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            {mode === 'on_device' ? (
              <SignaturePad onChange={setImage} />
            ) : (
              <Input
                type='file'
                accept='application/pdf,image/*'
                onChange={(e) => setScan(e.target.files?.[0] ?? null)}
              />
            )}
            <p className='text-xs text-amber-600'>
              {t('inspections.provisional_help')}
            </p>
          </div>
        )}
        <DialogFooter>
          <Button
            disabled={!ready || cosign.isPending}
            onClick={async () => {
              let scanId: number | null = null
              if (mode === 'scan' && scan) {
                const form = new FormData()
                form.append('project_id', String(inspection.project_id))
                form.append('entity_type', 'inspection')
                form.append('entity_id', String(inspection.id))
                form.append('file', scan)
                try {
                  scanId = (await uploadFile(form)).id
                } catch (error) {
                  toast.error((error as Error).message)
                  return
                }
              }
              cosign.mutate(
                mode === 'portal'
                  ? { mode, accept_intent: true }
                  : {
                      mode,
                      accept_intent: false,
                      client_user_id: clientId,
                      signer_name: name || null,
                      signature_image: mode === 'on_device' ? image : null,
                      scan_file_id: scanId,
                    },
                {
                  onSuccess: () => {
                    toast.success(t('inspections.cosigned'))
                    onClose()
                  },
                }
              )
            }}
          >
            <PenLine /> {t('inspections.cosign')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SubmitDialog({ inspection, onClose }: DialogProps) {
  const { t } = useTranslation()
  const session = useSession()
  const submit = useSubmit(inspection.id)
  const { data: check } = useEligibility(inspection.id, 'submit')
  const signed = inspection.signatures.some(
    (s) => s.role === 'inspector' && s.status === 'valid'
  )
  const [result, setResult] = useState<'pass' | 'fail'>(
    inspection.failed ? 'fail' : 'pass'
  )
  const [outcome, setOutcome] = useState(() => ({
    ...NO_OUTCOME,
    measured: inspection.measured_value ?? '',
  }))
  const [accept, setAccept] = useState(signed)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.submit_title')}</DialogTitle>
          <DialogDescription>{t('inspections.submit_help')}</DialogDescription>
        </DialogHeader>
        <NativeSelect
          aria-label={t('inspections.proposed_result')}
          options={[
            { value: 'pass', label: t('inspections.accept_result') },
            { value: 'fail', label: t('inspections.reject_result') },
          ]}
          value={result}
          onChange={(e) => setResult(e.target.value as 'pass' | 'fail')}
        />
        <OutcomeFields
          result={result}
          value={outcome}
          onChange={setOutcome}
          idPrefix='submit'
        />
        {check ? <Findings findings={check.findings} /> : null}
        {!signed ? (
          <Intent
            text={t('inspections.inspector_intent', {
              name: session.name,
              code: inspection.code,
            })}
            accepted={accept}
            onChange={setAccept}
          />
        ) : null}
        <DialogFooter>
          <Button
            disabled={!accept || submit.isPending}
            onClick={() =>
              submit.mutate(
                {
                  proposed_result: result,
                  accept_intent: true,
                  allow_unanswered: inspection.unanswered > 0,
                  ...outcomeBody(result, outcome),
                },
                { onSuccess: onClose }
              )
            }
          >
            <Send /> {t('inspections.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ReviewDialog({ inspection, onClose }: DialogProps) {
  const { t } = useTranslation()
  const session = useSession()
  const review = useReview(inspection.id)
  const { data: check } = useEligibility(inspection.id, 'approve')
  const [decision, setDecision] = useState<'approve' | 'return'>('approve')
  const [reason, setReason] = useState('')
  const [comments, setComments] = useState<Record<number, string>>({})
  const [accept, setAccept] = useState(false)
  const ok =
    decision === 'approve' ? accept && check?.eligible : !!reason.trim()
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>{t('inspections.review_title')}</DialogTitle>
          <DialogDescription>
            {t('inspections.proposed')}:{' '}
            <strong>
              {inspection.proposed_result === 'fail'
                ? t('inspections.reject_result')
                : t('inspections.accept_result')}
            </strong>
          </DialogDescription>
        </DialogHeader>
        <NativeSelect
          aria-label={t('inspections.decision')}
          options={[
            { value: 'approve', label: t('inspections.approve') },
            { value: 'return', label: t('inspections.return') },
          ]}
          value={decision}
          onChange={(e) => setDecision(e.target.value as typeof decision)}
        />
        {decision === 'approve' ? (
          <>
            {check ? <Findings findings={check.findings} /> : null}
            <Intent
              text={t('inspections.reviewer_intent', {
                name: session.name,
                code: inspection.code,
              })}
              accepted={accept}
              onChange={setAccept}
            />
          </>
        ) : (
          <div className='grid gap-3'>
            <Textarea
              aria-label={t('inspections.return_reason')}
              placeholder={t('inspections.return_reason')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            {inspection.items.map((item) => (
              <div key={item.id} className='grid gap-1'>
                <Label className='text-xs text-muted-foreground'>
                  {item.position}. {item.text}
                </Label>
                <Input
                  placeholder={t('inspections.comment_on_answer')}
                  value={comments[item.id] ?? ''}
                  onChange={(e) =>
                    setComments({ ...comments, [item.id]: e.target.value })
                  }
                />
              </div>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button
            disabled={!ok || review.isPending}
            variant={decision === 'return' ? 'outline' : 'default'}
            onClick={() =>
              review.mutate(
                decision === 'approve'
                  ? {
                      decision,
                      accept_intent: true,
                      comments: [],
                      follow_ups: [],
                    }
                  : {
                      decision,
                      reason,
                      accept_intent: false,
                      follow_ups: [],
                      comments: Object.entries(comments)
                        .filter(([, body]) => body.trim())
                        .map(([item_id, body]) => ({
                          item_id: Number(item_id),
                          body,
                        })),
                    },
                { onSuccess: onClose }
              )
            }
          >
            {decision === 'approve' ? <ShieldCheck /> : <Undo2 />}
            {decision === 'approve'
              ? t('inspections.approve')
              : t('inspections.return')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function HoldReleaseDialog({ inspection, onClose }: DialogProps) {
  const { t } = useTranslation()
  const session = useSession()
  const release = useHoldRelease(inspection.id)
  const { data: check } = useEligibility(inspection.id, 'hold_release')
  const [accept, setAccept] = useState(false)
  const [onBehalf, setOnBehalf] = useState<number | null>(null)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('inspections.release_hold')}</DialogTitle>
          <DialogDescription>
            {inspection.acceptance_criteria}
          </DialogDescription>
        </DialogHeader>
        {check ? <Findings findings={check.findings} /> : null}
        <div className='grid gap-1.5'>
          <Label>{t('inspections.on_behalf_of')}</Label>
          <UserSelect value={onBehalf} onChange={setOnBehalf} />
        </div>
        <Intent
          text={t('inspections.hold_intent', {
            name: session.name,
            code: inspection.code,
          })}
          accepted={accept}
          onChange={setAccept}
        />
        <DialogFooter>
          <Button
            disabled={!accept || !check?.eligible || release.isPending}
            onClick={() =>
              release.mutate(
                { accept_intent: true, on_behalf_of_user_id: onBehalf },
                { onSuccess: onClose }
              )
            }
          >
            <Unlock /> {t('inspections.release_hold')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
