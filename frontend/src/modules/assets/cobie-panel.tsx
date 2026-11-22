import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  RefreshCw,
  XCircle,
} from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cobieUrl, keys } from './api'

/** Checks the register against COBie, sheet by sheet, and exports the workbook. */
export function CobiePanel({ projectId }: { projectId: number }) {
  const session = useSession()
  const {
    data: report,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: keys.cobie(projectId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/assets/{project_id}/cobie/validate', {
          params: { path: { project_id: projectId } },
        })
      ),
  })
  return (
    <div className='grid gap-3'>
      <div className='flex flex-wrap items-center gap-2'>
        {report ? (
          report.valid ? (
            <span className='flex items-center gap-1.5 text-sm text-green-700 dark:text-green-400'>
              <CheckCircle2 className='size-4' /> Ready for handover: no errors
            </span>
          ) : (
            <span className='flex items-center gap-1.5 text-sm text-red-700 dark:text-red-400'>
              <XCircle className='size-4' /> {report.errors} errors,{' '}
              {report.warnings} warnings
            </span>
          )
        ) : null}
        <Button
          size='sm'
          variant='outline'
          className='ms-auto'
          disabled={isFetching}
          onClick={() => void refetch()}
        >
          <RefreshCw className={cn(isFetching && 'animate-spin')} /> Check again
        </Button>
        {can(session, 'assets.export') ? (
          <Button size='sm' asChild>
            <a href={cobieUrl(projectId)}>
              <Download /> COBie workbook
            </a>
          </Button>
        ) : null}
      </div>
      <div className='grid gap-2 md:grid-cols-2'>
        {report?.sheets.map((sheet) => {
          const issues = sheet.issues ?? []
          const errors = issues.filter((i) => i.severity === 'error')
          const warnings = issues.filter((i) => i.severity === 'warning')
          return (
            <details
              key={sheet.sheet}
              className='rounded-md border p-2 text-sm'
              open={errors.length > 0}
            >
              <summary className='flex cursor-pointer items-center gap-2'>
                <span className='font-medium'>{sheet.sheet}</span>
                <span className='text-xs text-muted-foreground'>
                  {sheet.rows} rows
                </span>
                <span className='ms-auto flex gap-1'>
                  {errors.length ? (
                    <Badge variant='destructive'>{errors.length}</Badge>
                  ) : null}
                  {warnings.length ? (
                    <Badge className='bg-amber-500/15 text-amber-700 dark:text-amber-400'>
                      {warnings.length}
                    </Badge>
                  ) : null}
                  {!issues.length ? (
                    <CheckCircle2 className='size-4 text-green-600' />
                  ) : null}
                </span>
              </summary>
              <ul className='mt-2 grid max-h-60 gap-1 overflow-y-auto'>
                {issues.map((issue, i) => (
                  <li key={i} className='flex items-start gap-1.5 text-xs'>
                    {issue.severity === 'error' ? (
                      <XCircle className='mt-0.5 size-3.5 shrink-0 text-red-600' />
                    ) : (
                      <AlertTriangle className='mt-0.5 size-3.5 shrink-0 text-amber-600' />
                    )}
                    <span>
                      {issue.row ? (
                        <span className='font-medium'>{issue.row}: </span>
                      ) : null}
                      {issue.message}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )
        })}
      </div>
    </div>
  )
}
