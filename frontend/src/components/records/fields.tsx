import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const NONE = '__none__'

export function Field({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('grid gap-1.5', className)}>
      <Label className='text-xs text-muted-foreground'>{label}</Label>
      {children}
    </div>
  )
}

/** A select over plain string options; `allowNone` adds an empty choice that maps to `null`. */
export function SelectField({
  value,
  onChange,
  options,
  allowNone,
  disabled,
  placeholder,
}: {
  value: string | null | undefined
  onChange: (value: string | null) => void
  options: { value: string; label: string }[]
  allowNone?: boolean
  disabled?: boolean
  placeholder?: string
}) {
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(v) => onChange(v === NONE ? null : v)}
      disabled={disabled}
    >
      <SelectTrigger className='w-full' size='sm'>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone ? <SelectItem value={NONE}>—</SelectItem> : null}
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function Kpi({
  label,
  value,
  tone,
}: {
  label: string
  value: ReactNode
  tone?: 'good' | 'bad' | 'warn'
}) {
  return (
    <Card className='gap-1 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-xs font-medium text-muted-foreground'>
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='px-4'>
        <p
          className={cn(
            'text-lg font-semibold tabular-nums',
            tone === 'good' && 'text-green-600',
            tone === 'bad' && 'text-red-600',
            tone === 'warn' && 'text-amber-600'
          )}
        >
          {value}
        </p>
      </CardContent>
    </Card>
  )
}
