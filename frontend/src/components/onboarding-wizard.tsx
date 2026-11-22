import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ProjectForm } from '@/modules/projects/project-form'
import { Check } from 'lucide-react'
import { toast } from 'sonner'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import { cn } from '@/lib/utils'
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

/** Modules each role starts with. Names that aren't installed are ignored. */
const ROLE_PRESETS: Record<
  string,
  {
    label: string
    hint: string
    modules: string[]
    mode: 'simple' | 'advanced'
  }
> = {
  commercial: {
    label: 'Commercial / QS',
    hint: 'Cost control, change, procurement and reporting',
    modules: [
      'cvr',
      'evm',
      'change_orders',
      'procurement',
      'contacts',
      'risk',
      'reporting',
      'portal',
      'tasks',
    ],
    mode: 'advanced',
  },
  project: {
    label: 'Project manager',
    hint: 'Schedule, tasks, RFIs, meetings and correspondence',
    modules: [
      'schedule',
      'tasks',
      'rfi',
      'meetings',
      'correspondence',
      'transmittals',
      'submittals',
      'contacts',
      'risk',
      'reporting',
      'portal',
    ],
    mode: 'advanced',
  },
  quality: {
    label: 'Quality & safety',
    hint: 'Inspections, NCRs, safety and site records',
    modules: ['inspections', 'ncr', 'safety', 'tasks', 'contacts', 'markups'],
    mode: 'simple',
  },
  documents: {
    label: 'Document control',
    hint: 'CDE, transmittals, submittals and correspondence',
    modules: [
      'cde',
      'transmittals',
      'submittals',
      'correspondence',
      'contacts',
      'markups',
    ],
    mode: 'simple',
  },
  everything: {
    label: 'Everything',
    hint: 'Every module this deployment has',
    modules: ['*'],
    mode: 'advanced',
  },
}

