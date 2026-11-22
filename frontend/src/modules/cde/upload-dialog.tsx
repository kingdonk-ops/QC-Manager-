import { useState } from 'react'
import { toast } from 'sonner'
import { useCurrentProject } from '@/stores/use-current-project'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
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
import { Textarea } from '@/components/ui/textarea'
import { postForm, useConvention, useRefresh } from './api'
import { compose, parse, type Convention } from './naming'

/** Register a container: pick each naming field, see the name and any problem live. */
export function UploadDialog({
  projectId,
  onClose,
  onDone,
}: {
  projectId: number
  onClose: () => void
  onDone: (id: number) => void
}) {
  const project = useCurrentProject()
  const { data: convention } = useConvention(projectId)
  const refresh = useRefresh(projectId)
  const [values, setValues] = useState<Record<string, string>>(() => ({
    project: (project?.code ?? '').replace(/[^A-Za-z0-9]/g, '').slice(0, 6),
  }))
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  if (!convention) return null
  const rules = convention as Convention
  const { name, errors } = compose(rules, values)
  const valid = Object.keys(errors).length === 0 && file && title.trim()

  const pick = (f: File | null) => {
    setFile(f)
    if (!f) return
    const stem = f.name.replace(/\.[^.]+$/, '')
    const parsed = parse(rules, stem)
    if (parsed) setValues(parsed)
    if (!title) setTitle(stem)
  }

  const submit = async () => {
    if (!file) return
    setBusy(true)
    setServerError(null)
    try {
      const form = new FormData()
      form.set('file', file)
      form.set('project_id', String(projectId))
      form.set('title', title.trim())
      form.set(
        'fields',
        JSON.stringify(
          Object.fromEntries(
            rules.fields.map((f) => [f.key, values[f.key] ?? ''])
          )
        )
      )
      if (description) form.set('description', description)
      const doc = await postForm('/api/v1/cde/documents/', form)
      toast.success(`${doc.name} registered at ${doc.revision}`)
      refresh()
      onDone(doc.id)
    } catch (error) {
      setServerError(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>Upload to WIP</DialogTitle>
        </DialogHeader>
        <div className='grid gap-3'>
          <div className='grid gap-1.5'>
            <Label htmlFor='cde-file'>File</Label>
            <input
              id='cde-file'
              type='file'
              className='text-sm'
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
            <p className='text-xs text-muted-foreground'>
              A file already named by the convention fills the fields in.
            </p>
          </div>
          <div className='grid gap-2 sm:grid-cols-4'>
            {rules.fields.map((field) => (
              <div key={field.key} className='grid gap-1'>
                <Label className='text-xs'>{field.label}</Label>
                {field.codes?.length ? (
                  <Select
                    value={values[field.key] ?? ''}
                    onValueChange={(v) =>
                      setValues((s) => ({ ...s, [field.key]: v }))
                    }
                  >
                    <SelectTrigger
                      size='sm'
                      className={cn(
                        'h-8 w-full',
                        errors[field.key] && 'border-red-500'
                      )}
                      aria-label={field.label}
                    >
                      <SelectValue placeholder='Choose' />
                    </SelectTrigger>
                    <SelectContent>
                      {field.codes.map((c) => (
                        <SelectItem key={c.code} value={c.code}>
                          {c.code}
                          {c.description ? ` · ${c.description}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    aria-label={field.label}
                    className={cn(
                      'h-8 uppercase',
                      errors[field.key] && 'border-red-500'
                    )}
                    value={values[field.key] ?? ''}
                    maxLength={field.max_length ?? 20}
                    onChange={(e) =>
                      setValues((s) => ({ ...s, [field.key]: e.target.value }))
                    }
                  />
                )}
              </div>
            ))}
          </div>
          <div className='rounded-md border bg-muted/40 px-3 py-2'>
            <div className='font-mono text-sm font-semibold tracking-wide'>
              {name}
            </div>
            {Object.values(errors).map((e) => (
              <p key={e} className='text-xs text-red-600'>
                {e}
              </p>
            ))}
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cde-title'>Title</Label>
            <Input
              id='cde-title'
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='cde-desc'>Description</Label>
            <Textarea
              id='cde-desc'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {serverError ? (
            <p className='text-sm text-red-600'>{serverError}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button disabled={!valid || busy} onClick={() => void submit()}>
            Register at P01
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
