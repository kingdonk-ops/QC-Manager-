/**
 * Scan-to-locate: read a barcode or QR code with the camera where the browser has `BarcodeDetector`,
 * otherwise type it (or use a handheld scanner, which types into the field). NFC is Android only (deferred).
 */
import { useEffect, useRef, useState } from 'react'
import { Camera, ScanLine } from 'lucide-react'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type Item, lookupItem } from './api'
import type { TermFn } from './terminology'

type Detected = { rawValue: string }
type Detector = { detect: (source: CanvasImageSource) => Promise<Detected[]> }
type DetectorClass = new (options?: { formats?: string[] }) => Detector

function detectorClass(): DetectorClass | null {
  const w = window as unknown as { BarcodeDetector?: DetectorClass }
  return w.BarcodeDetector ?? null
}

const cameraScanAvailable = () =>
  detectorClass() !== null && Boolean(navigator.mediaDevices?.getUserMedia)

function CameraScanner({ onValue }: { onValue: (value: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const Klass = detectorClass()
    if (!Klass) return
    let stream: MediaStream | null = null
    let timer: number | undefined
    let stopped = false
    const detector = new Klass()
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then(async (s) => {
        if (stopped) return s.getTracks().forEach((t) => t.stop())
        stream = s
        if (!video.current) return
        video.current.srcObject = s
        await video.current.play().catch(() => undefined)
        timer = window.setInterval(async () => {
          if (!video.current || video.current.readyState < 2) return
          try {
            const found = await detector.detect(video.current)
            if (found[0]?.rawValue) onValue(found[0].rawValue)
          } catch {
            /* a frame the detector can't read: try the next one */
          }
        }, 300)
      })
      .catch(() =>
        setError('The camera is not available. Type the code instead.')
      )
    return () => {
      stopped = true
      window.clearInterval(timer)
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [onValue])
  return error ? (
    <p className='text-sm text-muted-foreground'>{error}</p>
  ) : (
    <video
      ref={video}
      muted
      playsInline
      className='aspect-video w-full rounded-md bg-black object-cover'
    />
  )
}

export function ScanDialog({
  projectId,
  term,
  onClose,
  onFound,
}: {
  projectId: number
  term: TermFn
  onClose: () => void
  onFound: (item: Item) => void
}) {
  const [value, setValue] = useState('')
  const [camera, setCamera] = useState(cameraScanAvailable)
  const [missing, setMissing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  const look = async (code: string) => {
    const trimmed = code.trim()
    if (!trimmed || busyRef.current) return
    busyRef.current = true
    setBusy(true)
    try {
      const item = await lookupItem(projectId, trimmed)
      if (item) {
        onFound(item)
        onClose()
      } else {
        setMissing(trimmed)
        setValue(trimmed)
        setCamera(false)
      }
    } catch (e) {
      handleServerError(e)
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }
  const lookRef = useRef(look)
  useEffect(() => {
    lookRef.current = look
  })
  const [onCameraValue] = useState(() => (v: string) => void lookRef.current(v))

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Scan to locate</DialogTitle>
          <DialogDescription>
            Finds the {term('noun.item').toLowerCase()} by its barcode, QR or
            NFC code, or by its tag.
          </DialogDescription>
        </DialogHeader>
        {camera ? <CameraScanner onValue={onCameraValue} /> : null}
        <form
          id='scan-form'
          className='grid gap-1.5'
          onSubmit={(e) => {
            e.preventDefault()
            void look(value)
          }}
        >
          <Label htmlFor='scan-value'>Code or tag</Label>
          <Input
            id='scan-value'
            autoFocus={!camera}
            autoComplete='off'
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setMissing(null)
            }}
          />
          {missing ? (
            <p className='text-sm text-destructive'>
              Nothing in this project has the code “{missing}”.
            </p>
          ) : null}
        </form>
        <DialogFooter className='gap-2'>
          {cameraScanAvailable() && !camera ? (
            <Button variant='outline' onClick={() => setCamera(true)}>
              <Camera /> Use camera
            </Button>
          ) : null}
          <Button
            type='submit'
            form='scan-form'
            disabled={!value.trim() || busy}
          >
            <ScanLine /> Locate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
