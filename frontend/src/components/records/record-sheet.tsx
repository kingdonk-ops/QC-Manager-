import type { ReactNode } from 'react'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Attachments } from './attachments'
import { Comments } from './comments'

type RecordSheetProps = {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  badges?: ReactNode
  /** The record, for its Comments and Files tabs. Omit while creating a new one. */
  record?: { projectId: number; entityType: string; entityId: number }
  children: ReactNode
  /** Extra tabs after Details, e.g. `{ Responses: <Responses/> }`. */
  tabs?: Record<string, ReactNode>
  wide?: boolean
}

/** The standard side panel for one record: Details, any module tabs, then Comments and Files. */
export function RecordSheet({
  open,
  onClose,
  title,
  subtitle,
  badges,
  record,
  children,
  tabs,
  wide,
}: RecordSheetProps) {
  const extra = Object.entries(tabs ?? {})
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        className={
          wide ? 'w-full gap-0 sm:max-w-3xl' : 'w-full gap-0 sm:max-w-xl'
        }
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {subtitle ? <SheetDescription>{subtitle}</SheetDescription> : null}
          {badges ? (
            <div className='flex flex-wrap gap-1.5 pt-1'>{badges}</div>
          ) : null}
        </SheetHeader>
        <Tabs defaultValue='details' className='min-h-0 flex-1 px-4 pb-4'>
          <TabsList>
            <TabsTrigger value='details'>Details</TabsTrigger>
            {extra.map(([name]) => (
              <TabsTrigger key={name} value={name}>
                {name}
              </TabsTrigger>
            ))}
            {record ? (
              <TabsTrigger value='comments'>Comments</TabsTrigger>
            ) : null}
            {record ? <TabsTrigger value='files'>Files</TabsTrigger> : null}
          </TabsList>
          <div className='min-h-0 flex-1 overflow-y-auto pt-2'>
            <TabsContent value='details'>{children}</TabsContent>
            {extra.map(([name, node]) => (
              <TabsContent key={name} value={name}>
                {node}
              </TabsContent>
            ))}
            {record ? (
              <TabsContent value='comments'>
                <Comments {...record} />
              </TabsContent>
            ) : null}
            {record ? (
              <TabsContent value='files'>
                <Attachments {...record} />
              </TabsContent>
            ) : null}
          </div>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
