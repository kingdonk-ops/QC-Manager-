import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
} from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { can, useSession } from '@/lib/session'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/layout/page'
import { fileUrl } from '@/components/records/files'
import { useModuleParams } from '../_runtime'
import {
  createMarkup,
  deleteMarkup,
  flattenedUrl,
  keys,
  updateMarkup,
  useCalibrations,
  useDrawing,
  useMarkups,
  useSets,
  useStamps,
  type Markup,
  type MarkupType,
  type Style,
} from './api'
import {
  distance,
  formatMeasurement,
  measure,
  normaliseBox,
  translate,
  UNIT_METERS,
  type Point,
} from './geometry'
import { usePageCanvas, usePdfDocument, usePdfPage } from './pdf'
import { ShapeView, type Shape } from './shapes'
import { SidePanel } from './side-panel'
import { Toolbar, type Tool } from './toolbar'

type Geometry = Record<string, unknown>
type Op =
  | { kind: 'create'; markup: Markup }
  | { kind: 'delete'; markup: Markup }
  | { kind: 'update'; markup: Markup; before: Geometry; after: Geometry }

const DRAG_TOOLS: Tool[] = [
  'rect',
  'ellipse',
  'cloud',
  'highlight',
  'arrow',
  'line',
  'measure_length',
  'calibrate',
  'callout',
  'freehand',
]
const CLICK_TOOLS: Tool[] = ['polyline', 'measure_polyline', 'measure_area']
const BOX_TOOLS: Tool[] = ['rect', 'ellipse', 'cloud', 'highlight']

type Prompt =
  | { kind: 'text'; geometry: Geometry }
  | { kind: 'callout'; geometry: Geometry }
  | { kind: 'stamp'; geometry: Geometry }
  | { kind: 'calibrate'; points: [Point, Point] }

