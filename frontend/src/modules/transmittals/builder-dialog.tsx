import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
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
import { Textarea } from '@/components/ui/textarea'
import { PURPOSES, label, trKeys, type Transmittal } from './api'
import { Choice } from './choice'
import { ContactPicker, DocumentPicker } from './pickers'

/** Build a draft transmittal: subject, purpose, documents and recipients. */
export function BuilderDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number
  onClose: () => void
  onCreated: (t: Transmittal) => void
}) {
  const queryClient = useQueryClient()
  const [purpose, setPurpose] = useState<string>('for_information')
  const [files, setFiles] = useState<number[]>([])
  const [contacts, setContacts] = useState<number[]>([])
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      unwrap(api.POST('/api/v1/transmittals/', { body: body as never })),
    onSuccess: (t) => {
      toast.success(`${t.code} saved as a draft`)
      if (t.warnings?.length)
        toast.warning(
          `${t.warnings.length} document(s) are not the latest revision.`
        )
      void queryClient.invalidateQueries({ queryKey: trKeys.all(projectId) })
      onCreated(t)
    },
    onError: handleServerError,
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>New transmittal</DialogTitle>
        </DialogHeader>
        <form
          id='tr-builder'
          className='grid max-h-[70vh] grid-cols-2 gap-3 overflow-y-auto pe-1'
          onSubmit={(e) => {
            e.preventDefault()
            const data = new FormData(e.currentTarget)
            const text = (k: string) =>
              String(data.get(k) ?? '').trim() || undefined
            create.mutate({
              project_id: projectId,
              subject: text('subject'),
              notes: text('notes'),
              response_due: text('response_due'),
              purpose,
              file_ids: files,
              contact_ids: contacts,
            })
          }}
        >
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='tr-subject'>Subject</Label>
            <Input id='tr-subject' name='subject' required maxLength={300} />
          </div>
          <div className='grid gap-1.5'>
            <Label>Purpose</Label>
            <Choice
              value={purpose}
              onChange={setPurpose}
              options={PURPOSES.map((p) => ({ value: p, label: label(p) }))}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='tr-due'>Response due</Label>
            <Input id='tr-due' name='response_due' type='date' />
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label>Documents ({files.length})</Label>
            <DocumentPicker
              projectId={projectId}
              selected={files}
              onChange={setFiles}
            />
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label>Recipients ({contacts.length})</Label>
            <ContactPicker selected={contacts} onChange={setContacts} />
          </div>
          <div className='col-span-2 grid gap-1.5'>
            <Label htmlFor='tr-notes'>Notes</Label>
            <Textarea id='tr-notes' name='notes' rows={3} />
          </div>
        </form>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button type='submit' form='tr-builder' disabled={create.isPending}>
            Save draft
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
