import { useMemo } from 'react'
import { useModuleNav } from '@/modules/_runtime'
import { useTranslation } from 'react-i18next'
import { settingsNavGroup } from './data/sidebar-data'
import { type NavGroup } from './types'

/** The sidebar and ⌘K menu: every registered module's entries the account may see, then settings. */
export function useNavGroups(): NavGroup[] {
  const { t } = useTranslation()
  const moduleGroups = useModuleNav()
  return useMemo(
    () => [
      ...moduleGroups.map(({ group, items }) => ({
        title: t(`nav.group.${group}`),
        items: items.map((item) => ({
          title: t(item.labelKey),
          url: item.to,
          icon: item.icon,
        })),
      })),
      {
        title: t(settingsNavGroup.title),
        items: settingsNavGroup.items.map((item) => ({
          ...item,
          title: t(item.title),
        })),
      },
    ],
    [moduleGroups, t]
  )
}
