/** Every page of a paginated list endpoint (the API serves at most 100 rows per page), merged into one. */
export async function allPages<
  P extends { data: unknown[]; has_more: boolean },
>(get: (page: number) => Promise<P>, maxPages = 100): Promise<P> {
  const first = await get(1)
  const data = [...first.data]
  let last = first
  for (let page = 2; last.has_more && page <= maxPages; page++) {
    last = await get(page)
    data.push(...last.data)
  }
  return { ...first, data, has_more: last.has_more }
}