function Viewer({ fileId }: { fileId: number }) {
  const session = useSession()
  const queryClient = useQueryClient()
  const { data: drawing } = useDrawing(fileId)
  const { doc, error } = usePdfDocument(fileUrl(fileId, true))
  const [pageNumber, setPageNumber] = useState(1)
  const [scale, setScale] = useState(1.25)
  const pdfPage = usePdfPage(doc, pageNumber)
  const canvas = usePageCanvas(pdfPage, scale)
  const size = useMemo(() => {
    const v = pdfPage?.getViewport({ scale: 1 })
    return v ? { w: v.width, h: v.height } : null
  }, [pdfPage])

  const { data: markups = [] } = useMarkups(fileId)
  const { data: sets = [] } = useSets(fileId)
  const { data: calibrations = [] } = useCalibrations(fileId)
  const { data: stamps = [] } = useStamps(drawing?.project_id)

  const editable = can(session, 'markups.create')
  const [tool, setTool] = useState<Tool>('select')
  const [color, setColor] = useState('#dc2626')
  const [width, setWidth] = useState(1.5)
  const [fontSize, setFontSize] = useState(12)
  const [chosenStamp, setStamp] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [hidden, setHidden] = useState<Set<number>>(new Set())
  const [chosenSet, setActiveSet] = useState<number | null>(null)
  const [draft, setDraft] = useState<Shape | null>(null)
  const [path, setPath] = useState<Point[]>([])
  const [cursor, setCursor] = useState<Point | null>(null)
  const [moving, setMoving] = useState<{
    id: number
    geometry: Geometry
  } | null>(null)
  const [prompt, setPromptState] = useState<Prompt | null>(null)
  const [promptSeq, setPromptSeq] = useState(0)
  const setPrompt = (p: Prompt | null) => {
    setPromptState(p)
    if (p) setPromptSeq((n) => n + 1)
  }
  const [history, setHistory] = useState<{ past: Op[]; future: Op[] }>({
    past: [],
    future: [],
  })
  const drag = useRef<{ start: Point; original?: Markup } | null>(null)
  const ids = useRef(new Map<number, number>())
  const svg = useRef<SVGSVGElement>(null)

  const activeSet =
    chosenSet ?? sets.find((s) => s.author_id === session.id)?.id ?? null
  const stamp = chosenStamp || (stamps[0] ? String(stamps[0].id) : '')

  const calibration = calibrations.find((c) => c.page === pageNumber)
  const style: Style = { color, width, opacity: 1, font_size: fontSize }

  const refreshSets = () =>
    void queryClient.invalidateQueries({ queryKey: keys.sets(fileId) })
  const setMarkups = (fn: (list: Markup[]) => Markup[]) =>
    queryClient.setQueryData<Markup[]>(keys.markups(fileId), (old) =>
      fn(old ?? [])
    )
  const resolve = (id: number) => {
    let current = id
    while (ids.current.has(current)) current = ids.current.get(current)!
    return current
  }

  // --- operations, each undoable ----------------------------------------------------------------------

  const recreate = async (m: Markup) => {
    const made = await createMarkup({
      file_id: m.file_id,
      set_id: m.set_id,
      page: m.page,
      type: m.type as MarkupType,
      geometry: m.geometry,
      style: m.style as Style,
      text: m.text,
    })
    ids.current.set(resolve(m.id), made.id)
    setMarkups((list) => [...list, made])
    return made
  }
  const remove = async (id: number) => {
    const target = resolve(id)
    await deleteMarkup(target)
    setMarkups((list) => list.filter((x) => x.id !== target))
    if (selected === target) setSelected(null)
  }
  const reshape = async (
    id: number,
    geometry: Geometry,
    text?: string | null
  ) => {
    const target = resolve(id)
    const changed = await updateMarkup(
      target,
      text === undefined ? { geometry } : { geometry, text }
    )
    setMarkups((list) => list.map((x) => (x.id === target ? changed : x)))
    return changed
  }
  const record = (op: Op) =>
    setHistory((h) => ({ past: [...h.past, op], future: [] }))

  const add = useMutation({
    mutationFn: (body: {
      type: MarkupType
      geometry: Geometry
      text?: string | null
      style?: Style
    }) =>
      createMarkup({
        file_id: fileId,
        set_id: activeSet ?? undefined,
        page: pageNumber,
        style,
        ...body,
      }),
    onSuccess: (made) => {
      setMarkups((list) => [...list, made])
      record({ kind: 'create', markup: made })
      if (!sets.some((s) => s.id === made.set_id)) setActiveSet(made.set_id)
      refreshSets()
    },
    onError: handleServerError,
  })
  const move = useMutation({
    mutationFn: ({ m, geometry }: { m: Markup; geometry: Geometry }) =>
      reshape(m.id, geometry),
    onSuccess: (changed, { m }) =>
      record({
        kind: 'update',
        markup: changed,
        before: m.geometry,
        after: changed.geometry,
      }),
    onError: (e) => {
      handleServerError(e)
      void queryClient.invalidateQueries({ queryKey: keys.markups(fileId) })
    },
  })
  const erase = useMutation({
    mutationFn: async (m: Markup) => {
      await remove(m.id)
      return m
    },
    onSuccess: (m) => {
      record({ kind: 'delete', markup: m })
      refreshSets()
    },
    onError: handleServerError,
  })
  const step = useMutation({
    mutationFn: async (direction: 'undo' | 'redo') => {
      const op = (direction === 'undo' ? history.past : history.future).slice(
        -1
      )[0]
      if (!op) return
      const forward = direction === 'redo'
      if (op.kind === 'create') {
        if (forward) await recreate(op.markup)
        else await remove(op.markup.id)
      } else if (op.kind === 'delete') {
        if (forward) await remove(op.markup.id)
        else await recreate(op.markup)
      } else {
        await reshape(op.markup.id, forward ? op.after : op.before)
      }
      setHistory((h) =>
        forward
          ? { past: [...h.past, op], future: h.future.slice(0, -1) }
          : { past: h.past.slice(0, -1), future: [...h.future, op] }
      )
      refreshSets()
    },
    onError: handleServerError,
  })
  const calibrate = useMutation({
    mutationFn: (body: {
      points: Point[]
      real_distance: number
      unit: string
    }) =>
      unwrap(
        api.PUT('/api/v1/markups/calibrations/{file_id}/{page}', {
          params: { path: { file_id: fileId, page: pageNumber } },
          body: body as never,
        })
      ),
    onSuccess: () => {
      toast.success('Scale set for this page')
      void queryClient.invalidateQueries({
        queryKey: keys.calibrations(fileId),
      })
      void queryClient.invalidateQueries({ queryKey: keys.markups(fileId) })
    },
    onError: handleServerError,
  })

  const { mutate: runStep, isPending: stepping } = step
  const busy = add.isPending || stepping
  const selectedMarkup = markups.find((m) => m.id === selected) ?? null
  const mayChange = (m: Markup) =>
    m.author_id === session.id || can(session, 'markups.update')

  const deleteSelected = useCallback(() => {
    if (selectedMarkup && mayChange(selectedMarkup))
      erase.mutate(selectedMarkup)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMarkup])

  const finishPath = useCallback(() => {
    const pts = path.filter((p, i) => i === 0 || distance(p, path[i - 1]) > 1)
    const least = tool === 'measure_area' ? 3 : 2
    if (pts.length >= least)
      add.mutate({ type: tool as MarkupType, geometry: { points: pts } })
    setPath([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tool])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, [role="dialog"]')) return
      if (e.key === 'Escape') {
        setPath([])
        setDraft(null)
        setSelected(null)
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selected) {
        deleteSelected()
      } else if (e.key === 'Enter' && path.length) {
        finishPath()
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (!busy) runStep(e.shiftKey ? 'redo' : 'undo')
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault()
        if (!busy) runStep('redo')
      } else if (e.key === 'v' && !e.ctrlKey && !e.metaKey) {
        setTool('select')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, path, busy, runStep, deleteSelected, finishPath])

  // --- pointer handling ---------------------------------------------------------------------------------

  const at = (e: PointerEvent): Point => {
    const rect = svg.current!.getBoundingClientRect()
    return [(e.clientX - rect.left) / scale, (e.clientY - rect.top) / scale]
  }

  const onDown = (e: PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return
    const p = at(e)
    if (tool === 'select') {
      setSelected(null)
      return
    }
    if (!editable) return
    if (tool === 'text') {
      setPrompt({
        kind: 'text',
        geometry: { x: p[0], y: p[1], w: 200, h: fontSize * 1.4 },
      })
      return
    }
    if (tool === 'stamp') {
      setPrompt({
        kind: 'stamp',
        geometry: { x: p[0] - 85, y: p[1] - 30, w: 170, h: 60 },
      })
      return
    }
    if (CLICK_TOOLS.includes(tool)) {
      setPath((pts) => [...pts, p])
      return
    }
    if (DRAG_TOOLS.includes(tool)) {
      svg.current?.setPointerCapture(e.pointerId)
      drag.current = { start: p }
      setDraft(shapeFor(tool, p, p))
    }
  }

  const shapeFor = (t: Tool, a: Point, b: Point): Shape => {
    if (BOX_TOOLS.includes(t))
      return { type: t, geometry: normaliseBox(a, b), style }
    if (t === 'callout')
      return {
        type: 'callout',
        geometry: { x: b[0], y: b[1] - 15, w: 140, h: 30, anchor: a },
        style,
        text: '…',
      }
    if (t === 'calibrate')
      return {
        type: 'line',
        geometry: { points: [a, b] },
        style: { ...style, color: '#0ea5e9' },
      }
    return { type: t, geometry: { points: [a, b] }, style }
  }

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const p = at(e)
    if (CLICK_TOOLS.includes(tool) && path.length) setCursor(p)
    const d = drag.current
    if (!d) return
    if (moving && d.original) {
      setMoving({
        id: d.original.id,
        geometry: translate(
          d.original.geometry,
          p[0] - d.start[0],
          p[1] - d.start[1]
        ),
      })
    } else if (tool === 'freehand' && draft) {
      const pts = draft.geometry.points as Point[]
      if (distance(pts[pts.length - 1], p) > 1.5)
        setDraft({ ...draft, geometry: { points: [...pts, p] } })
    } else if (draft) {
      setDraft(shapeFor(tool, d.start, p))
    }
  }

  const onUp = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current
    drag.current = null
    if (!d) return
    if (moving && d.original) {
      const m = d.original
      if (JSON.stringify(moving.geometry) !== JSON.stringify(m.geometry))
        move.mutate({ m, geometry: moving.geometry })
      setMoving(null)
      return
    }
    const p = at(e)
    const shape = draft
    setDraft(null)
    if (!shape) return
    const far = distance(d.start, p) > 3
    if (tool === 'calibrate') {
      if (far) setPrompt({ kind: 'calibrate', points: [d.start, p] })
      return
    }
    if (tool === 'callout') {
      if (far) setPrompt({ kind: 'callout', geometry: shape.geometry })
      return
    }
    if (tool === 'freehand') {
      if ((shape.geometry.points as Point[]).length > 2)
        add.mutate({ type: 'freehand', geometry: shape.geometry })
      return
    }
    if (far) add.mutate({ type: tool as MarkupType, geometry: shape.geometry })
  }

  const onShapeDown = (m: Markup) => (e: PointerEvent<SVGGElement>) => {
    if (tool !== 'select') return
    e.stopPropagation()
    setSelected(m.id)
    if (!editable || !mayChange(m)) return
    svg.current?.setPointerCapture(e.pointerId)
    drag.current = { start: at(e), original: m }
    setMoving({ id: m.id, geometry: m.geometry })
  }

  // --- what's on the page -------------------------------------------------------------------------------

  const visible = markups.filter(
    (m) => m.page === pageNumber && !hidden.has(m.set_id)
  )
  const live = (type: string, pts: Point[]) =>
    calibration
      ? formatMeasurement(measure(type, pts, calibration.meters_per_unit))
      : undefined
  const pathPreview: Shape | null =
    path.length && CLICK_TOOLS.includes(tool)
      ? {
          type: tool,
          geometry: { points: cursor ? [...path, cursor] : path },
          style,
        }
      : null

  const pages = doc?.numPages ?? 0
  const visibleSets = sets.filter((s) => !hidden.has(s.id)).map((s) => s.id)

  return (
    <Page
      title={drawing?.name ?? 'Drawing'}
      description={
        drawing
          ? `Revision ${drawing.revision}. Markups are saved as you draw; measurements use each page's own scale.`
          : undefined
      }
      fixed
      actions={
        can(session, 'markups.export') ? (
          <Button size='sm' variant='outline' asChild>
            <a
              href={flattenedUrl(
                fileId,
                visibleSets.length === sets.length ? undefined : visibleSets
              )}
            >
              <Download /> PDF with markups
            </a>
          </Button>
        ) : null
      }
    >
      <div className='flex flex-wrap items-center gap-2'>
        <Toolbar
          tool={tool}
          onTool={(t) => {
            setTool(t)
            setPath([])
            setDraft(null)
          }}
          color={color}
          onColor={(c) => {
            setColor(c)
            if (selectedMarkup && mayChange(selectedMarkup))
              void updateMarkup(selectedMarkup.id, {
                style: { ...(selectedMarkup.style as Style), color: c },
              })
                .then((changed) =>
                  setMarkups((list) =>
                    list.map((x) => (x.id === changed.id ? changed : x))
                  )
                )
                .catch(handleServerError)
          }}
          width={width}
          onWidth={setWidth}
          fontSize={fontSize}
          onFontSize={setFontSize}
          stamps={stamps}
          stamp={stamp}
          onStamp={setStamp}
          canUndo={history.past.length > 0 && !busy}
          canRedo={history.future.length > 0 && !busy}
          onUndo={() => step.mutate('undo')}
          onRedo={() => step.mutate('redo')}
          canDelete={!!selectedMarkup && mayChange(selectedMarkup)}
          onDelete={deleteSelected}
          readOnly={!editable}
        />
        <div className='ms-auto flex items-center gap-1'>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Previous page'
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((n) => n - 1)}
          >
            <ChevronLeft className='size-4' />
          </Button>
          <span className='text-sm tabular-nums'>
            {pageNumber} / {pages || '…'}
          </span>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Next page'
            disabled={pageNumber >= pages}
            onClick={() => setPageNumber((n) => n + 1)}
          >
            <ChevronRight className='size-4' />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Zoom out'
            onClick={() =>
              setScale((s) => Math.max(0.25, +(s / 1.25).toFixed(3)))
            }
          >
            <ZoomOut className='size-4' />
          </Button>
          <span className='w-12 text-center text-sm tabular-nums'>
            {Math.round(scale * 100)}%
          </span>
          <Button
            size='icon'
            variant='ghost'
            className='size-8'
            aria-label='Zoom in'
            onClick={() => setScale((s) => Math.min(8, +(s * 1.25).toFixed(3)))}
          >
            <ZoomIn className='size-4' />
          </Button>
        </div>
      </div>
      <div className='flex min-h-0 flex-1 gap-3'>
        <div className='relative min-h-0 flex-1 overflow-auto rounded-md border bg-muted/40'>
          {error ? (
            <p className='p-4 text-sm text-destructive'>{error}</p>
          ) : null}
          {size ? (
            <div
              className='relative m-4 inline-block shadow-sm'
              style={{ width: size.w * scale, height: size.h * scale }}
            >
              <canvas ref={canvas} className='absolute inset-0 bg-white' />
              <svg
                ref={svg}
                className='absolute inset-0 touch-none select-none'
                width={size.w * scale}
                height={size.h * scale}
                viewBox={`0 0 ${size.w} ${size.h}`}
                style={{ cursor: tool === 'select' ? 'default' : 'crosshair' }}
                onPointerDown={onDown}
                onPointerMove={onMove}
                onPointerUp={onUp}
                onDoubleClick={() => CLICK_TOOLS.includes(tool) && finishPath()}
              >
                {visible.map((m) => (
                  <ShapeView
                    key={m.id}
                    shape={
                      moving?.id === m.id
                        ? { ...m, geometry: moving.geometry }
                        : m
                    }
                    selected={selected === m.id}
                    onPointerDown={
                      tool === 'select' ? onShapeDown(m) : undefined
                    }
                  />
                ))}
                {draft ? (
                  <ShapeView
                    shape={draft}
                    calibratedLabel={
                      draft.type === 'measure_length'
                        ? live(
                            'measure_length',
                            draft.geometry.points as Point[]
                          )
                        : tool === 'calibrate'
                          ? `${distance(...(draft.geometry.points as [Point, Point])).toFixed(1)} units`
                          : undefined
                    }
                  />
                ) : null}
                {pathPreview ? (
                  <ShapeView
                    shape={pathPreview}
                    calibratedLabel={live(
                      tool,
                      pathPreview.geometry.points as Point[]
                    )}
                  />
                ) : null}
              </svg>
            </div>
          ) : !error ? (
            <p className='p-4 text-sm text-muted-foreground'>
              Opening the drawing…
            </p>
          ) : null}
        </div>
        <SidePanel
          projectId={drawing?.project_id ?? null}
          sets={sets}
          hidden={hidden}
          onToggle={(id) =>
            setHidden((h) => {
              const next = new Set(h)
              if (next.has(id)) next.delete(id)
              else next.add(id)
              return next
            })
          }
          activeSet={activeSet}
          onActiveSet={setActiveSet}
          fileId={fileId}
          calibration={calibration ?? null}
          page={pageNumber}
          selected={selectedMarkup}
          editable={editable}
          onEditText={(m) =>
            setPrompt(
              m.type === 'callout'
                ? { kind: 'callout', geometry: { ...m.geometry, id: m.id } }
                : { kind: 'text', geometry: { ...m.geometry, id: m.id } }
            )
          }
        />
      </div>
      <PromptDialog
        key={promptSeq}
        prompt={prompt}
        initialText={
          prompt &&
          'geometry' in prompt &&
          typeof prompt.geometry.id === 'number'
            ? (markups.find((m) => m.id === prompt.geometry.id)?.text ?? '')
            : ''
        }
        stampLabel={stamps.find((s) => String(s.id) === stamp)}
        author={session.name}
        onClose={() => setPrompt(null)}
        onText={(kind, geometry, text) => {
          const { id, ...rest } = geometry
          if (typeof id === 'number') {
            const m = markups.find((x) => x.id === id)
            if (m)
              void updateMarkup(m.id, { text })
                .then((changed) =>
                  setMarkups((list) =>
                    list.map((x) => (x.id === changed.id ? changed : x))
                  )
                )
                .catch(handleServerError)
          } else {
            const lines = text.split('\n')
            const h =
              kind === 'stamp'
                ? rest.h
                : Math.max(fontSize * 1.4, lines.length * fontSize * 1.2 + 6)
            const longest = Math.max(...lines.map((l) => l.length))
            const w =
              kind === 'stamp'
                ? rest.w
                : Math.max(60, longest * fontSize * 0.55 + 10)
            const template = stamps.find((x) => String(x.id) === stamp)
            add.mutate({
              type: kind,
              geometry: { ...rest, w, h },
              text,
              style:
                kind === 'stamp' && template
                  ? { ...style, color: template.color }
                  : style,
            })
          }
          setPrompt(null)
        }}
        onCalibrate={(points, real, unit) => {
          calibrate.mutate({ points, real_distance: real, unit })
          setPrompt(null)
          setTool('select')
        }}
      />
    </Page>
  )
}

