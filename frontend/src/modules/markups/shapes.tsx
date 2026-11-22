import type { PointerEvent, ReactNode } from 'react'
import {
  bounds,
  centroid,
  cloudPath,
  formatMeasurement,
  type Box,
  type Measurement,
  type Point,
} from './geometry'

export type Shape = {
  id?: number
  type: string
  geometry: Record<string, unknown>
  style: { [key: string]: unknown }
  text?: string | null
  measurement?: { [key: string]: unknown } | null
}

function ArrowHead({
  a,
  b,
  size,
  color,
}: {
  a: Point
  b: Point
  size: number
  color: string
}) {
  const angle = Math.atan2(b[1] - a[1], b[0] - a[0])
  const left: Point = [
    b[0] - size * Math.cos(angle - Math.PI / 7),
    b[1] - size * Math.sin(angle - Math.PI / 7),
  ]
  const right: Point = [
    b[0] - size * Math.cos(angle + Math.PI / 7),
    b[1] - size * Math.sin(angle + Math.PI / 7),
  ]
  return (
    <polygon
      points={[b, left, right].map((p) => p.join(',')).join(' ')}
      fill={color}
      stroke='none'
    />
  )
}

function Label({
  at,
  text,
  color,
  size,
}: {
  at: Point
  text: string
  color: string
  size: number
}) {
  const width = text.length * size * 0.6 + 6
  return (
    <g>
      <rect
        x={at[0]}
        y={at[1] - size - 1}
        width={width}
        height={size + 4}
        fill='white'
        stroke={color}
        strokeWidth={0.5}
      />
      <text
        x={at[0] + 3}
        y={at[1]}
        fontSize={size}
        fontWeight={600}
        fill={color}
        fontFamily='Helvetica, Arial, sans-serif'
      >
        {text}
      </text>
    </g>
  )
}

function Lines({
  text,
  x,
  y,
  size,
  color,
  bold,
  anchor,
}: {
  text: string
  x: number
  y: number
  size: number
  color: string
  bold?: boolean
  anchor?: 'start' | 'middle'
}) {
  return (
    <text
      x={x}
      y={y}
      fontSize={size}
      fill={color}
      fontWeight={bold ? 700 : 400}
      textAnchor={anchor ?? 'start'}
      fontFamily='Helvetica, Arial, sans-serif'
      style={{ whiteSpace: 'pre' }}
    >
      {text.split('\n').map((line, i) => (
        <tspan key={i} x={x} dy={i === 0 ? size : size * 1.2}>
          {line}
        </tspan>
      ))}
    </text>
  )
}

