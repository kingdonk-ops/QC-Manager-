/**
 * The "Views" dropdown for a register grid. The wiring is `useSavedViews` in `@/hooks/use-saved-views`:
 *
 *   const views = useSavedViews('ncr.register', projectId)
 *   <SavedViewsMenu views={views} />
 *   <DataGrid onGridReady={views.onGridReady} ... />
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronDown, Eye, Star, Trash2 } from 'lucide-react'
import { api, unwrap } from '@/api/client'
import { can, useSession } from '@/lib/session'
import {
  type SavedView,
  type SavedViews,
  type Visibility,
} from '@/hooks/use-saved-views'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect } from '@/components/native-select'

function useTeamOptions(open: boolean) {
  const session = useSession()
  const all = can(session, 'team.read')
  return useQuery({
    queryKey: ['teams', all ? 'all' : 'mine', 'options'],
    enabled: open,
    queryFn: async () =>
      all
        ? (
            await unwrap(
              api.GET('/api/v1/teams/', {
                params: { query: { items_per_page: 100 } },
              })
            )
          ).data
        : await unwrap(api.GET('/api/v1/teams/mine')),
  })
}

function SaveViewDialog({
  views,
  onClose,
}: {
  views: SavedViews
  onClose: () => void
}) {
  const session = useSession()
  const [name, setName] = useState('')
  const [visibility, setVisibility] = useState<Visibility>('private')
  const [teamIds, setTeamIds] = useState<number[]>([])
  const [isDefault, setIsDefault] = useState(false)
  const teams = useTeamOptions(visibility === 'team')
  const canShare = can(session, 'saved_views.share')
  const canManage = can(session, 'saved_views.manage')
  const options = [
    { value: 'private', label: 'Only me' },
    ...(canShare || canManage
      ? [
          { value: 'project', label: 'Everyone on the project' },
          { value: 'team', label: 'Teams…' },
        ]
      : []),
  ]
  const defaultAllowed =
    visibility === 'private' || (visibility === 'project' && canManage)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Save view</DialogTitle>
        </DialogHeader>
        <form
          id='save-view'
          className='grid gap-3'
          onSubmit={(e) => {
            e.preventDefault()
            views.save.mutate(
              {
                name: name.trim(),
                visibility,
                team_ids: visibility === 'team' ? teamIds : [],
                is_default: defaultAllowed && isDefault,
              },
              { onSuccess: onClose }
            )
          }}
        >
          <div className='grid gap-1.5'>
            <Label htmlFor='view-name'>Name</Label>
            <Input
              id='view-name'
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className='grid gap-1.5'>
            <Label htmlFor='view-visibility'>Shared with</Label>
            <NativeSelect
              id='view-visibility'
              options={options}
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
            />
          </div>
          {visibility === 'team' ? (
            <div className='grid max-h-40 gap-1 overflow-y-auto rounded-md border p-2 text-sm'>
              {(teams.data ?? []).map((team) => (
                <label key={team.id} className='flex items-center gap-2'>
                  <Checkbox
                    checked={teamIds.includes(team.id)}
                    onCheckedChange={(c) =>
                      setTeamIds((ids) =>
                        c === true
                          ? [...ids, team.id]
                          : ids.filter((i) => i !== team.id)
                      )
                    }
                  />
                  {team.name}
                </label>
              ))}
              {teams.data?.length === 0 ? (
                <p className='text-muted-foreground'>No teams.</p>
              ) : null}
            </div>
          ) : null}
          {defaultAllowed ? (
            <label className='flex items-center gap-2 text-sm'>
              <Checkbox
                checked={isDefault}
                onCheckedChange={(c) => setIsDefault(c === true)}
              />
              {visibility === 'project'
                ? 'Project default for this register'
                : 'Open this register with this view'}
            </label>
          ) : null}
        </form>
        <DialogFooter>
          <Button
            type='submit'
            form='save-view'
            disabled={
              !name.trim() ||
              views.save.isPending ||
              (visibility === 'team' && teamIds.length === 0)
            }
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const SHARING: Record<string, string> = {
  private: 'Only me',
  project: 'Project',
  team: 'Teams',
}

/** The "Views" dropdown: pick, save, update, make default, delete. Hidden without `saved_views.read`. */
export function SavedViewsMenu({ views }: { views: SavedViews }) {
  const session = useSession()
  const [saving, setSaving] = useState(false)
  if (!views.enabled) return null
  const { current } = views
  const mine = views.views.filter((v) => v.visibility === 'private')
  const shared = views.views.filter((v) => v.visibility !== 'private')
  const canCreate = can(session, 'saved_views.create')
  const row = (v: SavedView) => (
    <DropdownMenuItem key={v.id} onSelect={() => views.apply(v)}>
      {current?.id === v.id ? <Check /> : <span className='size-4' />}
      <span className='flex-1 truncate'>{v.name}</span>
      {v.is_default ? <Star className='text-amber-500' /> : null}
      {v.visibility !== 'private' ? (
        <span className='text-xs text-muted-foreground'>
          {SHARING[v.visibility]}
        </span>
      ) : null}
    </DropdownMenuItem>
  )
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size='sm' variant='outline' aria-label='Saved views'>
            <Eye />
            <span className='max-w-40 truncate'>
              {current ? current.name : 'Views'}
            </span>
            <ChevronDown />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='start' className='w-72'>
          <DropdownMenuItem onSelect={() => views.apply(null)}>
            {current ? <span className='size-4' /> : <Check />}
            Standard columns
          </DropdownMenuItem>
          {mine.length ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>My views</DropdownMenuLabel>
              {mine.map(row)}
            </>
          ) : null}
          {shared.length ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Shared</DropdownMenuLabel>
              {shared.map(row)}
            </>
          ) : null}
          {canCreate ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setSaving(true)}>
                Save as new view…
              </DropdownMenuItem>
            </>
          ) : null}
          {current?.can_edit ? (
            <>
              <DropdownMenuItem onSelect={views.saveCurrent}>
                Update “{current.name}”
              </DropdownMenuItem>
              {current.visibility === 'private' && !current.is_default ? (
                <DropdownMenuItem
                  onSelect={() =>
                    views.update.mutate({
                      id: current.id,
                      body: { is_default: true },
                    })
                  }
                >
                  <Star /> Make my default
                </DropdownMenuItem>
              ) : null}
              {current.is_default &&
              (current.visibility === 'private' ||
                can(session, 'saved_views.manage')) ? (
                <DropdownMenuItem
                  onSelect={() =>
                    views.update.mutate({
                      id: current.id,
                      body: { is_default: false },
                    })
                  }
                >
                  Stop using as default
                </DropdownMenuItem>
              ) : null}
              <DropdownMenuItem
                variant='destructive'
                onSelect={() => views.remove.mutate(current.id)}
              >
                <Trash2 /> Delete “{current.name}”
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      {saving ? (
        <SaveViewDialog views={views} onClose={() => setSaving(false)} />
      ) : null}
    </>
  )
}