function PromptDialog({
  prompt,
  initialText,
  stampLabel,
  author,
  onClose,
  onText,
  onCalibrate,
}: {
  prompt: Prompt | null
  initialText: string
  stampLabel?: {
    label: string
    include_date: boolean
    include_author: boolean
    color: string
  }
  author: string
  onClose: () => void
  onText: (
    kind: 'text' | 'callout' | 'stamp',
    geometry: Geometry,
    text: string
  ) => void
  onCalibrate: (points: Point[], real: number, unit: string) => void
}) {
  const [text, setText] = useState(() => {
    if (prompt?.kind !== 'stamp' || !stampLabel) return initialText
    const meta = [
      stampLabel.include_date ? new Date().toLocaleDateString() : '',
      stampLabel.include_author ? author : '',
    ].filter(Boolean)
    return [stampLabel.label, ...(meta.length ? [meta.join(' · ')] : [])].join(
      '\n'
    )
  })
  const [real, setReal] = useState('')
  const [unit, setUnit] = useState('m')
  if (!prompt) return null
  const title = {
    text: 'Text note',
    callout: 'Callout',
    stamp: 'Stamp',
    calibrate: 'Set the scale',
  }[prompt.kind]
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {prompt.kind === 'calibrate' ? (
          <div className='grid gap-2 text-sm'>
            <p className='text-muted-foreground'>
              The line you picked is {distance(...prompt.points).toFixed(1)} PDF
              units long. How long is it on site?
            </p>
            <div className='flex gap-2'>
              <Input
                autoFocus
                type='number'
                min='0'
                step='any'
                aria-label='Real distance'
                value={real}
                onChange={(e) => setReal(e.target.value)}
              />
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger className='w-24' aria-label='Unit'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.keys(UNIT_METERS).map((u) => (
                    <SelectItem key={u} value={u}>
                      {u}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        ) : (
          <Textarea
            autoFocus
            rows={4}
            aria-label='Text'
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        )}
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          {prompt.kind === 'calibrate' ? (
            <Button
              disabled={!(Number(real) > 0)}
              onClick={() => onCalibrate(prompt.points, Number(real), unit)}
            >
              Set scale
            </Button>
          ) : (
            <Button
              disabled={!text.trim()}
              onClick={() =>
                onText(prompt.kind as 'text', prompt.geometry, text.trim())
              }
            >
              Save
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function MarkupViewerPage() {
  const { fileId } = useModuleParams()
  const id = Number(fileId)
  if (!Number.isInteger(id) || id < 1)
    return (
      <Page title='Markups'>
        <p className='text-sm text-muted-foreground'>No such drawing.</p>
      </Page>
    )
  return <Viewer key={id} fileId={id} />
}
