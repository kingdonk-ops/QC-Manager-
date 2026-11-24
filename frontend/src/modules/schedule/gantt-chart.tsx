/**
 * The timeline half of the Gantt, drawn as plain SVG: a two-row timescale header and one row per
 * activity, with status-coloured bars, critical bars in red with a CP badge, milestones as diamonds,
 * summary brackets, progress fill, baseline bars, routed dependency arrows, and today / data-date lines.
 *
 * Drag a bar to move it, drag its right edge to change its duration, or drag from the dot after a bar
 * onto another bar to link them finish-to-start. Colours are written as attributes (not classes) so the
 * SVG exports to PNG/PDF exactly as shown.
 */
import { type PointerEvent, type Ref, useMemo, useState } from 'react'
import type { Activity, Dependency } from './api'
import { COLORS, barColor, floatOf, isCritical } from './gantt-colors'
import {
  HEADER_HEIGHT,
  PX_PER_DAY,
  ROW_HEIGHT,
  type TreeRow,
  type Zoom,
  dayNumber,
  isoOf,
  linkPath,
  snapDays,
  timescale,
  weekday,
} from './gantt-math'

type Drag = {
  mode: 'move' | 'resize' | 'link'
  id: number
  originX: number
  dx: number
  pointer: { x: number; y: number }
}

type Props = {
  rows: TreeRow<Activity>[]
  dependencies: Dependency[]
  zoom: Zoom
  from: number
  to: number
  workingDays: number[]
  holidays: string[]
  dataDate?: string | null
  showBaseline: boolean
  editable: boolean
  selectedId?: number | null
  headerRef?: Ref<SVGSVGElement>
  bodyRef?: Ref<SVGSVGElement>
  onSelect?: (id: number) => void
  onMove?: (id: number, start: string) => void
  onResize?: (id: number, finish: string) => void
  onLink?: (predecessorId: number, successorId: number) => void
}

function span(a: Activity): [number, number] | null {
  const start = a.early_start ?? a.planned_start
  const finish = a.early_finish ?? a.planned_finish ?? start
  if (!start || !finish) return null
  return [dayNumber(start), dayNumber(finish)]
}

export function TimescaleHeader({
  zoom,
  from,
  to,
  svgRef,
}: {
  zoom: Zoom
  from: number
  to: number
  svgRef?: Ref<SVGSVGElement>
}) {
  const px = PX_PER_DAY[zoom]
  const width = (to - from) * px
  const { top, bottom } = useMemo(
    () => timescale(zoom, from, to),
    [zoom, from, to]
  )
  const x = (day: number) => Math.max(0, (day - from) * px)
  const half = HEADER_HEIGHT / 2
  return (
    <svg
      ref={svgRef}
      width={width}
      height={HEADER_HEIGHT}
      className='block'
      fontSize={11}
      fill='currentColor'
      role='img'
      aria-label='Timescale'
    >
      {top.map((t) => (
        <g key={`t${t.start}`}>
          <line
            x1={x(t.start)}
            x2={x(t.start)}
            y1={0}
            y2={HEADER_HEIGHT}
            stroke='currentColor'
            strokeOpacity={0.25}
          />
          <text x={x(t.start) + 4} y={15} fontWeight={600}>
            {t.label}
          </text>
        </g>
      ))}
      <line
        x1={0}
        x2={width}
        y1={half}
        y2={half}
        stroke='currentColor'
        strokeOpacity={0.2}
      />
      {bottom.map((t) => {
        const w = (t.end - t.start) * px
        return (
          <g key={`b${t.start}`}>
            <line
              x1={x(t.start)}
              x2={x(t.start)}
              y1={half}
              y2={HEADER_HEIGHT}
              stroke='currentColor'
              strokeOpacity={0.15}
            />
            {w >= 14 ? (
              <text
                x={x(t.start) + w / 2}
                y={half + 15}
                textAnchor='middle'
                fillOpacity={0.75}
              >
                {t.label}
              </text>
            ) : null}
          </g>
        )
      })}
      <line
        x1={0}
        x2={width}
        y1={HEADER_HEIGHT - 0.5}
        y2={HEADER_HEIGHT - 0.5}
        stroke='currentColor'
        strokeOpacity={0.3}
      />
    </svg>
  )
}

