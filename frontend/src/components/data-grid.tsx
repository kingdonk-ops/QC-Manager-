/**
 * AG Grid with the app's look: compact rows, the shell's font and colours, light and dark.
 * Use it for every dense, spreadsheet-like screen.
 */
import { useMemo, type Ref } from 'react'
import {
  AllCommunityModule,
  ModuleRegistry,
  colorSchemeDark,
  colorSchemeLight,
  themeQuartz,
} from 'ag-grid-community'
import { AgGridReact, type AgGridReactProps } from 'ag-grid-react'
import { useTheme } from '@/context/theme-provider'

ModuleRegistry.registerModules([AllCommunityModule])

const base = themeQuartz.withParams({
  fontFamily: 'inherit',
  fontSize: 13,
  headerFontSize: 12,
  headerFontWeight: 600,
  rowHeight: 32,
  headerHeight: 34,
  spacing: 6,
  wrapperBorderRadius: 8,
  accentColor: '#2563eb',
})

const light = base.withPart(colorSchemeLight)
const dark = base
  .withPart(colorSchemeDark)
  .withParams({ backgroundColor: '#0a0a0a' })

type DataGridProps<T> = AgGridReactProps<T> & { ref?: Ref<AgGridReact<T>> }

export function DataGrid<T>({
  ref,
  defaultColDef,
  ...props
}: DataGridProps<T>) {
  const { resolvedTheme } = useTheme()
  const columnDefaults = useMemo(
    () => ({ sortable: true, resizable: true, filter: true, ...defaultColDef }),
    [defaultColDef]
  )
  return (
    <AgGridReact<T>
      ref={ref}
      theme={resolvedTheme === 'dark' ? dark : light}
      animateRows={false}
      stopEditingWhenCellsLoseFocus
      enterNavigatesVertically
      enterNavigatesVerticallyAfterEdit
      {...props}
      defaultColDef={columnDefaults}
    />
  )
}
