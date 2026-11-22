import { useState } from 'react'
import { Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { type ImportReport, importProgress, useInvalidateEvm } from './api'

/** Progress from Excel/CSV (code, percent, actual hours): check first, then import. */
export function ImportDialog({
  projectId,
  dataDate,
}: {
  projectId: number
  dataDate: string
}) {
  const { t } = useTranslation()
  const refresh = useInvalidateEvm(projectId)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [date, setDate] = useState(dataDate)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (dryRun: boolean) => {
    if (!file) return
    setBusy(true)
    try {
      const result = await importProgress(projectId, file, date, dryRun)
      setReport(result)
      if (!dryRun) {
        refresh()
        toast.success(t('evm.imported', { count: result.saved }))
        if (!result.issues.length) setOpen(false)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) {
          setDate(dataDate)
          setReport(null)
          setFile(null)
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size='sm' variant='outline'>
          <Upload /> {t('evm.import')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('evm.import_title')}</DialogTitle>
          <DialogDescription>{t('evm.import_help')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='evm-import-date'>{t('evm.data_date')}</Label>
            <Input
              id='evm-import-date'
              type='date'
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='evm-import-file'>{t('evm.file')}</Label>
            <Input
              id='evm-import-file'
              type='file'
              accept='.xlsx,.csv'
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setReport(null)
              }}
            />
          </div>
          {report ? (
            <div className='rounded-md border p-3 text-sm'>
              <p>
                {t(report.dry_run ? 'evm.import_checked' : 'evm.import_done', {
                  rows: report.rows,
                  saved: report.saved,
                  issues: report.issues.length,
                })}
              </p>
              {report.issues.length ? (
                <ul className='mt-2 max-h-40 list-disc overflow-auto ps-5 text-red-600'>
                  {report.issues.map((i) => (
                    <li key={`${i.row}-${i.message}`}>
                      {t('evm.row', { row: i.row })}: {i.message}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button
            variant='outline'
            disabled={!file || busy}
            onClick={() => run(true)}
          >
            {t('evm.check')}
          </Button>
          <Button disabled={!file || busy} onClick={() => run(false)}>
            {t('evm.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
