/**
 * A styled native `<select>`: the phone's own picker on mobile, which suits field forms.
 * `UserSelect` lists people for an assignee field (everyone with `people.read`, otherwise just you).
 */
import type { ComponentProps } from 'react'
import { usePeople } from '@/modules/people/api'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'

export type Option = { value: string; label: string }

/** `options` with labels, or `values` (snake_case) labelled "Snake case". */
export function NativeSelect({
  options,
  values,
  placeholder,
  className,
  ...props
}: Omit<ComponentProps<'select'>, 'children'> & {
  options?: Option[]
  values?: readonly string[]
  placeholder?: string
}) {
  const choices = options ?? optionsOf(values ?? [])
  return (
    <select
      className={cn(
        'flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2 py-1 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 md:text-sm dark:bg-input/30',
        className
      )}
      {...props}
    >
      {placeholder !== undefined ? (
        <option value=''>{placeholder}</option>
      ) : null}
      {choices.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

/** `value`/`onChange` carry a user id, or `null` for nobody. */
export function UserSelect({
  value,
  onChange,
  placeholder = '—',
  className,
  id,
}: {
  value: number | null | undefined
  onChange: (id: number | null) => void
  placeholder?: string
  className?: string
  id?: string
}) {
  const session = useSession()
  const listable = can(session, 'people.read')
  const { data: people = [] } = usePeople('', false, listable)
  const options: Option[] = listable
    ? people.map((p) => ({ value: String(p.id), label: p.name }))
    : [{ value: String(session.id), label: session.name }]
  if (value && !options.some((o) => o.value === String(value)))
    options.push({ value: String(value), label: `User ${value}` })
  return (
    <NativeSelect
      id={id}
      className={className}
      options={options}
      placeholder={placeholder}
      value={value ? String(value) : ''}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    />
  )
}

function optionsOf(values: readonly string[]): Option[] {
  return values.map((v) => ({
    value: v,
    label: v.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()),
  }))
}