/** One markup drawn in PDF units. */
export function ShapeView({
  shape,
  selected,
  onPointerDown,
  calibratedLabel,
}: {
  shape: Shape
  selected?: boolean
  onPointerDown?: (e: PointerEvent<SVGGElement>) => void
  /** A live measurement for a draft, when the page is calibrated. */
  calibratedLabel?: string
}) {
  const style = shape.style as {
    color?: string
    width?: number
    opacity?: number
    font_size?: number
  }
  const color = style.color ?? '#dc2626'
  const width = style.width ?? 1.5
  const size = style.font_size ?? 12
  const opacity = style.opacity ?? 1
  const g = shape.geometry
  const text = shape.text ?? ''
  const common = {
    stroke: color,
    strokeWidth: width,
    fill: 'none',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
  let body: ReactNode = null
  const box = g as unknown as Box
  const points = (g.points ?? []) as Point[]

  switch (shape.type) {
    case 'rect':
      body = (
        <rect x={box.x} y={box.y} width={box.w} height={box.h} {...common} />
      )
      break
    case 'ellipse':
      body = (
        <ellipse
          cx={box.x + box.w / 2}
          cy={box.y + box.h / 2}
          rx={box.w / 2}
          ry={box.h / 2}
          {...common}
        />
      )
      break
    case 'cloud':
      body = <path d={cloudPath(box)} {...common} />
      break
    case 'highlight':
      body = (
        <rect
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          fill={color}
          fillOpacity={
            style.opacity && style.opacity < 1 ? style.opacity : 0.35
          }
          stroke='none'
        />
      )
      break
    case 'text':
      body = (
        <Lines text={text} x={box.x + 2} y={box.y} size={size} color={color} />
      )
      break
    case 'stamp': {
      const lines = text.split('\n')
      const head = Math.min(size * 1.5, box.h / (lines.length + 0.6))
      body = (
        <g>
          <rect
            x={box.x}
            y={box.y}
            width={box.w}
            height={box.h}
            rx={Math.min(6, box.h / 4)}
            {...common}
            strokeWidth={Math.max(width, 2)}
          />
          <Lines
            text={lines[0].toUpperCase()}
            x={box.x + box.w / 2}
            y={box.y + head * 0.25}
            size={head}
            color={color}
            bold
            anchor='middle'
          />
          {lines.length > 1 ? (
            <Lines
              text={lines.slice(1).join('\n')}
              x={box.x + box.w / 2}
              y={box.y + head * 1.25}
              size={head * 0.55}
              color={color}
              anchor='middle'
            />
          ) : null}
        </g>
      )
      break
    }
    case 'callout': {
      const [ax, ay] = (g.anchor ?? [box.x, box.y]) as Point
      const cx = Math.min(Math.max(ax, box.x), box.x + box.w)
      const cy = Math.min(Math.max(ay, box.y), box.y + box.h)
      body = (
        <g>
          <line x1={ax} y1={ay} x2={cx} y2={cy} {...common} />
          <ArrowHead
            a={[cx, cy]}
            b={[ax, ay]}
            size={Math.max(6, width * 4)}
            color={color}
          />
          <rect
            x={box.x}
            y={box.y}
            width={box.w}
            height={box.h}
            {...common}
            fill='white'
          />
          <Lines
            text={text}
            x={box.x + 3}
            y={box.y + 2}
            size={size}
            color={color}
          />
        </g>
      )
      break
    }
    default: {
      if (points.length < 1) break
      const d = points
        .map((p, i) => `${i ? 'L' : 'M'} ${p[0]} ${p[1]}`)
        .join(' ')
      const area = shape.type === 'measure_area'
      const measureLabel = shape.type.startsWith('measure')
        ? (calibratedLabel ??
          (formatMeasurement(shape.measurement as Measurement | null) ||
            'not calibrated'))
        : null
      const at: Point = area
        ? centroid(points)
        : [points[points.length - 1][0] + 4, points[points.length - 1][1] - 4]
      body = (
        <g>
          <path
            d={area ? `${d} Z` : d}
            {...common}
            fill={area ? color : 'none'}
            fillOpacity={area ? 0.15 : 0}
          />
          {shape.type === 'arrow' && points.length >= 2 ? (
            <ArrowHead
              a={points[points.length - 2]}
              b={points[points.length - 1]}
              size={Math.max(8, width * 4)}
              color={color}
            />
          ) : null}
          {measureLabel
            ? (area ? points : [points[0], points[points.length - 1]]).map(
                (p, i) => (
                  <circle
                    key={i}
                    cx={p[0]}
                    cy={p[1]}
                    r={Math.max(1.5, width)}
                    fill={color}
                  />
                )
              )
            : null}
          {measureLabel ? (
            <Label
              at={at}
              text={measureLabel}
              color={color}
              size={Math.max(7, size * 0.8)}
            />
          ) : null}
        </g>
      )
    }
  }
  const outline = selected ? bounds(g) : null
  return (
    <g
      opacity={shape.type === 'highlight' ? 1 : opacity}
      onPointerDown={onPointerDown}
      style={{ cursor: onPointerDown ? 'move' : undefined }}
      data-markup-id={shape.id}
    >
      {/* A wide invisible stroke so thin lines are easy to pick. */}
      {onPointerDown && points.length ? (
        <path
          d={points.map((p, i) => `${i ? 'L' : 'M'} ${p[0]} ${p[1]}`).join(' ')}
          stroke='transparent'
          strokeWidth={Math.max(10, width * 4)}
          fill={shape.type === 'measure_area' ? 'transparent' : 'none'}
        />
      ) : null}
      {onPointerDown && !points.length ? (
        <rect
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          fill='transparent'
        />
      ) : null}
      {body}
      {outline ? (
        <rect
          x={outline.x - 4}
          y={outline.y - 4}
          width={outline.w + 8}
          height={outline.h + 8}
          fill='none'
          stroke='#2563eb'
          strokeDasharray='4 3'
          strokeWidth={1}
          pointerEvents='none'
        />
      ) : null}
    </g>
  )
}
