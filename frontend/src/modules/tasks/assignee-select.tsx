import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAssignees } from './api'

const NONE = 'none'

/** Picks an account to assign work to, or nobody. */
export function AssigneeSelect({
  value,
  onChange,
  disabled,
  placeholder = 'Unassigned',
  className,
  id,
}: {
  value: number | null | undefined
  onChange: (id: number | null) => void
  disabled?: boolean
  placeholder?: string
  className?: string
  id?: string
}) {
  const { data: people = [] } = useAssignees()
  return (
    <Select
      value={value ? String(value) : NONE}
      onValueChange={(v) => onChange(v === NONE ? null : Number(v))}
      disabled={disabled}
    >
      <SelectTrigger id={id} className={className ?? 'w-full'}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{placeholder}</SelectItem>
        {people.map((p) => (
          <SelectItem key={p.id} value={String(p.id)}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
