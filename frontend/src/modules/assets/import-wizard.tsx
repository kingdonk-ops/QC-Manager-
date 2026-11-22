import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { handleServerError } from '@/lib/handle-server-error'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  postForm,
  useRefresh,
  type ImportPreview,
  type ImportReport,
} from './api'

const SKIP = '__skip__'
type Target = 'components' | 'types'

const LABELS: Record<string, string> = {
  name: 'Name / tag',
  type: 'Type (name)',
  space: 'Space (name)',
  manufacturer: 'Manufacturer (email, name or company)',
  warranty_guarantor: 'Warranty guarantor',
  asset_kind: 'Fixed or moveable',
}
const label = (field: string) =>
  LABELS[field] ??
  field.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

/** Upload, map columns to fields, try it as a dry run, then import. */
export function ImportWizard({
  projectId,
  open,
  onClose,
}: {
  projectId: number
  open: boolean
  onClose: () => void
}) {
  const refresh = useRefresh(projectId)
  const [target, setTarget] = useState<Target>('components')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [onDuplicate, setOnDuplicate] = useState<'skip' | 'update'>('skip')
  const [extra, setExtra] = useState(false)
  const [report, setReport] = useState<ImportReport | null>(null)

  const reset = () => {
    setFile(null)
    setPreview(null)
    setReport(null)
    setMapping({})
  }
  const close = () => {
    reset()
    onClose()
  }

  const read = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData()
      form.set('file', f)
      form.set('target', target)
      return postForm<ImportPreview>(
        `/api/v1/assets/${projectId}/import/preview`,
        form
      )
    },
    onSuccess: (p) => {
      setPreview(p)
      setMapping(p.mapping)
      setReport(null)
    },
    onError: handleServerError,
  })
  const run = useMutation({
    mutationFn: (dryRun: boolean) => {
      const form = new FormData()
      form.set('file', file!)
      form.set('target', target)
      form.set('mapping', JSON.stringify(mapping))
      form.set('on_duplicate', onDuplicate)
      form.set('dry_run', String(dryRun))
      form.set('extra_as_attributes', String(extra))
      return postForm<ImportReport>(`/api/v1/assets/${projectId}/import`, form)
    },
    onSuccess: (r) => {
      setReport(r)
      if (!r.dry_run) {
        toast.success(`${r.created} created, ${r.updated} updated`)
        refresh()
      }
    },
    onError: handleServerError,
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>Import from Excel or CSV</DialogTitle>
          <DialogDescription>
            One row per {target === 'components' ? 'component' : 'product type'}
            . Rows whose name is already in the register are duplicates.
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-4 text-sm'>
          <div className='flex flex-wrap items-end gap-3'>
            <div className='grid gap-1'>
              <Label>Import</Label>
              <Select
                value={target}
                onValueChange={(v) => {
                  setTarget(v as Target)
                  reset()
                }}
              >
                <SelectTrigger className='w-40'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='components'>Components</SelectItem>
                  <SelectItem value='types'>Product types</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='import-file'>File</Label>
              <Input
                id='import-file'
                type='file'
                accept='.xlsx,.xlsm,.csv,.txt'
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null
                  setFile(f)
                  if (f) read.mutate(f)
                }}
              />
            </div>
          </div>
          {preview ? (
            <>
              <p className='text-muted-foreground'>
                {preview.rows} rows, {preview.columns.length} columns. Match
                each field to a column.
              </p>
              <div className='grid grid-cols-2 gap-2'>
                {preview.fields.map((field) => (
                  <div key={field} className='grid gap-1'>
                    <Label>{label(field)}</Label>
                    <Select
                      value={mapping[field] ?? SKIP}
                      onValueChange={(v) =>
                        setMapping((m) => {
                          const next = { ...m }
                          if (v === SKIP) delete next[field]
                          else next[field] = v
                          return next
                        })
                      }
                    >
                      <SelectTrigger className='h-8 w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={SKIP}>Not imported</SelectItem>
                        {preview.columns.map((c) => (
                          <SelectItem key={c} value={c}>
                            {c}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
              <div className='flex flex-wrap items-center gap-4'>
                <label className='flex items-center gap-2'>
                  <Checkbox
                    checked={extra}
                    onCheckedChange={(c) => setExtra(c === true)}
                  />
                  Keep other columns as attributes
                </label>
                <Select
                  value={onDuplicate}
                  onValueChange={(v) => setOnDuplicate(v as 'skip' | 'update')}
                >
                  <SelectTrigger className='h-8 w-52'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='skip'>Skip duplicates</SelectItem>
                    <SelectItem value='update'>Update duplicates</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {preview.sample.length ? (
                <div className='overflow-x-auto rounded-md border'>
                  <table className='w-full text-xs'>
                    <thead>
                      <tr>
                        {preview.columns.map((c) => (
                          <th
                            key={c}
                            className='border-b px-2 py-1 text-start font-medium whitespace-nowrap'
                          >
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.sample.map((row, i) => (
                        <tr key={i}>
                          {preview.columns.map((c) => (
                            <td
                              key={c}
                              className='border-b px-2 py-1 whitespace-nowrap'
                            >
                              {String(row[c] ?? '')}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </>
          ) : null}
          {report ? (
            <div className='grid gap-1 rounded-md bg-muted/50 p-3'>
              <p className='font-medium'>
                {report.dry_run ? 'Dry run: ' : 'Imported: '}
                {report.created} new, {report.updated} updated, {report.skipped}{' '}
                skipped
              </p>
              {[...(report.errors ?? []), ...(report.duplicates ?? [])]
                .slice(0, 20)
                .map((line) => (
                  <p key={line} className='text-xs text-muted-foreground'>
                    {line}
                  </p>
                ))}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={close}>
            {report && !report.dry_run ? 'Done' : 'Cancel'}
          </Button>
          <Button
            variant='outline'
            disabled={!preview || !mapping.name || run.isPending}
            onClick={() => run.mutate(true)}
          >
            Dry run
          </Button>
          <Button
            disabled={!preview || !mapping.name || run.isPending}
            onClick={() => run.mutate(false)}
          >
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
