import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
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
import { type ImportPreview, type ImportReport, upload } from './api'

const NONE = '__none__'
const GAEB = /\.(x8[1-6]|xml)$/i

/**
 * Upload a spreadsheet, map its columns to fields (auto-detected from the headers), and import.
 * GAEB XML files skip the mapping when `gaeb` is set.
 */
export function ImportDialog({
  open,
  onOpenChange,
  title,
  previewUrl,
  importUrl,
  fields = {},
  gaeb,
  replaceOption,
  onDone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  previewUrl: string
  importUrl: string
  fields?: Record<string, string>
  gaeb?: boolean
  replaceOption?: boolean
  onDone: (report: ImportReport) => void
}) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setFile(null)
    setPreview(null)
    setMapping({})
    setReplace(false)
  }

  const choose = async (picked: File | null) => {
    setFile(picked)
    setPreview(null)
    if (!picked || (gaeb && GAEB.test(picked.name))) return
    try {
      const result = await upload<ImportPreview>(previewUrl, picked)
      setPreview(result)
      setMapping(result.mapping)
    } catch (error) {
      toast.error((error as Error).message)
    }
  }

  const run = async () => {
    if (!file) return
    setBusy(true)
    try {
      const form: Record<string, string> = {}
      if (preview) form.mapping = JSON.stringify(mapping)
      if (replaceOption) form.replace = String(replace)
      const report = await upload<ImportReport>(importUrl, file, {
        ...fields,
        ...form,
      })
      toast.success(t('boq.import_done', { count: report.created }))
      if (report.errors?.length)
        toast.warning(report.errors.slice(0, 5).join('\n'))
      onDone(report)
      reset()
      onOpenChange(false)
    } catch (error) {
      toast.error((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {gaeb ? '.xlsx, .csv, .x83 / .x84 (GAEB DA XML)' : '.xlsx, .csv'}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='boq-import-file'>{t('boq.import_file')}</Label>
            <Input
              id='boq-import-file'
              type='file'
              accept={gaeb ? '.xlsx,.csv,.x83,.x84,.x86,.xml' : '.xlsx,.csv'}
              onChange={(e) => void choose(e.target.files?.[0] ?? null)}
            />
          </div>
          {preview ? (
            <div className='grid gap-2'>
              <p className='text-sm font-medium'>
                {t('boq.import_mapping')} · {preview.rows}
              </p>
              {preview.fields.map((field) => (
                <div
                  key={field}
                  className='grid grid-cols-[10rem_1fr] items-center gap-2'
                >
                  <Label className='text-xs'>{t(`boq.field.${field}`)}</Label>
                  <Select
                    value={mapping[field] ?? NONE}
                    onValueChange={(column) =>
                      setMapping((m) => {
                        const next = { ...m }
                        if (column === NONE) delete next[field]
                        else next[field] = column
                        return next
                      })
                    }
                  >
                    <SelectTrigger className='h-8 w-full'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>
                        {t('boq.not_mapped')}
                      </SelectItem>
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
          ) : null}
          {replaceOption ? (
            <label className='flex items-center gap-2 text-sm'>
              <Checkbox
                checked={replace}
                onCheckedChange={(v) => setReplace(v === true)}
              />
              {t('boq.import_replace')}
            </label>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button disabled={!file || busy} onClick={() => void run()}>
            {t('boq.import_run')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
