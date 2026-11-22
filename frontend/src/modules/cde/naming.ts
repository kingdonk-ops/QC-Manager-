/**
 * Builds and checks container names against a naming convention as the user types.
 * Mirrors the backend's rules, which have the final say.
 */

export type CodeOption = { code: string; description?: string }

export type NamingField = {
  key: string
  label: string
  codes?: CodeOption[]
  min_length?: number
  max_length?: number
  charset?: 'alnum' | 'alpha' | 'numeric'
}

export type Convention = {
  separator: string
  fields: NamingField[]
}

const CHARSETS: Record<string, [RegExp, string]> = {
  alnum: [/^[A-Z0-9]+$/, 'letters and digits'],
  alpha: [/^[A-Z]+$/, 'letters'],
  numeric: [/^[0-9]+$/, 'digits'],
}

/** Why `value` doesn't fit `field`, or null when it does. */
export function checkValue(
  field: NamingField,
  raw: string,
  separator: string
): string | null {
  const value = raw.trim().toUpperCase()
  const where = `${field.label} (${field.key})`
  if (!value) return `${where} is required`
  if (value.includes(separator))
    return `${where}: '${value}' must not contain the separator '${separator}'`
  const codes = (field.codes ?? []).map((c) => c.code.toUpperCase())
  if (codes.length) {
    if (!codes.includes(value)) {
      const shown =
        codes.slice(0, 12).join(', ') + (codes.length > 12 ? ', ...' : '')
      return `${where}: '${value}' is not an allowed code (allowed: ${shown})`
    }
    return null
  }
  const low = field.min_length ?? 1
  const high = field.max_length ?? 20
  if (value.length < low || value.length > high) {
    const size = low === high ? `${low}` : `${low} to ${high}`
    return `${where}: '${value}' must be ${size} characters long`
  }
  const [pattern, words] = CHARSETS[field.charset ?? 'alnum']
  if (!pattern.test(value))
    return `${where}: '${value}' may contain only ${words}`
  return null
}

export type Composed = {
  name: string
  errors: Record<string, string>
}

/** The name built from the values, and the problem with each field that has one. */
export function compose(
  convention: Convention,
  values: Record<string, string>
): Composed {
  const errors: Record<string, string> = {}
  const parts = convention.fields.map((field) => {
    const value = (values[field.key] ?? '').trim().toUpperCase()
    const problem = checkValue(field, value, convention.separator)
    if (problem) errors[field.key] = problem
    return value || field.key.toUpperCase()
  })
  return { name: parts.join(convention.separator), errors }
}

/** Split a name (e.g. a file name without its extension) into field values, when it has the right number of parts. */
export function parse(
  convention: Convention,
  name: string
): Record<string, string> | null {
  const parts = name.trim().split(convention.separator)
  if (parts.length !== convention.fields.length) return null
  return Object.fromEntries(
    convention.fields.map((f, i) => [f.key, parts[i].toUpperCase()])
  )
}
