import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { statusLabel } from './status'

const TONES: [RegExp, string][] = [
  [
    /^(closed|done|approved|verified|completed|answered|published|accepted|received|fully_received|pass|resolved)/,
    'bg-green-500/15 text-green-700 dark:text-green-400',
  ],
  [
    /^(rejected|overdue|critical|fail|occurred|cancelled|scrap)/,
    'bg-red-500/15 text-red-700 dark:text-red-400',
  ],
  [
    /^(open|in_progress|submitted|under_review|sent|shared|mitigating|investigation|review|active|partially)/,
    'bg-blue-500/15 text-blue-700 dark:text-blue-400',
  ],
  [
    /^(draft|pending|todo|to_do|wip|identified|planned|new)/,
    'bg-muted text-muted-foreground',
  ],
  [
    /^(high|warning|revise|on_hold|assessed|approved_as_noted)/,
    'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  ],
  // A check covered by a recorded override: neither a pass nor a fail.
  [
    /^overridden/,
    'bg-violet-500/15 text-violet-700 dark:text-violet-400',
  ],
]

/** A coloured pill for any status or priority value, by its meaning. */
export function StatusBadge({
  status,
  className,
}: {
  status?: string | null
  className?: string
}) {
  if (!status) return null
  const tone =
    TONES.find(([re]) => re.test(status.toLowerCase()))?.[1] ??
    'bg-muted text-muted-foreground'
  return (
    <Badge
      variant='outline'
      className={cn('border-transparent font-medium', tone, className)}
    >
      {statusLabel(status)}
    </Badge>
  )
}
