import { Monitor, Palette, Settings, ShieldCheck, UserCog } from 'lucide-react'
import { type NavGroup } from '../types'

/** The shell's own entries, after the modules' groups. */
export const settingsNavGroup: NavGroup = {
  title: 'nav.group.settings',
  items: [
    {
      title: 'nav.settings',
      icon: Settings,
      items: [
        { title: 'settings.profile', url: '/settings', icon: UserCog },
        {
          title: 'settings.security',
          url: '/settings/security',
          icon: ShieldCheck,
        },
        {
          title: 'settings.appearance',
          url: '/settings/appearance',
          icon: Palette,
        },
        { title: 'settings.display', url: '/settings/display', icon: Monitor },
      ],
    },
  ],
}
