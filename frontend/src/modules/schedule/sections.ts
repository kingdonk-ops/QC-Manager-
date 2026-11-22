/** `[{code,name,value}]` as JSON, or one section per line: `code, name, value`. */
export function parseSections(
  text: string
): { code: string; name: string; value: string }[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  if (trimmed.startsWith('[')) {
    const parsed = JSON.parse(trimmed) as {
      code: unknown
      name: unknown
      value: unknown
    }[]
    return parsed.map((s) => ({
      code: String(s.code),
      name: String(s.name),
      value: String(s.value ?? 0),
    }))
  }
  return trimmed
    .split(/\r?\n/)
    .map((line) => {
      // Tabs or semicolons separate cells; with commas, the value keeps any thousands separators.
      let cells = line.split(/[;\t]/)
      if (cells.length < 3) {
        const parts = line.split(',')
        cells = [parts[0], parts[1] ?? '', parts.slice(2).join('')]
      }
      return cells.map((c) => c.trim())
    })
    .filter((cells) => cells.length >= 3 && cells[0] && cells[1])
    .map(([code, name, value]) => ({
      code,
      name,
      value: String(Number(value.replace(/[^0-9.-]/g, '')) || 0),
    }))
}
