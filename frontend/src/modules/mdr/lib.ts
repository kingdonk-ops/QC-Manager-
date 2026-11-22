/** Pure helpers for the dossier builder. */

export type Section = { key: string; title: string; enabled: boolean }

/** `sections` with the one at `index` moved by `delta` (-1 up, +1 down); unchanged at the ends. */
export function moveSection<T>(
  sections: T[],
  index: number,
  delta: number
): T[] {
  const target = index + delta
  if (target < 0 || target >= sections.length || index < 0) return sections
  const out = [...sections]
  const [item] = out.splice(index, 1)
  out.splice(target, 0, item)
  return out
}

/** Hex SHA-256 of a file, computed in the browser so the file is never uploaded. */
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

/** What the next issue would be called: review A, B ... Z, AA; final 0, 1 ... */
export function nextRevisionLabel(kind: 'review' | 'final', issued: number) {
  if (kind === 'final') return String(issued)
  let n = issued + 1
  let label = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    label = String.fromCharCode(65 + rem) + label
    n = Math.floor((n - 1) / 26)
  }
  return label
}

export type Check = {
  key: string
  blocking: boolean
  status: string
}

/** Whether nothing blocking failed. `not_available` never blocks. */
export function gateReady(checks: Check[]) {
  return !checks.some((c) => c.blocking && c.status === 'fail')
}
