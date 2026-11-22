import type { ReactNode } from 'react'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { NotificationBell } from '@/components/notification-bell'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ProjectSelector } from '@/components/project-selector'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

type PageProps = {
  title: ReactNode
  description?: ReactNode
  /** Buttons at the right of the title. */
  actions?: ReactNode
  /** Show the project selector in the top bar (for project-scoped pages). */
  projectScoped?: boolean
  children: ReactNode
  /** Let the content fill the height, for full-height grids. */
  fixed?: boolean
}

/** The standard page every module renders: top bar, title row, content. */
export function Page({
  title,
  description,
  actions,
  projectScoped,
  children,
  fixed,
}: PageProps) {
  return (
    <>
      <Header fixed>
        {projectScoped ? <ProjectSelector /> : null}
        <Search className='ms-auto' />
        <NotificationBell />
        <ThemeSwitch />
        <ConfigDrawer />
        <ProfileDropdown />
      </Header>
      <Main fixed={fixed} className='flex flex-1 flex-col gap-4'>
        <div className='flex flex-wrap items-end justify-between gap-2'>
          <div>
            <h2 className='text-xl font-semibold tracking-tight'>{title}</h2>
            {description ? (
              <p className='text-sm text-muted-foreground'>{description}</p>
            ) : null}
          </div>
          {actions ? (
            <div className='flex items-center gap-2'>{actions}</div>
          ) : null}
        </div>
        {children}
      </Main>
    </>
  )
}
