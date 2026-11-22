/**
 * Client-side reading of a numbering pattern, mirroring the server's whitelist
 * (`infrastructure/records/schemes.py`). The server stays the authority: the
 * editor uses this only to show which tokens a pattern uses before the preview
 * comes back.
 */

export const CODE_TOKENS = [
  'discipline',
  'type',
  'doc_type',
  'area',
  'originator',
  'system',
  'unit',
  'level',
  'package',
  'role',
] as const

export const AUTO_TOKENS = ['project', 'year', 'seq'] as const

export type Segment =
  | { kind: 'literal'; text: string }
  | { kind: 'token'; name: string; width?: number; known: boolean }

const TOKEN = /\{([a-z_]+)(?::(\d{1,2}))?\}/g

export function segments(pattern: string): Segment[] {
  const out: Segment[] = []
  let pos = 0
  for (const match of pattern.matchAll(TOKEN)) {
    const start = match.index ?? 0
    if (start > pos)
      out.push({ kind: 'literal', text: pattern.slice(pos, start) })
    const name = match[1]
    const width = match[2] ? Number(match[2]) : undefined
    const known =
      (name === 'seq' && true) ||
      (width === undefined &&
        ((CODE_TOKENS as readonly string[]).includes(name) ||
          name === 'project' ||
          name === 'year'))
    out.push({ kind: 'token', name, width, known })
    pos = start + match[0].length
  }
  if (pos < pattern.length)
    out.push({ kind: 'literal', text: pattern.slice(pos) })
  return out
}

/** The code tokens a pattern uses, in order, without repeats. */
export function codeTokens(pattern: string): string[] {
  const seen: string[] = []
  for (const s of segments(pattern)) {
    if (
      s.kind === 'token' &&
      (CODE_TOKENS as readonly string[]).includes(s.name) &&
      !seen.includes(s.name)
    )
      seen.push(s.name)
  }
  return seen
}

/** `"ME Mechanical\nEL Electrical"` ⇄ `[{code: 'ME', label: 'Mechanical'}, ...]`. */
export function parseCodeList(text: string): { code: string; label: string }[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [code, ...rest] = line.split(/\s+/)
      return { code: code.toUpperCase(), label: rest.join(' ') }
    })
}

export function formatCodeList(codes: { code: string; label?: string }[] = []) {
  return codes.map((c) => `${c.code}${c.label ? ` ${c.label}` : ''}`).join('\n')
}
