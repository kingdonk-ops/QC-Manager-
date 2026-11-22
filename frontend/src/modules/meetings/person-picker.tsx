import { useState } from 'react'
import { useContacts } from '@/modules/contacts/api'
import { useAssignees } from '@/modules/tasks/api'
import { UserPlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import type { Person } from './api'

/** Picks an app user or a contact, searching both. Contacts on the project come first. */
export function PersonPicker({
  projectId,
  onPick,
  exclude,
  label,
  disabled,
}: {
  projectId: number
  onPick: (person: Person, name: string) => void
  /** Keys like `u:3` or `c:9` already chosen. */
  exclude?: Set<string>
  label?: string
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const { data: users = [] } = useAssignees(open)
  const filters = {
    search,
    type: 'all',
    company_id: null,
    tag: '',
  }
  const { data: onProject } = useContacts(
    { ...filters, project_id: projectId },
    1,
    open
  )
  const { data: everyone } = useContacts(
    { ...filters, project_id: null },
    1,
    open && search.length > 1
  )
  const q = search.toLowerCase()
  const shownUsers = users
    .filter((u) => !exclude?.has(`u:${u.id}`))
    .filter((u) => !q || `${u.name} ${u.email}`.toLowerCase().includes(q))
    .slice(0, 30)
  const projectIds = new Set(onProject?.data.map((c) => c.id))
  const contacts = [
    ...(onProject?.data ?? []),
    ...(everyone?.data ?? []).filter((c) => !projectIds.has(c.id)),
  ]
    .filter((c) => !exclude?.has(`c:${c.id}`))
    .slice(0, 40)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size='sm' variant='outline' disabled={disabled}>
          <UserPlus /> {label ?? t('meetings.add_person')}
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-80 p-0' align='start'>
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={t('meetings.search_people')}
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>{t('meetings.nobody_found')}</CommandEmpty>
            {shownUsers.length ? (
              <CommandGroup heading={t('meetings.users')}>
                {shownUsers.map((u) => (
                  <CommandItem
                    key={`u${u.id}`}
                    value={`u${u.id}`}
                    onSelect={() => {
                      onPick({ user_id: u.id }, u.name)
                      setOpen(false)
                    }}
                  >
                    <span className='truncate'>{u.name}</span>
                    <span className='ms-auto truncate text-xs text-muted-foreground'>
                      {u.email}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
            {contacts.length ? (
              <CommandGroup heading={t('meetings.contacts')}>
                {contacts.map((c) => (
                  <CommandItem
                    key={`c${c.id}`}
                    value={`c${c.id}`}
                    onSelect={() => {
                      onPick({ contact_id: c.id }, c.full_name)
                      setOpen(false)
                    }}
                  >
                    <span className='truncate'>{c.full_name}</span>
                    <span className='ms-auto truncate text-xs text-muted-foreground'>
                      {c.company_name ?? ''}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
