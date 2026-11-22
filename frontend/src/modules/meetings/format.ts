/** Moves ``id`` to sit before ``beforeId`` (or last), returning the new order of ids. */
export function reorder(ids: number[], id: number, beforeId: number | null) {
  const rest = ids.filter((i) => i !== id)
  const at = beforeId === null ? -1 : rest.indexOf(beforeId)
  return at < 0 ? [...rest, id] : [...rest.slice(0, at), id, ...rest.slice(at)]
}

/** ISO timestamp → the value a `datetime-local` input takes, in local time. */
export function toLocalInput(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