export function GanttChart({
  rows,
  dependencies,
  zoom,
  from,
  to,
  workingDays,
  holidays,
  dataDate,
  showBaseline,
  editable,
  selectedId,
  bodyRef,
  onSelect,
  onMove,
  onResize,
  onLink,
}: Props) {
  const px = PX_PER_DAY[zoom]
  const width = (to - from) * px
  const height = Math.max(rows.length * ROW_HEIGHT, ROW_HEIGHT)
  const [drag, setDrag] = useState<Drag | null>(null)
  const x = (day: number) => (day - from) * px
  const rowIndex = useMemo(
    () => new Map(rows.map((r, i) => [r.item.id, i])),
    [rows]
  )

  const nonWorking = useMemo(() => {
    if (px < 6) return []
    const off = new Set(holidays.map(dayNumber))
    const working = new Set(workingDays)
    const out: number[] = []
    for (let day = from; day < to; day++)
      if (!working.has(weekday(day)) || off.has(day)) out.push(day)
    return out
  }, [px, holidays, workingDays, from, to])

  const [today] = useState(() => Math.floor(Date.now() / 86_400_000))

  const startDrag = (
    e: PointerEvent<SVGElement>,
    mode: Drag['mode'],
    id: number
  ) => {
    if (!editable) return
    e.stopPropagation()
    const svg = e.currentTarget.ownerSVGElement
    svg?.setPointerCapture(e.pointerId)
    const box = svg?.getBoundingClientRect()
    setDrag({
      mode,
      id,
      originX: e.clientX,
      dx: 0,
      pointer: {
        x: e.clientX - (box?.left ?? 0),
        y: e.clientY - (box?.top ?? 0),
      },
    })
  }

  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    if (!drag) return
    const box = e.currentTarget.getBoundingClientRect()
    setDrag({
      ...drag,
      dx: e.clientX - drag.originX,
      pointer: { x: e.clientX - box.left, y: e.clientY - box.top },
    })
  }

  const onPointerUp = (e: PointerEvent<SVGSVGElement>) => {
    if (!drag) return
    e.currentTarget.releasePointerCapture(e.pointerId)
    const row = rows.find((r) => r.item.id === drag.id)
    const s = row ? span(row.item) : null
    const days = snapDays(drag.dx, zoom)
    if (drag.mode === 'link') {
      const target = document
        .elementsFromPoint(e.clientX, e.clientY)
        .map((el) => el.closest('[data-activity]'))
        .find(Boolean)
      const targetId = Number(target?.getAttribute('data-activity'))
      if (targetId && targetId !== drag.id) onLink?.(drag.id, targetId)
    } else if (s && days !== 0) {
      if (drag.mode === 'move') onMove?.(drag.id, isoOf(s[0] + days))
      else onResize?.(drag.id, isoOf(Math.max(s[0], s[1] + days)))
    }
    setDrag(null)
  }

  const anchor = (a: Activity, end: 'start' | 'finish') => {
    const s = span(a)
    const i = rowIndex.get(a.id)
    if (!s || i === undefined) return null
    const y = i * ROW_HEIGHT + ROW_HEIGHT / 2
    if (a.type === 'milestone')
      return { x: x(s[0]) + (end === 'start' ? -6 : 6), y }
    return { x: end === 'start' ? x(s[0]) : x(s[1] + 1), y }
  }

  const byId = useMemo(
    () => new Map(rows.map((r) => [r.item.id, r.item])),
    [rows]
  )

  return (
    <svg
      ref={bodyRef}
      width={width}
      height={height}
      className='block touch-none select-none'
      fontSize={10}
      fill='currentColor'
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => setDrag(null)}
      role='img'
      aria-label='Gantt chart'
    >
      <defs>
        <marker
          id='gantt-arrow'
          viewBox='0 0 8 8'
          refX='7'
          refY='4'
          markerWidth='6'
          markerHeight='6'
          orient='auto-start-reverse'
        >
          <path d='M0,0 L8,4 L0,8 z' fill={COLORS.link} />
        </marker>
        <marker
          id='gantt-arrow-critical'
          viewBox='0 0 8 8'
          refX='7'
          refY='4'
          markerWidth='6'
          markerHeight='6'
          orient='auto-start-reverse'
        >
          <path d='M0,0 L8,4 L0,8 z' fill={COLORS.critical} />
        </marker>
      </defs>

      {nonWorking.map((day) => (
        <rect
          key={day}
          x={x(day)}
          y={0}
          width={px}
          height={height}
          fill={COLORS.nonWorking}
          fillOpacity={0.12}
        />
      ))}
      {rows.map((r, i) => (
        <rect
          key={`row${r.item.id}`}
          x={0}
          y={i * ROW_HEIGHT}
          width={width}
          height={ROW_HEIGHT}
          fill={r.item.id === selectedId ? COLORS.in_progress : 'transparent'}
          fillOpacity={r.item.id === selectedId ? 0.08 : 0}
          onClick={() => onSelect?.(r.item.id)}
        />
      ))}
      {rows.map((_, i) => (
        <line
          key={`grid${i}`}
          x1={0}
          x2={width}
          y1={(i + 1) * ROW_HEIGHT - 0.5}
          y2={(i + 1) * ROW_HEIGHT - 0.5}
          stroke='currentColor'
          strokeOpacity={0.06}
        />
      ))}

      {dependencies.map((d) => {
        const pred = byId.get(d.predecessor_id)
        const succ = byId.get(d.successor_id)
        if (!pred || !succ) return null
        const out = d.type === 'FS' || d.type === 'FF' ? 'finish' : 'start'
        const into = d.type === 'FS' || d.type === 'SS' ? 'start' : 'finish'
        const a = anchor(pred, out)
        const b = anchor(succ, into)
        if (!a || !b) return null
        const critical =
          isCritical(pred) &&
          isCritical(succ) &&
          succ.driving_predecessor_ids.includes(pred.id)
        return (
          <path
            key={`dep${d.id}`}
            d={linkPath(d.type, a, b)}
            fill='none'
            stroke={critical ? COLORS.critical : COLORS.link}
            strokeWidth={critical ? 1.5 : 1}
            strokeOpacity={0.9}
            markerEnd={`url(#${critical ? 'gantt-arrow-critical' : 'gantt-arrow'})`}
          >
            <title>{`${pred.code} → ${succ.code} ${d.type}${d.lag ? ` ${d.lag > 0 ? '+' : ''}${d.lag}d` : ''}`}</title>
          </path>
        )
      })}

      {rows.map(({ item: a }, i) => {
        const s = span(a)
        if (!s) return null
        const top = i * ROW_HEIGHT
        const dragging = drag && drag.id === a.id ? drag : null
        const shift = dragging?.mode === 'move' ? dragging.dx : 0
        const stretch = dragging?.mode === 'resize' ? dragging.dx : 0
        const x1 = x(s[0]) + shift
        const w = Math.max((s[1] - s[0] + 1) * px + stretch, 2)
        const color = barColor(a)
        const pct = Math.max(0, Math.min(100, a.percent_complete)) / 100
        const baseline =
          showBaseline && a.baseline_start && a.baseline_finish ? (
            <rect
              x={x(dayNumber(a.baseline_start))}
              y={top + 21}
              width={Math.max(
                (dayNumber(a.baseline_finish) -
                  dayNumber(a.baseline_start) +
                  1) *
                  px,
                2
              )}
              height={4}
              rx={1}
              fill={COLORS.baseline}
            >
              <title>{`Baseline ${a.baseline_start} – ${a.baseline_finish}`}</title>
            </rect>
          ) : null
        const label = (
          <title>{`${a.code} ${a.name}\n${a.early_start} – ${a.early_finish} (${a.duration}d)\nFloat ${floatOf(a) ?? '–'}d · ${Math.round(a.percent_complete)}%`}</title>
        )

        if (a.type === 'summary') {
          const y = top + 8
          return (
            <g key={a.id} data-activity={a.id}>
              {baseline}
              <path
                d={`M${x1},${y} h${w} v9 l-5,-4 H${x1 + 5} l-5,4 z`}
                fill={color}
              >
                {label}
              </path>
              <rect
                x={x1}
                y={y}
                width={w * pct}
                height={4}
                fill={COLORS.completed}
              />
            </g>
          )
        }

        if (a.type === 'milestone') {
          const cx = x(s[0]) + shift
          const cy = top + ROW_HEIGHT / 2 - 2
          return (
            <g key={a.id} data-activity={a.id}>
              {baseline}
              <path
                d={`M${cx},${cy - 7} l7,7 l-7,7 l-7,-7 z`}
                fill={color}
                className={editable ? 'cursor-grab' : undefined}
                onPointerDown={(e) => startDrag(e, 'move', a.id)}
                onClick={() => onSelect?.(a.id)}
              >
                {label}
              </path>
              {isCritical(a) && a.status !== 'completed' ? (
                <CpBadge x={cx + 11} y={top + 6} />
              ) : null}
              {editable ? (
                <circle
                  cx={cx + 9}
                  cy={cy}
                  r={3}
                  fill={COLORS.link}
                  fillOpacity={0.5}
                  className='cursor-crosshair'
                  onPointerDown={(e) => startDrag(e, 'link', a.id)}
                />
              ) : null}
            </g>
          )
        }

        return (
          <g key={a.id} data-activity={a.id}>
            {baseline}
            <rect
              x={x1}
              y={top + 6}
              width={w}
              height={14}
              rx={3}
              fill={color}
              fillOpacity={0.85}
              className={editable ? 'cursor-grab' : undefined}
              onPointerDown={(e) => startDrag(e, 'move', a.id)}
              onClick={() => onSelect?.(a.id)}
            >
              {label}
            </rect>
            {pct > 0 ? (
              <rect
                x={x1}
                y={top + 6}
                width={w * pct}
                height={14}
                rx={3}
                fill='#000000'
                fillOpacity={0.28}
                pointerEvents='none'
              />
            ) : null}
            {editable ? (
              <>
                <rect
                  x={x1 + w - 4}
                  y={top + 6}
                  width={6}
                  height={14}
                  fill='transparent'
                  className='cursor-ew-resize'
                  onPointerDown={(e) => startDrag(e, 'resize', a.id)}
                />
                <circle
                  cx={x1 + w + 6}
                  cy={top + 13}
                  r={3}
                  fill={COLORS.link}
                  fillOpacity={0.5}
                  className='cursor-crosshair'
                  onPointerDown={(e) => startDrag(e, 'link', a.id)}
                />
              </>
            ) : null}
            {isCritical(a) && a.status !== 'completed' ? (
              <CpBadge x={x1 + w + (editable ? 12 : 4)} y={top + 7} />
            ) : null}
          </g>
        )
      })}

      {[
        { day: today, color: COLORS.today, label: 'Today' },
        ...(dataDate
          ? [
              {
                day: dayNumber(dataDate),
                color: COLORS.dataDate,
                label: 'Data date',
              },
            ]
          : []),
      ]
        .filter((l) => l.day >= from && l.day <= to)
        .map((l) => (
          <g key={l.label} pointerEvents='none'>
            <line
              x1={x(l.day)}
              x2={x(l.day)}
              y1={0}
              y2={height}
              stroke={l.color}
              strokeWidth={1.5}
              strokeDasharray='4 3'
            />
            <text x={x(l.day) + 3} y={10} fill={l.color} fontWeight={600}>
              {l.label}
            </text>
          </g>
        ))}

      {drag?.mode === 'link' ? (
        <line
          x1={(() => {
            const row = rows.find((r) => r.item.id === drag.id)
            const s = row ? span(row.item) : null
            return s ? x(s[1] + 1) + 6 : 0
          })()}
          y1={(rowIndex.get(drag.id) ?? 0) * ROW_HEIGHT + 13}
          x2={drag.pointer.x}
          y2={drag.pointer.y}
          stroke={COLORS.in_progress}
          strokeDasharray='3 3'
          markerEnd='url(#gantt-arrow)'
          pointerEvents='none'
        />
      ) : null}
    </svg>
  )
}

function CpBadge({ x, y }: { x: number; y: number }) {
  return (
    <g pointerEvents='none'>
      <rect x={x} y={y} width={18} height={12} rx={3} fill={COLORS.critical} />
      <text
        x={x + 9}
        y={y + 9}
        textAnchor='middle'
        fontSize={8}
        fontWeight={700}
        fill='#ffffff'
      >
        CP
      </text>
    </g>
  )
}
