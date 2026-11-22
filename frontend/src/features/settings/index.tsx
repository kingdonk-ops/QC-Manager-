import { Outlet } from '@tanstack/react-router'
import { Monitor, Palette, ShieldCheck, UserCog } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Separator } from '@/components/ui/separator'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { NotificationBell } from '@/components/notification-bell'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { SidebarNav } from './components/sidebar-nav'

const sidebarNavItems = [
  {
    titleKey: 'settings.profile',
    href: '/settings',
    icon: <UserCog size={18} />,
  },
  {
    titleKey: 'settings.security',
    href: '/settings/security',
    icon: <ShieldCheck size={18} />,
  },
  {
    titleKey: 'settings.appearance',
    href: '/settings/appearance',
    icon: <Palette size={18} />,
  },
  {
    titleKey: 'settings.display',
    href: '/settings/display',
    icon: <Monitor size={18} />,
  },
]

export function Settings() {
  const { t } = useTranslation()
  const items = sidebarNavItems.map(({ titleKey, ...item }) => ({
    ...item,
    title: t(titleKey),
  }))
  return (
    <>
      {/* ===== Top Heading ===== */}
      <Header>
        <Search className='me-auto' />
        <NotificationBell />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>

      <Main fixed>
        <div className='space-y-0.5'>
          <h1 className='text-2xl font-bold tracking-tight md:text-3xl'>
            {t('settings.title')}
          </h1>
          <p className='text-muted-foreground'>{t('settings.description')}</p>
        </div>
        <Separator className='my-4 lg:my-6' />
        <div className='flex flex-1 flex-col space-y-2 overflow-hidden md:space-y-2 lg:flex-row lg:space-y-0 lg:space-x-12'>
          <aside className='top-0 lg:sticky lg:w-1/5'>
            <SidebarNav items={items} />
          </aside>
          <div className='flex w-full overflow-y-hidden p-1'>
            <Outlet />
          </div>
        </div>
      </Main>
    </>
  )
}
