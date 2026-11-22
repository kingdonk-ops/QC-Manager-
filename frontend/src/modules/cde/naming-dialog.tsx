import { useState } from 'react'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useSaveConvention, type CdeConvention } from './api'
import type { NamingField } from './naming'

type Draft = NamingField & { codesText: string }

const toText = (f: NamingField) =>
  (f.codes ?? [])
    .map((c) => (c.description ? `${c.code} ${c.description}` : c.code))
    .join('\n')

const fromText = (text: string) =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [code, ...rest] = line.split(/\s+/)
      return { code: code.toUpperCase(), description: rest.join(' ') }
    })

/** Edit the project's naming convention: ordered fields, allowed codes, separator. */
export function NamingDialog({
  projectId,
  convention,
  onClose,
}: {
  projectId: number
  convention: CdeConvention
  onClose: () => void
}) {
  const save = useSaveConvention(projectId)
  const [separator, setSeparator] = useState(convention.separator)
  const [requireApproval, setRequireApproval] = useState(
    convention.require_share_approval
  )
  const [fields, setFields] = useState<Draft[]>(() =>
    convention.fields.map((f) => ({
      ...(f as NamingField),
      codesText: toText(f as NamingField),
    }))
  )
  const update = (i: number, patch: Partial<Draft>) =>
    setFields((all) => all.map((f, j) => (j === i ? { ...f, ...patch } : f)))
  const move = (i: number, by: number) =>
    setFields((all) => {
      const next = [...all]
      const [f] = next.splice(i, 1)
      next.splice(i + by, 0, f)
      return next
    })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>Naming convention</DialogTitle>
          <DialogDescription>
            Fields in name order. List allowed codes one per line (code, then an
            optional description); leave the list empty to accept any value of
            the given length and characters. Example now:{' '}
            <span className='font-mono'>{convention.example}</span>
          </DialogDescription>
        </DialogHeader>
        <div className='flex flex-wrap items-center gap-4'>
          <div className='flex items-center gap-2'>
            <Label>Separator</Label>
            <Select value={separator} onValueChange={setSeparator}>
              <SelectTrigger size='sm' className='h-8 w-20'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['-', '_', '.'].map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Label className='flex items-center gap-2 font-normal'>
            <Switch
              checked={requireApproval}
              onCheckedChange={setRequireApproval}
            />
            Sharing WIP needs a task-team reviewer's check
          </Label>
        </div>
        <div className='grid gap-2'>
          {fields.map((f, i) => (
            <div key={i} className='grid gap-2 rounded-md border p-3'>
              <div className='flex flex-wrap items-end gap-2'>
                <div className='grid gap-1'>
                  <Label className='text-xs'>Label</Label>
                  <Input
                    className='h-8 w-40'
                    value={f.label}
                    onChange={(e) => update(i, { label: e.target.value })}
                  />
                </div>
                <div className='grid gap-1'>
                  <Label className='text-xs'>Key</Label>
                  <Input
                    className='h-8 w-28 font-mono'
                    value={f.key}
                    onChange={(e) =>
                      update(i, {
                        key: e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9_]/g, ''),
                      })
                    }
                  />
                </div>
                <div className='grid gap-1'>
                  <Label className='text-xs'>Length</Label>
                  <div className='flex items-center gap-1'>
                    <Input
                      type='number'
                      min={1}
                      max={20}
                      className='h-8 w-16'
                      value={f.min_length ?? 1}
                      onChange={(e) =>
                        update(i, { min_length: Number(e.target.value) })
                      }
                    />
                    –
                    <Input
                      type='number'
                      min={1}
                      max={20}
                      className='h-8 w-16'
                      value={f.max_length ?? 20}
                      onChange={(e) =>
                        update(i, { max_length: Number(e.target.value) })
                      }
                    />
                  </div>
                </div>
                <div className='grid gap-1'>
                  <Label className='text-xs'>Characters</Label>
                  <Select
                    value={f.charset ?? 'alnum'}
                    onValueChange={(v) =>
                      update(i, { charset: v as NamingField['charset'] })
                    }
                  >
                    <SelectTrigger size='sm' className='h-8 w-36'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value='alnum'>Letters and digits</SelectItem>
                      <SelectItem value='alpha'>Letters</SelectItem>
                      <SelectItem value='numeric'>Digits</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className='ms-auto flex'>
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label='Move up'
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                  >
                    <ArrowUp />
                  </Button>
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label='Move down'
                    disabled={i === fields.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    <ArrowDown />
                  </Button>
                  <Button
                    size='icon'
                    variant='ghost'
                    aria-label='Remove field'
                    onClick={() =>
                      setFields((all) => all.filter((_, j) => j !== i))
                    }
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
              <Textarea
                className='min-h-16 font-mono text-xs'
                placeholder='Allowed codes, e.g.&#10;DR Drawing&#10;M3 3D model'
                value={f.codesText}
                onChange={(e) => update(i, { codesText: e.target.value })}
              />
            </div>
          ))}
          <Button
            size='sm'
            variant='outline'
            className='w-fit'
            onClick={() =>
              setFields((all) => [
                ...all,
                {
                  key: `field${all.length + 1}`,
                  label: 'New field',
                  codes: [],
                  codesText: '',
                  min_length: 1,
                  max_length: 6,
                  charset: 'alnum',
                },
              ])
            }
          >
            <Plus /> Add field
          </Button>
        </div>
        <DialogFooter>
          <Button
            disabled={save.isPending || fields.length === 0}
            onClick={() =>
              save.mutate(
                {
                  separator: separator as '-' | '_' | '.',
                  require_share_approval: requireApproval,
                  fields: fields.map(({ codesText, ...f }) => ({
                    key: f.key,
                    label: f.label,
                    codes: fromText(codesText),
                    min_length: f.min_length ?? 1,
                    max_length: f.max_length ?? 20,
                    charset: f.charset ?? 'alnum',
                  })),
                },
                {
                  onSuccess: () => {
                    toast.success('Naming convention saved')
                    onClose()
                  },
                }
              )
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
