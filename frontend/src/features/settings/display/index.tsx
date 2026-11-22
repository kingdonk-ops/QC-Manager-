import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useInterfaceMode } from '@/modules/_runtime'
import { api, unwrap } from '@/api/client'
import { handleServerError } from '@/lib/handle-server-error'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ContentSection } from '../components/content-section'

export function SettingsDisplay() {
  const mode = useInterfaceMode()
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: (value: 'simple' | 'advanced') =>
      unwrap(
        api.PUT('/api/v1/platform/me/preferences/{key}', {
          params: { path: { key: 'interface' } },
          body: { value: { mode: value } },
        })
      ),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: ['platform', 'preferences'],
      }),
    onError: handleServerError,
  })

  return (
    <ContentSection
      title='Display'
      desc='How much of the app the menu shows you.'
    >
      <RadioGroup
        value={mode}
        onValueChange={(v) => save.mutate(v as 'simple' | 'advanced')}
        className='grid gap-3'
      >
        {(
          [
            [
              'simple',
              'Simple',
              'The screens most people use every day. Specialist screens are hidden from the menu.',
            ],
            [
              'advanced',
              'Advanced',
              'Every screen your access allows, including specialist and analysis tools.',
            ],
          ] as const
        ).map(([value, title, desc]) => (
          <Label
            key={value}
            htmlFor={value}
            className='flex items-start gap-3 rounded-md border p-3 font-normal'
          >
            <RadioGroupItem id={value} value={value} className='mt-0.5' />
            <span className='grid gap-0.5'>
              <span className='font-medium'>{title}</span>
              <span className='text-sm text-muted-foreground'>{desc}</span>
            </span>
          </Label>
        ))}
      </RadioGroup>
    </ContentSection>
  )
}
