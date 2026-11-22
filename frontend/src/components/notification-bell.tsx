import { Link, useNavigate } from '@tanstack/react-router'
import {
  useMarkRead,
  useNotifications,
  useReadAll,
  useUnreadCount,
} from '@/modules/notifications/api'
import { Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

export function NotificationBell() {
  const navigate = useNavigate()
  const { data: count } = useUnreadCount()
  const { data } = useNotifications()
  const markRead = useMarkRead()
  const readAll = useReadAll()
  const unread = count?.unread ?? 0

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant='ghost'
          size='icon'
          className='relative rounded-full'
          aria-label={`Notifications, ${unread} unread`}
        >
          <Bell className='size-[1.2rem]' />
          {unread > 0 ? (
            <span className='absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white'>
              {unread > 99 ? '99+' : unread}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align='end' className='w-96 p-0'>
        <div className='flex items-center justify-between border-b px-3 py-2'>
          <span className='text-sm font-semibold'>Notifications</span>
          <Button
            size='sm'
            variant='ghost'
            className='h-7 text-xs'
            onClick={() => readAll.mutate()}
            disabled={!unread}
          >
            Mark all read
          </Button>
        </div>
        <div className='max-h-96 overflow-y-auto'>
          {data?.data.length ? null : (
            <p className='p-4 text-sm text-muted-foreground'>
              You're all caught up.
            </p>
          )}
          {data?.data.slice(0, 15).map((n) => (
            <button
              key={n.id}
              className={cn(
                'grid w-full gap-0.5 border-b px-3 py-2 text-start text-sm hover:bg-accent',
                !n.read_at && 'bg-blue-500/5'
              )}
              onClick={() => {
                if (!n.read_at) markRead.mutate({ id: n.id, read: true })
                if (n.link) void navigate({ to: n.link as never })
              }}
            >
              <span
                className={cn(
                  'flex items-start gap-2',
                  !n.read_at && 'font-medium'
                )}
              >
                {!n.read_at ? (
                  <span className='mt-1.5 size-2 shrink-0 rounded-full bg-blue-600' />
                ) : null}
                {n.title}
              </span>
              {n.body ? (
                <span className='line-clamp-2 text-xs text-muted-foreground'>
                  {n.body}
                </span>
              ) : null}
              <span className='text-[11px] text-muted-foreground'>
                {new Date(n.created_at).toLocaleString()}
              </span>
            </button>
          ))}
        </div>
        <Link
          to='/$'
          params={{ _splat: 'notifications' }}
          className='block px-3 py-2 text-center text-xs underline'
        >
          All notifications and preferences
        </Link>
      </PopoverContent>
    </Popover>
  )
}
