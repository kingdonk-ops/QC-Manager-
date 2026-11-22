import { Badge } from '@/components/ui/badge'

export function AccountTypeBadge({ type }: { type: 'staff' | 'external' }) {
  return type === 'staff' ? (
    <Badge variant='secondary'>Staff</Badge>
  ) : (
    <Badge
      variant='outline'
      className='border-amber-500/50 text-amber-700 dark:text-amber-400'
    >
      Client portal
    </Badge>
  )
}

export function SignInBadge({ method }: { method: 'entra' | 'password' }) {
  return (
    <Badge variant='outline' className='gap-1'>
      {method === 'entra' ? 'Microsoft' : 'Password'}
    </Badge>
  )
}

export function EntraTag() {
  return (
    <Badge
      variant='outline'
      className='h-5 px-1.5 text-[10px] text-sky-700 dark:text-sky-400'
    >
      Entra
    </Badge>
  )
}
