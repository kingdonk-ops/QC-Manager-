import { Bell, Monitor, Palette, Settings, UserCog, Wrench } from 'lucide-react'
import { type NavGroup } from '../types'

/** The shell's own entries, after the modules' groups. */
export const settingsNavGroup: NavGroup = {
  title: 'nav.group.settings',
  items: [
    {
      title: 'nav.settings',
      icon: Settings,
      items: [
        { title: 'Profile', url: '/settings', icon: UserCog },
        { title: 'Account', url: '/settings/account', icon: Wrench },
        { title: 'Appearance', url: '/settings/appearance', icon: Palette },
        { title: 'Notifications', url: '/settings/notifications', icon: Bell },
        { title: 'Display', url: '/settings/display', icon: Monitor },
      ],
    },
  ],
}
