import { useEffect, useState } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useResultDrawerStore } from '@/stores/resultDrawerStore'

export function ResultDrawer() {
  const { isOpen, runId, close } = useResultDrawerStore()
  const [tab, setTab] = useState('findings')

  // Placeholder: replace with real API call once getJob / getJobResults exist in v3.ts
  // For now show a stub so App.tsx can mount this without errors
  useEffect(() => {
    if (!isOpen) setTab('findings')
  }, [isOpen])

  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) close() }}>
      <SheetContent side="right" className="w-full sm:max-w-[640px] lg:max-w-[50vw]">
        <SheetHeader>
          <SheetTitle className="truncate">{runId ? `Run ${runId.slice(0, 8)}…` : 'Loading…'}</SheetTitle>
          <SheetDescription className="flex items-center gap-2 text-xs opacity-70">
            {runId ?? '—'}
          </SheetDescription>
        </SheetHeader>

        <Tabs value={tab} onValueChange={setTab} className="mt-4">
          <TabsList>
            <TabsTrigger value="findings">Findings</TabsTrigger>
            <TabsTrigger value="trail">Trail</TabsTrigger>
            <TabsTrigger value="raw">Raw JSON</TabsTrigger>
          </TabsList>

          <TabsContent value="findings" className="mt-3 space-y-2 max-h-[60vh] overflow-auto">
            <p className="text-sm opacity-70">Findings will load here (Phase A wires this in Task 4 once getJobResults is available).</p>
          </TabsContent>

          <TabsContent value="trail" className="mt-3 text-sm opacity-70">
            Trail view will be wired in Phase B.
          </TabsContent>

          <TabsContent value="raw" className="mt-3 max-h-[60vh] overflow-auto">
            <pre className="text-xs whitespace-pre-wrap">{JSON.stringify({ runId }, null, 2)}</pre>
          </TabsContent>
        </Tabs>

        <SheetFooter className="mt-4">
          {/* DownloadMenu added in Task 3 */}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
