import { ArrowDown, ArrowUp, Plus, Trash2, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { useReviewers, type WorkflowStep } from './api'

type Props = {
  value: WorkflowStep[]
  onChange: (steps: WorkflowStep[]) => void
}

/** Ordered review steps; a step with several reviewers can decide in parallel. */
export function WorkflowBuilder({ value, onChange }: Props) {
  const { data: reviewers = [] } = useReviewers()
  const nameOf = (id: number) =>
    reviewers.find((r) => r.id === id)?.name ?? `User ${id}`

  const update = (index: number, patch: Partial<WorkflowStep>) =>
    onChange(value.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  const move = (index: number, by: number) => {
    const next = [...value]
    const [step] = next.splice(index, 1)
    next.splice(index + by, 0, step)
    onChange(next)
  }

  return (
    <div className='grid gap-2'>
      {value.map((step, index) => (
        <div
          key={index}
          className='grid gap-2 rounded-md border p-3'
          data-testid='workflow-step'
        >
          <div className='flex items-center gap-2'>
            <span className='flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold'>
              {index + 1}
            </span>
            <Input
              className='h-8'
              placeholder={`Step ${index + 1} name, e.g. Engineer`}
              value={step.name ?? ''}
              onChange={(e) => update(index, { name: e.target.value })}
            />
            <Button
              type='button'
              size='icon'
              variant='ghost'
              aria-label='Move up'
              disabled={index === 0}
              onClick={() => move(index, -1)}
            >
              <ArrowUp />
            </Button>
            <Button
              type='button'
              size='icon'
              variant='ghost'
              aria-label='Move down'
              disabled={index === value.length - 1}
              onClick={() => move(index, 1)}
            >
              <ArrowDown />
            </Button>
            <Button
              type='button'
              size='icon'
              variant='ghost'
              aria-label='Remove step'
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              <Trash2 />
            </Button>
          </div>
          <div className='flex flex-wrap items-center gap-1.5'>
            {step.reviewer_ids.map((id) => (
              <Badge key={id} variant='secondary' className='gap-1'>
                {nameOf(id)}
                <button
                  type='button'
                  aria-label={`Remove ${nameOf(id)}`}
                  onClick={() =>
                    update(index, {
                      reviewer_ids: step.reviewer_ids.filter((r) => r !== id),
                    })
                  }
                >
                  <X className='size-3' />
                </button>
              </Badge>
            ))}
            <Select
              value=''
              onValueChange={(v) =>
                update(index, {
                  reviewer_ids: [...step.reviewer_ids, Number(v)],
                })
              }
            >
              <SelectTrigger size='sm' className='h-7 w-44'>
                <SelectValue placeholder='Add reviewer' />
              </SelectTrigger>
              <SelectContent>
                {reviewers
                  .filter((r) => !step.reviewer_ids.includes(r.id))
                  .map((r) => (
                    <SelectItem key={r.id} value={String(r.id)}>
                      {r.name}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          {step.reviewer_ids.length > 1 ? (
            <Label className='flex items-center gap-2 text-xs font-normal'>
              <Switch
                checked={Boolean(step.parallel)}
                onCheckedChange={(parallel) => update(index, { parallel })}
              />
              {step.parallel
                ? 'Parallel: all reviewers decide at the same time'
                : 'Sequential: reviewers decide one after another'}
            </Label>
          ) : null}
        </div>
      ))}
      <Button
        type='button'
        size='sm'
        variant='outline'
        className='w-fit'
        onClick={() =>
          onChange([...value, { name: '', reviewer_ids: [], parallel: false }])
        }
      >
        <Plus /> Add step
      </Button>
    </div>
  )
}
