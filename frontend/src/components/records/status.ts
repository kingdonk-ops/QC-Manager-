export function statusLabel(status: string) {
  return status.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}
