import type { Board, TaskStatus } from './api'

/** The board with ``id`` moved into ``status`` above ``beforeId`` (or at the bottom). */
export function applyMove(
  board: Board,
  id: number,
  status: TaskStatus,
  beforeId?: number | null
): Board {
  const task = board.columns.flatMap((c) => c.tasks).find((t) => t.id === id)
  if (!task) return board
  const moved = { ...task, status }
  return {
    ...board,
    columns: board.columns.map((column) => {
      const rest = column.tasks.filter((t) => t.id !== id)
      if (column.status !== status) return { ...column, tasks: rest }
      const at = beforeId ? rest.findIndex((t) => t.id === beforeId) : -1
      const tasks =
        at < 0
          ? [...rest, moved]
          : [...rest.slice(0, at), moved, ...rest.slice(at)]
      return { ...column, tasks }
    }),
  }
}

/** The six weeks shown for a month, starting on Monday. */
export function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  return Array.from(
    { length: 42 },
    (_, i) => new Date(year, month, 1 - offset + i)
  )
}
