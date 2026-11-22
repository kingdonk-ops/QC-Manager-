/**
 * Signing, client co-sign, submit and review for one inspection record.
 */
import { useEffect, useRef, useState } from 'react'
import {
  CheckCircle2,
  FileSignature,
  Lock,
  PenLine,
  Send,
  ShieldCheck,
  Undo2,
  Unlock,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import {
  type Finding,
  type Signature,
  formatWhen,
  pointTone,
  useCosign,
  useDecideCosign,
  useEligibility,
  useHoldRelease,
  useReview,
  useSign,
  useSubmit,
} from './quality-api'

const SIG_TONE: Record<string, string> = {
  valid: 'bg-green-600 text-white',
  provisional: 'bg-amber-500 text-white',
  void: 'bg-muted text-muted-foreground line-through',
  rejected: 'bg-red-600 text-white',
}

export function PointBadges({ points }: { points: Record<string, string> }) {
  const { t } = useTranslation()
  const shown = Object.entries(points ?? {}).filter(([, v]) => v !== 'none')
  if (!shown.length) return <span className='text-muted-foreground'>—</span>
  return (
    <span className='flex flex-wrap gap-1'>
      {shown.map(([party, point]) => (
        <span
          key={party}
          title={t(`inspections.party.${party}`)}
          className={`rounded px-1.5 py-0.5 text-xs font-semibold ${pointTone(point)}`}
        >
          {t(`inspections.party_short.${party}`)} {point}
        </span>
      ))}
    </span>
  )
}

function Findings({ findings }: { findings: Finding[] }) {
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

function Intent({
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

function SignatureRow({
  sig,
  inspection,
}: {
  sig: Signature
  inspection: Inspection
}) {
  const { t } = useTranslation()
  const session = useSession()
  const decide = useDecideCosign(inspection.id)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [accept, setAccept] = useState(false)
  const mine =
    sig.status === 'provisional' &&
    sig.signer_user_id === session.id &&
    can(session, 'inspections.respond')
  const name =
    (sig.signer_snapshot as { name?: string }).name ??
    sig.signer_name_stated ??
    '—'
  return (
    <li className='grid gap-1 rounded-md border p-2 text-sm'>
      <div className='flex flex-wrap items-center gap-2'>
        <span className='font-medium'>{t(`inspections.role.${sig.role}`)}</span>
        <span>{name}</span>
        {sig.mode ? (
          <Badge variant='outline'>{t(`inspections.mode.${sig.mode}`)}</Badge>
        ) : null}
        <span
          className={`rounded px-1.5 py-0.5 text-xs ${SIG_TONE[sig.status] ?? ''}`}
        >
          {sig.status === 'provisional'
            ? t('inspections.provisional_client')
            : t(`inspections.sig_status.${sig.status}`)}
        </span>
        <span className='ms-auto text-xs text-muted-foreground'>
          {formatWhen(sig.signed_at)}
        </span>
      </div>
      <p className='font-mono text-[11px] text-muted-foreground'>
        SHA-256 {sig.content_sha256.slice(0, 16)}…
        {sig.on_behalf_of_user_id
          ? ` · ${t('inspections.on_behalf')} #${sig.on_behalf_of_user_id}`
          : ''}
      </p>
      {sig.competency_snapshot.length ? (
        <p className='text-xs text-muted-foreground'>
          {sig.competency_snapshot
            .map(
              (c) =>
                `${String(c.qualification)} → ${String(c.expires_on ?? '∞')}`
            )
            .join(' · ')}
        </p>
      ) : null}
      {sig.void_reason ? (
        <p className='text-xs text-muted-foreground'>{sig.void_reason}</p>
      ) : null}
      {sig.rejected_reason ? (
        <p className='text-xs text-red-600'>{sig.rejected_reason}</p>
      ) : null}
      {mine ? (
        <div className='grid gap-2 pt-1'>
          <Intent
            text={t('inspections.cosign_confirm_intent', {
              code: inspection.code,
            })}
            accepted={accept}
            onChange={setAccept}
          />
          {rejecting ? (
            <Textarea
              placeholder={t('inspections.reject_reason')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          ) : null}
          <div className='flex gap-2'>
            <Button
              size='sm'
              disabled={!accept || decide.isPending}
              onClick={() =>
                decide.mutate({
                  signatureId: sig.id,
                  body: { decision: 'confirm', accept_intent: true },
                })
              }
            >
              <CheckCircle2 /> {t('inspections.confirm_signature')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              disabled={decide.isPending || (rejecting && !reason.trim())}
              onClick={() =>
                rejecting
                  ? decide.mutate({
                      signatureId: sig.id,
                      body: {
                        decision: 'reject',
                        reason,
                        accept_intent: false,
                      },
                    })
                  : setRejecting(true)
              }
            >
              {t('inspections.reject_signature')}
            </Button>
          </div>
        </div>
      ) : null}
    </li>
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

function CosignDialog({
  inspection,
  onClose,
}: {
  inspection: Inspection
  onClose: () => void
}) {
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

function SubmitDialog({
  inspection,
  onClose,
}: {
  inspection: Inspection
  onClose: () => void
}) {
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

function ReviewDialog({
  inspection,
  onClose,
}: {
  inspection: Inspection
  onClose: () => void
}) {
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

function HoldReleaseDialog({
  inspection,
  onClose,
}: {
  inspection: Inspection
  onClose: () => void
}) {
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

/** Signatures, the review state and the actions the caller may take on a formal record or ITP line. */
export function SignOffPanel({ inspection }: { inspection: Inspection }) {
  const { t } = useTranslation()
  const session = useSession()
  const sign = useSign(inspection.id)
  const [dialog, setDialog] = useState<
    'cosign' | 'submit' | 'review' | 'hold' | null
  >(null)
  const editable = ['planned', 'requested', 'in_progress', 'returned'].includes(
    inspection.status
  )
  const live = inspection.signatures.filter((s) =>
    ['valid', 'provisional'].includes(s.status)
  )
  const inspectorSigned = live.some((s) => s.role === 'inspector')
  const clientSigned = live.some((s) => s.role === 'client')
  const hasHold = Object.values(inspection.points ?? {}).includes('H')

  return (
    <Card>
      <CardHeader className='flex flex-row flex-wrap items-center gap-2'>
        <CardTitle className='flex items-center gap-2 text-base'>
          <FileSignature className='size-4' /> {t('inspections.signoff')}
        </CardTitle>
        {inspection.review_round ? (
          <Badge variant='secondary'>
            {t('inspections.round')} {inspection.review_round}
          </Badge>
        ) : null}
        {inspection.result ? (
          <Badge
            className={
              inspection.result === 'pass' ? 'bg-green-600' : 'bg-red-600'
            }
          >
            {inspection.result === 'pass'
              ? t('inspections.accepted')
              : t('inspections.rejected')}
          </Badge>
        ) : null}
        {inspection.self_approved ? (
          <Badge variant='outline'>{t('inspections.self_approved')}</Badge>
        ) : null}
        {hasHold ? (
          inspection.hold_released_at ? (
            <Badge variant='outline' className='gap-1'>
              <Unlock className='size-3' /> {t('inspections.hold_released')}
            </Badge>
          ) : (
            <Badge variant='outline' className='gap-1 text-red-600'>
              <Lock className='size-3' /> {t('inspections.hold_open')}
            </Badge>
          )
        ) : null}
      </CardHeader>
      <CardContent className='grid gap-3'>
        {inspection.return_reason ? (
          <p className='rounded-md border border-amber-500 p-2 text-sm'>
            <strong>{t('inspections.returned_because')}</strong>{' '}
            {inspection.return_reason}
          </p>
        ) : null}
        {inspection.signatures.length ? (
          <ul className='grid gap-2'>
            {inspection.signatures.map((s) => (
              <SignatureRow key={s.id} sig={s} inspection={inspection} />
            ))}
          </ul>
        ) : (
          <p className='text-sm text-muted-foreground'>
            {t('inspections.not_signed')}
          </p>
        )}
        <div className='flex flex-wrap gap-2'>
          {editable &&
          !inspectorSigned &&
          inspection.status !== 'planned' &&
          can(session, 'inspections.submit') ? (
            <Button
              size='sm'
              variant='outline'
              disabled={sign.isPending}
              onClick={() =>
                sign.mutate(undefined, {
                  onSuccess: () => toast.success(t('inspections.signed')),
                })
              }
            >
              <PenLine /> {t('inspections.sign')}
            </Button>
          ) : null}
          {inspectorSigned &&
          !clientSigned &&
          inspection.status !== 'completed' &&
          inspection.status !== 'closed' ? (
            <Button
              size='sm'
              variant='outline'
              onClick={() => setDialog('cosign')}
            >
              <PenLine /> {t('inspections.client_cosign')}
            </Button>
          ) : null}
          {inspection.is_formal &&
          editable &&
          can(session, 'inspections.submit') ? (
            <Button size='sm' onClick={() => setDialog('submit')}>
              <Send /> {t('inspections.submit')}
            </Button>
          ) : null}
          {inspection.status === 'submitted' &&
          can(session, 'inspections.review') ? (
            <Button size='sm' onClick={() => setDialog('review')}>
              <ShieldCheck /> {t('inspections.review')}
            </Button>
          ) : null}
          {hasHold &&
          !inspection.hold_released_at &&
          inspection.result === 'pass' &&
          can(session, 'inspections.approve') ? (
            <Button size='sm' onClick={() => setDialog('hold')}>
              <Unlock /> {t('inspections.release_hold')}
            </Button>
          ) : null}
        </div>
      </CardContent>
      {dialog === 'cosign' ? (
        <CosignDialog inspection={inspection} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === 'submit' ? (
        <SubmitDialog inspection={inspection} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === 'review' ? (
        <ReviewDialog inspection={inspection} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === 'hold' ? (
        <HoldReleaseDialog
          inspection={inspection}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </Card>
  )
}
