import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect, type Option } from '@/components/native-select'

/** A labelled control; the message under it shows once the field has been touched and is invalid. */
export function Control({
  id,
  label,
  error,
  className,
  children,
}: {
  id: string
  label: string
  error?: string
  className?: string
  children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className={`grid gap-1.5 ${className ?? ''}`}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p
          role='alert'
          data-testid={`${id}-error`}
          className='text-xs text-destructive'
        >
          {t(error)}
        </p>
      ) : null}
    </div>
  )
}

export function TextControl({
  id,
  label,
  value,
  onChange,
  onBlur,
  error,
  type,
  className,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  onBlur?: () => void
  error?: string
  type?: string
  className?: string
}) {
  return (
    <Control id={id} label={label} error={error} className={className}>
      <Input
        id={id}
        type={type}
        value={value}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      />
    </Control>
  )
}

export function AreaControl({
  id,
  label,
  value,
  onChange,
  error,
  className,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  error?: string
  className?: string
}) {
  return (
    <Control id={id} label={label} error={error} className={className}>
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Control>
  )
}

export function SelectControl({
  id,
  label,
  value,
  onChange,
  onBlur,
  options,
  placeholder,
  error,
  className,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  onBlur?: () => void
  options: Option[]
  placeholder?: string
  error?: string
  className?: string
}) {
  return (
    <Control id={id} label={label} error={error} className={className}>
      <NativeSelect
        id={id}
        options={options}
        placeholder={placeholder}
        value={value}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      />
    </Control>
  )
}
