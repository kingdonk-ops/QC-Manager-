import { useState } from 'react'
import { Download, FileCheck2, PenLine, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
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
import { StatusBadge } from '@/components/records/status-badge'
import {
  type Dossier,
  type Revision,
  downloadUrl,
  useDecide,
  useRevisions,
  useSign,
  useVerifyHash,
} from './api'
import { sha256Hex } from './lib'

const INTENT =
  'I confirm that this dossier revision is complete and correct to the best of my knowledge, and I sign it on behalf of the contractor.'

function SignDialog({
  revision,
  onClose,
}: {
  revision: Revision
  onClose: () => void
}) {
  const { t } = useTranslation()
  const sign = useSign()
  const [confirmed, setConfirmed] = useState(false)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {t('mdr.sign_title', { rev: revision.revision })}
          </DialogTitle>
          <DialogDescription>{t('mdr.sign_hint')}</DialogDescription>
        </DialogHeader>
        <label className='flex items-start gap-2 text-sm'>
          <Checkbox
            checked={confirmed}
            onCheckedChange={(on) => setConfirmed(Boolean(on))}
          />
          {INTENT}
        </label>
        <DialogFooter>
          <Button
            disabled={!confirmed || sign.isPending}
            onClick={() => sign.mutate(revision.id, { onSuccess: onClose })}
          >
            <PenLine /> {t('mdr.sign')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The dossier's revisions with sign, accept and reject actions, and the copy check. */
export function Revisions({ dossier }: { dossier: Dossier }) {
  const { t } = useTranslation()
  const session = useSession()
  const { data: revisions = [] } = useRevisions(dossier.id)
  const decide = useDecide()
  const verify = useVerifyHash(dossier.id)
  const [signing, setSigning] = useState<Revision | null>(null)
  const [hash, setHash] = useState<string | null>(null)
  return (
    <div className='grid gap-3'>
      <ul className='grid gap-2'>
        {revisions.map((r) => (
          <li key={r.id} className='grid gap-1 rounded-md border p-2 text-sm'>
            <div className='flex flex-wrap items-center gap-2'>
              <span className='font-medium'>
                {r.revision ? `Rev ${r.revision}` : t('mdr.draft')}
              </span>
              <Badge variant='outline'>{r.kind}</Badge>
              <StatusBadge status={r.status} />
              <span className='text-xs text-muted-foreground'>
                {t('mdr.pages', { count: r.page_count })}
              </span>
              <Button size='sm' variant='ghost' className='ms-auto' asChild>
                <a href={downloadUrl(r.id)}>
                  <Download /> {t('mdr.download')}
                </a>
              </Button>
            </div>
            {r.sha256 ? (
              <div className='font-mono text-xs break-all text-muted-foreground'>
                SHA-256 {r.sha256}
              </div>
            ) : null}
            <div className='text-xs text-muted-foreground'>
              {[
                r.compiled_by_name &&
                  t('mdr.compiled_by', { name: r.compiled_by_name }),
                r.signed_by_name &&
                  t('mdr.signed_by', {
                    name: r.signed_by_name,
                    at: r.signed_at
                      ? new Date(r.signed_at).toLocaleString()
                      : '',
                  }),
                r.decided_by_name &&
                  t('mdr.decided_by', {
                    name: r.decided_by_name,
                    decision: r.status,
                  }),
              ]
                .filter(Boolean)
                .join(' · ')}
            </div>
            <div className='flex flex-wrap gap-2'>
              {r.status === 'pending_signature' && can(session, 'mdr.sign') ? (
                <Button size='sm' onClick={() => setSigning(r)}>
                  <PenLine /> {t('mdr.sign')}
                </Button>
              ) : null}
              {r.kind === 'review' &&
              r.status === 'issued' &&
              can(session, 'mdr.accept') ? (
                <>
                  <Button
                    size='sm'
                    onClick={() =>
                      decide.mutate({ revisionId: r.id, decision: 'accepted' })
                    }
                  >
                    <FileCheck2 /> {t('mdr.accept')}
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => {
                      const note = window.prompt(t('mdr.reject_note'))
                      if (note !== null)
                        decide.mutate({
                          revisionId: r.id,
                          decision: 'rejected',
                          note,
                        })
                    }}
                  >
                    {t('mdr.reject')}
                  </Button>
                </>
              ) : null}
            </div>
          </li>
        ))}
        {!revisions.length ? (
          <p className='text-sm text-muted-foreground'>
            {t('mdr.no_revisions')}
          </p>
        ) : null}
      </ul>
      <section className='grid gap-1 rounded-md border p-2'>
        <Label htmlFor='hash-check' className='flex items-center gap-1'>
          <ShieldCheck className='size-4' /> {t('mdr.check_copy')}
        </Label>
        <p className='text-xs text-muted-foreground'>
          {t('mdr.check_copy_hint')}
        </p>
        <Input
          id='hash-check'
          type='file'
          accept='application/pdf'
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return
            const sha = await sha256Hex(await file.arrayBuffer())
            setHash(sha)
            verify.mutate(sha)
          }}
        />
        {hash && verify.data ? (
          <p
            className={
              verify.data.match
                ? 'text-sm text-green-700 dark:text-green-400'
                : 'text-sm text-red-600'
            }
          >
            {verify.data.match
              ? t('mdr.copy_matches', {
                  rev: verify.data.revision ?? t('mdr.draft'),
                  signed: verify.data.signed
                    ? t('mdr.signed')
                    : t('mdr.unsigned'),
                })
              : t('mdr.copy_differs')}
          </p>
        ) : null}
      </section>
      {signing ? (
        <SignDialog revision={signing} onClose={() => setSigning(null)} />
      ) : null}
    </div>
  )
}
