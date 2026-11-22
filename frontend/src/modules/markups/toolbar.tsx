import type { ComponentType } from 'react'
import {
  ArrowUpRight,
  Circle,
  Cloud,
  Highlighter,
  MessageSquareQuote,
  MousePointer2,
  PenLine,
  Pencil,
  Redo2,
  Ruler,
  Spline,
  Square,
  SquareDashed,
  Stamp as StampIcon,
  Trash2,
  Type,
  Undo2,
  Minus,
  DraftingCompass,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { Stamp } from './api'

export type Tool =
  | 'select'
  | 'rect'
  | 'ellipse'
  | 'cloud'
  | 'arrow'
  | 'line'
  | 'polyline'
  | 'freehand'
  | 'text'
  | 'callout'
  | 'highlight'
  | 'stamp'
  | 'measure_length'
  | 'measure_polyline'
  | 'measure_area'
  | 'calibrate'

const TOOLS: {
  id: Tool
  label: string
  icon: ComponentType<{ className?: string }>
  group: number
}[] = [
  { id: 'select', label: 'Select and move (V)', icon: MousePointer2, group: 0 },
  { id: 'rect', label: 'Rectangle', icon: Square, group: 1 },
  { id: 'ellipse', label: 'Ellipse', icon: Circle, group: 1 },
  { id: 'cloud', label: 'Revision cloud', icon: Cloud, group: 1 },
  { id: 'arrow', label: 'Arrow', icon: ArrowUpRight, group: 1 },
  { id: 'line', label: 'Line', icon: Minus, group: 1 },
  {
    id: 'polyline',
    label: 'Polyline (double-click to finish)',
    icon: Spline,
    group: 1,
  },
  { id: 'freehand', label: 'Freehand', icon: Pencil, group: 1 },
  { id: 'text', label: 'Text note', icon: Type, group: 2 },
  {
    id: 'callout',
    label: 'Callout (drag from the point to the note)',
    icon: MessageSquareQuote,
    group: 2,
  },
  { id: 'highlight', label: 'Highlight', icon: Highlighter, group: 2 },
  { id: 'stamp', label: 'Stamp', icon: StampIcon, group: 2 },
  {
    id: 'calibrate',
    label: 'Calibrate scale: pick two points',
    icon: DraftingCompass,
    group: 3,
  },
  { id: 'measure_length', label: 'Measure length', icon: Ruler, group: 3 },
  {
    id: 'measure_polyline',
    label: 'Measure along a path (double-click to finish)',
    icon: PenLine,
    group: 3,
  },
  {
    id: 'measure_area',
    label: 'Measure area (double-click to finish)',
    icon: SquareDashed,
    group: 3,
  },
]

const COLORS = [
  '#dc2626',
  '#ea580c',
  '#facc15',
  '#16a34a',
  '#2563eb',
  '#7c3aed',
  '#111827',
]

export function Toolbar({
  tool,
  onTool,
  color,
  onColor,
  width,
  onWidth,
  fontSize,
  onFontSize,
  stamps,
  stamp,
  onStamp,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  canDelete,
  onDelete,
  readOnly,
}: {
  tool: Tool
  onTool: (t: Tool) => void
  color: string
  onColor: (c: string) => void
  width: number
  onWidth: (w: number) => void
  fontSize: number
  onFontSize: (s: number) => void
  stamps: Stamp[]
  stamp: string
  onStamp: (s: string) => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  canDelete: boolean
  onDelete: () => void
  readOnly: boolean
}) {
  const tools = readOnly ? TOOLS.filter((t) => t.id === 'select') : TOOLS
  return (
    <div className='flex flex-wrap items-center gap-1 rounded-md border bg-background p-1'>
      {tools.map((t, i) => (
        <span key={t.id} className='flex items-center'>
          {i > 0 && tools[i - 1].group !== t.group ? (
            <span className='mx-1 h-5 w-px bg-border' />
          ) : null}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size='icon'
                variant={tool === t.id ? 'default' : 'ghost'}
                className='size-8'
                aria-label={t.label}
                aria-pressed={tool === t.id}
                onClick={() => onTool(t.id)}
              >
                <t.icon className='size-4' />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t.label}</TooltipContent>
          </Tooltip>
        </span>
      ))}
      {tool === 'stamp' ? (
        <Select value={stamp} onValueChange={onStamp}>
          <SelectTrigger size='sm' className='h-8 w-44'>
            <SelectValue placeholder='Stamp' />
          </SelectTrigger>
          <SelectContent>
            {stamps.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.label}
              </SelectItem>
            ))}
            <SelectItem value='custom'>Custom text…</SelectItem>
          </SelectContent>
        </Select>
      ) : null}
      {!readOnly ? (
        <>
          <span className='mx-1 h-5 w-px bg-border' />
          {COLORS.map((c) => (
            <button
              key={c}
              aria-label={`Colour ${c}`}
              className={cn(
                'size-5 rounded-full border-2',
                color === c ? 'border-foreground' : 'border-transparent'
              )}
              style={{ background: c }}
              onClick={() => onColor(c)}
            />
          ))}
          <Select
            value={String(width)}
            onValueChange={(v) => onWidth(Number(v))}
          >
            <SelectTrigger
              size='sm'
              className='h-8 w-24'
              aria-label='Line width'
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[0.75, 1.5, 2.5, 4, 6].map((w) => (
                <SelectItem key={w} value={String(w)}>
                  {w} pt
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={String(fontSize)}
            onValueChange={(v) => onFontSize(Number(v))}
          >
            <SelectTrigger
              size='sm'
              className='h-8 w-24'
              aria-label='Text size'
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[8, 10, 12, 16, 20, 28].map((s) => (
                <SelectItem key={s} value={String(s)}>
                  {s} pt
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className='mx-1 h-5 w-px bg-border' />
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Undo'
            disabled={!canUndo}
            onClick={onUndo}
          >
            <Undo2 className='size-4' />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Redo'
            disabled={!canRedo}
            onClick={onRedo}
          >
            <Redo2 className='size-4' />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Delete selected'
            disabled={!canDelete}
            onClick={onDelete}
          >
            <Trash2 className='size-4' />
          </Button>
        </>
      ) : null}
    </div>
  )
}
