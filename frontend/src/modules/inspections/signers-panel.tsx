/**
 * Distinct signers on an ITP line: the signers panel of the sign-off screen, the collected-over-required note on the
 * ITP instance page and the required count field of the ITP editor. Every number shown comes from the server.
 */
import { useId, useState } from 'react'
import { PenLine, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { can, useSession } from '@/lib/session'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type Inspection } from './api'
import { AdditionalSignatoryDialog } from './countersign-dialog'
import {
  REQUIRED_MAX,
  REQUIRED_MIN,
  type SignatoryStatus,
  parseRequired,
  refusalText,
  useAddSignatory,
  useSignatories,
} from './signatories-api'

/** The server's answer for one line: collected over required, who signed in which roles, and the add action. */
export function SignersView({
  status,
  canAdd,
  onAdd,
}: {
  status: SignatoryStatus
  canAdd: boolean
  onAdd: () => void
}) {
  const { t } = useTranslation()
  // A requirement of one is the default: keep the panel to a single quiet line.
  const compact = status.required <= 1
  return (
    <div
      data-testid='signers-panel'
      className='grid gap-2 rounded-md border p-2 text-sm'
    >
      <div className='flex flex-wrap items-center gap-2'>
        <span className='flex items-center gap-1 font-medium'>
          <Users className='size-4' /> {t('inspections.signers.title')}
        </span>
        <span
          data-testid='signers-count'
          data-collected={status.collected}
          data-required={status.required}
        >
          {t('inspections.signers.count', {
            collected: status.collected,
            required: status.required,
          })}
        </span>
        {compact && status.met ? null : (
          <Badge
            variant='outline'
            data-testid='signers-met'
            data-met={status.met ? 'true' : 'false'}
            className={status.met ? 'text-green-700' : 'text-amber-700'}
          >
            {status.met
              ? t('inspections.signers.met')
              : t('inspections.signers.not_met')}
          </Badge>
        )}
        {canAdd ? (
          <Button
            data-testid='signer-add'
            size='sm'
            variant='outline'
            className='ms-auto'
            onClick={onAdd}
          >
            <PenLine /> {t('inspections.signers.add')}
          </Button>
        ) : null}
      </div>
      {compact ? null : status.signers.length ? (
        <ul className='grid gap-1'>
          {status.signers.map((p) => (
            <li
              key={p.user_id}
              data-testid='signer-row'
              className='flex flex-wrap items-center gap-2'
            >
              <span>{p.name ?? t('inspections.signers.unnamed')}</span>
              {p.roles.map((r) => (
                <Badge key={r} variant='secondary'>
                  {t(`inspections.role.${r}`)}
                </Badge>
              ))}
            </li>
          ))}
        </ul>
      ) : (
        <p className='text-muted-foreground'>{t('inspections.signers.none')}</p>
      )}
    </div>
  )
}

const OPEN_STATUSES = ['requested', 'in_progress', 'submitted', 'returned']

/** The signers panel of an ITP line's sign-off card; nothing for a record that is not an ITP line. */
export function SignersPanel({ inspection }: { inspection: Inspection }) {
  const session = useSession()
  const isLine = inspection.itp_instance_id != null
  const { data: status } = useSignatories(inspection.id, isLine)
  const add = useAddSignatory(inspection.id)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!isLine || !status) return null
  const inspectorSigned = inspection.signatures.some(
    (s) => s.role === 'inspector' && ['valid', 'provisional'].includes(s.status)
  )
  // Only a convenience: the server decides, and its refusal is shown in the dialog.
  const canAdd =
    can(session, 'inspections.submit') &&
    inspectorSigned &&
    OPEN_STATUSES.includes(inspection.status)
  return (
    <>
      <SignersView
        status={status}
        canAdd={canAdd}
        onAdd={() => {
          setError(null)
          setOpen(true)
        }}
      />
      {open ? (
        <AdditionalSignatoryDialog
          name={session.name}
          code={inspection.code}
          pending={add.isPending}
          error={error}
          onClose={() => setOpen(false)}
          onSubmit={() =>
            add.mutate(undefined, {
              onSuccess: () => setOpen(false),
              onError: (e) => setError(refusalText(e)),
            })
          }
        />
      ) : null}
    </>
  )
}

/** Collected over required beside a line of the ITP instance page; shown only when more than one is required. */
export function LineSignerCount({
  required,
  collected,
}: {
  required: number
  collected: number
}) {
  const { t } = useTranslation()
  if (required <= 1) return null
  return (
    <span
      data-testid='line-signers'
      data-collected={collected}
      data-required={required}
      className='flex items-center gap-1 text-muted-foreground'
    >
      <Users className='size-3' />{' '}
      {t('inspections.signers.line_count', { collected, required })}
    </span>
  )
}

/** The required signatory count of one ITP activity: 1 to 10, empty meaning 1; a bad value is flagged and not sent. */
export function RequiredField({
  value,
  onChange,
}: {
  value: number
  onChange: (n: number) => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(String(value))
  const [seen, setSeen] = useState(value)
  const typed = text.trim() === '' ? REQUIRED_MIN : parseRequired(text)
  // The row may move or reload: follow the value when it changes from outside what was typed.
  if (value !== seen) {
    setSeen(value)
    if (typed !== value) setText(String(value))
  }
  const valid = typed !== null
  const id = useId()
  const helpId = `${id}-help`
  const errorId = `${id}-error`
  return (
    <div className='grid gap-1'>
      <Label htmlFor={id} className='text-xs'>
        {t('inspections.signers.required_field')}
      </Label>
      <Input
        id={id}
        type='number'
        inputMode='numeric'
        min={REQUIRED_MIN}
        max={REQUIRED_MAX}
        step={1}
        aria-invalid={!valid}
        aria-describedby={valid ? helpId : `${helpId} ${errorId}`}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          if (e.target.value.trim() === '') return onChange(REQUIRED_MIN)
          const n = parseRequired(e.target.value)
          if (n !== null) onChange(n)
        }}
      />
      <p
        id={helpId}
        data-testid='required-help'
        className='text-xs text-muted-foreground'
      >
        {t('inspections.signers.required_help', {
          min: REQUIRED_MIN,
          max: REQUIRED_MAX,
        })}
      </p>
      {valid ? null : (
        <p id={errorId} role='alert' className='text-xs text-red-600'>
          {t('inspections.signers.required_range')}
        </p>
      )}
    </div>
  )
}
