import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const NONE = '__none__'

/** A select over `{ value, label }` options; `emptyLabel` adds a "none" choice that maps to `''`. */
export function Choice({
  id,
  value,
  onChange,
  options,
  emptyLabel,
  className,
}: {
  id?: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  emptyLabel?: string
  className?: string
}) {
  return (
    <Select
      value={value === '' && emptyLabel ? NONE : value}
      onValueChange={(v) => onChange(v === NONE ? '' : v)}
    >
      <SelectTrigger id={id} size='sm' className={className ?? 'w-full'}>
        <SelectValue placeholder={emptyLabel} />
      </SelectTrigger>
      <SelectContent>
        {emptyLabel ? <SelectItem value={NONE}>{emptyLabel}</SelectItem> : null}
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
