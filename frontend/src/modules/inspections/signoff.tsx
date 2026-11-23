/**
 * Signing, client co-sign, submit and review for one inspection record.
 */
import { useState } from 'react'
import {
  CheckCircle2,
  FileSignature,
  Lock,
  PenLine,
  Send,
  ShieldCheck,
  Unlock,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { type Inspection } from './api'
import {
  type Signature,
  formatWhen,
  pointTone,
  useDecideCosign,
  useSign,
} from './quality-api'
import {
  CosignDialog,
  HoldReleaseDialog,
  Intent,
  ReviewDialog,
  SubmitDialog,
} from './signoff-dialogs'

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
