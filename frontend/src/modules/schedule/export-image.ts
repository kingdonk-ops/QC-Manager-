/**
 * Exporting the Gantt as a picture. The header and body SVGs are composed into one standalone SVG
 * with a WBS / name column on the left, then:
 *  - PNG: the SVG is drawn onto a canvas and saved;
 *  - PDF: the SVG opens in a print window, where the browser's "Save as PDF" writes a vector PDF.
 */
import { HEADER_HEIGHT, ROW_HEIGHT } from './gantt-math'

const LABEL_WIDTH = 300
const MAX_CANVAS_SIDE = 16_000

function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export type ExportRow = { wbs: string; name: string; depth: number }

/** One self-contained SVG document: title, labels, timescale and bars, on white. */
export function composeSvg(
  header: SVGSVGElement,
  body: SVGSVGElement,
  rows: ExportRow[],
  title: string
): { svg: string; width: number; height: number } {
  const chartWidth = Number(body.getAttribute('width')) || 0
  const bodyHeight = Number(body.getAttribute('height')) || 0
  const titleHeight = 28
  const width = LABEL_WIDTH + chartWidth
  const height = titleHeight + HEADER_HEIGHT + bodyHeight
  const labels = rows
    .map((r, i) => {
      const y =
        titleHeight + HEADER_HEIGHT + i * ROW_HEIGHT + ROW_HEIGHT / 2 + 4
      return (
        `<text x="8" y="${y}" font-family="monospace" font-size="10" fill-opacity="0.7">${escapeXml(r.wbs)}</text>` +
        `<text x="${70 + r.depth * 10}" y="${y}" font-size="11">${escapeXml(r.name.slice(0, 40))}</text>`
      )
    })
    .join('')
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}" color="#111827" fill="#111827" font-family="Inter, Arial, sans-serif">` +
    `<rect width="100%" height="100%" fill="#ffffff"/>` +
    `<text x="8" y="19" font-size="14" font-weight="600">${escapeXml(title)}</text>` +
    `<g transform="translate(0,${titleHeight})">` +
    `<text x="8" y="${HEADER_HEIGHT - 10}" font-size="11" font-weight="600">WBS</text>` +
    `<text x="70" y="${HEADER_HEIGHT - 10}" font-size="11" font-weight="600">Activity</text>` +
    `<line x1="0" x2="${width}" y1="${HEADER_HEIGHT}" y2="${HEADER_HEIGHT}" stroke="#d1d5db"/>` +
    `</g>` +
    labels +
    `<line x1="${LABEL_WIDTH - 0.5}" x2="${LABEL_WIDTH - 0.5}" y1="${titleHeight}" y2="${height}" stroke="#d1d5db"/>` +
    `<g transform="translate(${LABEL_WIDTH},${titleHeight})" font-size="11">${header.innerHTML}</g>` +
    `<g transform="translate(${LABEL_WIDTH},${titleHeight + HEADER_HEIGHT})" font-size="10">${body.innerHTML}</g>` +
    `</svg>`
  return { svg, width, height }
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function exportPng(
  composed: { svg: string; width: number; height: number },
  filename: string
): Promise<void> {
  const scale = Math.min(
    2,
    MAX_CANVAS_SIDE / composed.width,
    MAX_CANVAS_SIDE / composed.height
  )
  const url = URL.createObjectURL(
    new Blob([composed.svg], { type: 'image/svg+xml;charset=utf-8' })
  )
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('The chart could not be drawn.'))
      image.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = Math.ceil(composed.width * scale)
    canvas.height = Math.ceil(composed.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas is not available.')
    ctx.scale(scale, scale)
    ctx.drawImage(image, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/png')
    )
    if (!blob) throw new Error('The PNG could not be written.')
    download(blob, filename)
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Opens the chart in a print window; choose "Save as PDF" there. */
export function exportPdf(
  composed: { svg: string; width: number; height: number },
  title: string
): void {
  const win = window.open('', '_blank')
  if (!win) throw new Error('Allow pop-ups to print the chart.')
  win.document.write(
    `<!doctype html><html><head><title>${escapeXml(title)}</title>` +
      `<style>@page{size:landscape;margin:10mm}html,body{margin:0}svg{width:100%;height:auto}</style>` +
      `</head><body>${composed.svg}</body></html>`
  )
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 250)
}