export function OnboardingWizard() {
  const session = useSession()
  const queryClient = useQueryClient()
  const { data: prefs, isSuccess } = useQuery({
    queryKey: ['platform', 'preferences'],
    queryFn: () =>
      unwrap(api.GET('/api/v1/platform/me/preferences')) as Promise<
        Record<string, Record<string, unknown>>
      >,
  })
  const canModules = can(session, 'platform.modules')
  const { data: modules = [] } = useQuery({
    queryKey: ['platform', 'modules', 'admin'],
    queryFn: () => unwrap(api.GET('/api/v1/modules')),
    enabled: canModules,
  })
  const [step, setStep] = useState(0)
  const [role, setRole] = useState('commercial')
  const [chosen, setChosen] = useState<Set<string> | null>(null)
  const [dismissed, setDismissed] = useState(false)

  const switchable = useMemo(
    () => modules.filter((m) => m.installed && !m.core),
    [modules]
  )
  const preset = ROLE_PRESETS[role]
  const selected =
    chosen ??
    new Set(
      switchable
        .filter(
          (m) => preset.modules.includes('*') || preset.modules.includes(m.name)
        )
        .map((m) => m.name)
    )

  const finish = useMutation({
    mutationFn: async () => {
      if (canModules) {
        for (const m of switchable) {
          const want = selected.has(m.name)
          if (want !== m.enabled)
            await unwrap(
              api.PATCH('/api/v1/modules/{name}/toggle', {
                params: { path: { name: m.name } },
                body: { enabled: want, cascade: true },
              })
            ).catch(() => undefined)
        }
      }
      await unwrap(
        api.PUT('/api/v1/platform/me/preferences/{key}', {
          params: { path: { key: 'interface' } },
          body: { value: { mode: preset.mode } },
        })
      )
      await unwrap(
        api.PUT('/api/v1/platform/me/preferences/{key}', {
          params: { path: { key: 'onboarding' } },
          body: { value: { done: true, role } },
        })
      )
    },
    onSuccess: () => {
      toast.success("You're set up")
      void queryClient.invalidateQueries({ queryKey: ['platform'] })
    },
  })

  const open =
    isSuccess &&
    !dismissed &&
    !prefs?.onboarding?.done &&
    session.account_type === 'staff' &&
    can(session, 'projects.create')
  if (!open) return null

  const steps = [
    'Welcome',
    'First project',
    ...(canModules ? ['Modules'] : []),
    'Done',
  ]
  const current = steps[step]

  return (
    <Dialog open onOpenChange={(o) => !o && setDismissed(true)}>
      <DialogContent className='max-w-2xl'>
        <div className='flex gap-2'>
          {steps.map((s, i) => (
            <div key={s} className='flex flex-1 items-center gap-2 text-xs'>
              <span
                className={cn(
                  'flex size-5 items-center justify-center rounded-full border text-[10px]',
                  i < step &&
                    'border-primary bg-primary text-primary-foreground',
                  i === step && 'border-primary font-semibold'
                )}
              >
                {i < step ? <Check className='size-3' /> : i + 1}
              </span>
              <span
                className={i === step ? 'font-medium' : 'text-muted-foreground'}
              >
                {s}
              </span>
            </div>
          ))}
        </div>

        {current === 'Welcome' ? (
          <DialogHeader>
            <DialogTitle>Welcome, {session.name.split(' ')[0]}</DialogTitle>
            <DialogDescription>
              Three quick steps: create your first project, choose the modules
              your team uses, and pick how much of the app the menu shows. You
              can change all of it later in Settings and Administration.
            </DialogDescription>
          </DialogHeader>
        ) : null}

        {current === 'First project' ? (
          <>
            <DialogHeader>
              <DialogTitle>Create your first project</DialogTitle>
              <DialogDescription>
                The region sets the currency and the default classification
                standard.
              </DialogDescription>
            </DialogHeader>
            <ProjectForm
              formId='onboarding-project'
              onCreated={() => setStep(step + 1)}
            />
          </>
        ) : null}

        {current === 'Modules' ? (
          <>
            <DialogHeader>
              <DialogTitle>What does your team do?</DialogTitle>
              <DialogDescription>
                We'll switch on the modules for that role. Untick any you don't
                need.
              </DialogDescription>
            </DialogHeader>
            <div className='grid grid-cols-2 gap-2 md:grid-cols-3'>
              {Object.entries(ROLE_PRESETS).map(([key, p]) => (
                <button
                  key={key}
                  className={cn(
                    'rounded-md border p-2 text-start text-sm',
                    role === key && 'border-primary bg-primary/5'
                  )}
                  onClick={() => {
                    setRole(key)
                    setChosen(null)
                  }}
                >
                  <span className='font-medium'>{p.label}</span>
                  <span className='block text-xs text-muted-foreground'>
                    {p.hint}
                  </span>
                </button>
              ))}
            </div>
            <div className='grid max-h-48 grid-cols-2 gap-1.5 overflow-y-auto'>
              {switchable.map((m) => (
                <label key={m.name} className='flex items-center gap-2 text-sm'>
                  <Checkbox
                    checked={selected.has(m.name)}
                    onCheckedChange={(v) => {
                      const next = new Set(selected)
                      if (v) next.add(m.name)
                      else next.delete(m.name)
                      setChosen(next)
                    }}
                  />
                  {m.display_name}
                </label>
              ))}
            </div>
          </>
        ) : null}

        {current === 'Done' ? (
          <DialogHeader>
            <DialogTitle>All set</DialogTitle>
            <DialogDescription>
              The menu now shows{' '}
              {preset.mode === 'simple'
                ? 'the everyday screens (Simple mode)'
                : 'every screen you can use (Advanced mode)'}
              . Switch modes any time in Settings → Display.
            </DialogDescription>
          </DialogHeader>
        ) : null}

        <DialogFooter className='gap-2'>
          <Button variant='ghost' onClick={() => setDismissed(true)}>
            Later
          </Button>
          {current === 'First project' ? (
            <>
              <Button variant='outline' onClick={() => setStep(step + 1)}>
                Skip
              </Button>
              <Button type='submit' form='onboarding-project'>
                Create project
              </Button>
            </>
          ) : current === 'Done' ? (
            <Button onClick={() => finish.mutate()} disabled={finish.isPending}>
              Finish
            </Button>
          ) : (
            <Button onClick={() => setStep(step + 1)}>Continue</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
