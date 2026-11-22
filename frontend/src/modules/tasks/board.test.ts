import { describe, expect, it } from 'vitest'
import type { Board, Task } from './api'
import { applyMove, monthGrid } from './board'
import { NO_FILTERS, matches, sourceLink } from './constants'

const task = (id: number, status: string, extra: Partial<Task> = {}): Task =>
  ({
    id,
    project_id: 1,
    code: `TASK-00${id}`,
    title: `Task ${id}`,
    description: null,
    type: 'general',
    status,
    priority: 'medium',
    assignee_id: null,
    start_date: null,
    due_date: null,
    position: id,
    type_fields: {},
    entity_type: null,
    entity_id: null,
    ...extra,
  }) as Task

const board: Board = {
  project_id: 1,
  type_fields: {},
  columns: [
    { status: 'todo', wip_limit: 0, tasks: [task(1, 'todo'), task(2, 'todo')] },
    { status: 'in_progress', wip_limit: 1, tasks: [task(3, 'in_progress')] },
    { status: 'review', wip_limit: 0, tasks: [] },
    { status: 'done', wip_limit: 0, tasks: [] },
  ],
}

const ids = (b: Board, status: string) =>
  b.columns.find((c) => c.status === status)!.tasks.map((t) => t.id)

describe('applyMove', () => {
  it('moves a card above another in a different column', () => {
    const moved = applyMove(board, 1, 'in_progress', 3)
    expect(ids(moved, 'todo')).toEqual([2])
    expect(ids(moved, 'in_progress')).toEqual([1, 3])
    expect(moved.columns[1].tasks[0].status).toBe('in_progress')
  })

  it('moves a card to the bottom, and within its own column', () => {
    expect(ids(applyMove(board, 1, 'todo', null), 'todo')).toEqual([2, 1])
    expect(ids(applyMove(board, 2, 'todo', 1), 'todo')).toEqual([2, 1])
  })
})

describe('monthGrid', () => {
  it('covers six weeks starting on the Monday on or before the 1st', () => {
    const days = monthGrid(2026, 10) // November 2026 starts on a Sunday
    expect(days).toHaveLength(42)
    expect(days[0].getDay()).toBe(1)
    expect(days[6].getDate()).toBe(1)
  })
})

describe('filters', () => {
  it('matches on assignee, type, overdue and search', () => {
    const t = task(5, 'todo', { assignee_id: 7, overdue: true, type: 'design' })
    expect(matches(t, NO_FILTERS, 1)).toBe(true)
    expect(matches(t, { ...NO_FILTERS, mine: true }, 1)).toBe(false)
    expect(matches(t, { ...NO_FILTERS, mine: true }, 7)).toBe(true)
    expect(matches(t, { ...NO_FILTERS, type: 'procurement' }, 7)).toBe(false)
    expect(matches(t, { ...NO_FILTERS, overdue: true }, 7)).toBe(true)
    expect(matches(t, { ...NO_FILTERS, search: 'task-005' }, 7)).toBe(true)
  })

  it('links a task to the record it came from', () => {
    expect(
      sourceLink(task(1, 'todo', { entity_type: 'meeting', entity_id: 4 }))
    ).toBe('/meetings?project=1&meeting=4')
    expect(sourceLink(task(1, 'todo'))).toBeNull()
  })
})
