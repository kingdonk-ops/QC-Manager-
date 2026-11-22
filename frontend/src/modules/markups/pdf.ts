/** pdf.js, loaded on demand with its worker. */
import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'

async function pdfjs() {
  const lib = await import('pdfjs-dist')
  if (!lib.GlobalWorkerOptions.workerSrc) {
    const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url')
    lib.GlobalWorkerOptions.workerSrc = worker.default
  }
  return lib
}

export function usePdfDocument(url: string) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    let loaded: PDFDocumentProxy | null = null
    void pdfjs()
      .then((lib) => lib.getDocument({ url, withCredentials: true }).promise)
      .then((d) => {
        loaded = d
        if (cancelled) void d.destroy()
        else setDoc(d)
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(
            e instanceof Error ? e.message : 'The PDF could not be opened.'
          )
      })
    return () => {
      cancelled = true
      if (loaded) void loaded.destroy()
    }
  }, [url])
  return { doc, error }
}

export function usePdfPage(doc: PDFDocumentProxy | null, pageNumber: number) {
  const [page, setPage] = useState<PDFPageProxy | null>(null)
  useEffect(() => {
    if (!doc) return
    let cancelled = false
    void doc.getPage(pageNumber).then((p) => {
      if (!cancelled) setPage(p)
    })
    return () => {
      cancelled = true
    }
  }, [doc, pageNumber])
  return page
}

/** Draws one page at a zoom, sharp on high-density screens. */
export function usePageCanvas(page: PDFPageProxy | null, scale: number) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const el = canvas.current
    if (!page || !el) return
    const ratio = window.devicePixelRatio || 1
    const viewport = page.getViewport({ scale: scale * ratio })
    el.width = Math.floor(viewport.width)
    el.height = Math.floor(viewport.height)
    el.style.width = `${Math.floor(viewport.width / ratio)}px`
    el.style.height = `${Math.floor(viewport.height / ratio)}px`
    const context = el.getContext('2d')
    if (!context) return
    const task = page.render({ canvasContext: context, viewport })
    task.promise.catch(() => undefined)
    return () => task.cancel()
  }, [page, scale])
  return canvas
}
