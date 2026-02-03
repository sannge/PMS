/**
 * Knowledge Tab Bar
 *
 * Horizontal tab bar for switching between knowledge scopes.
 * Shows "My Notes" as the first permanent tab, followed by
 * one tab per application that has documents.
 *
 * Uses Radix Tabs for accessible, keyboard-navigable tab switching.
 * Tab values use the encoding: 'personal' | 'app:{id}'
 *
 * Includes overflow handling: when the panel is too narrow to show all tabs,
 * excess tabs are hidden and accessible via a "..." dropdown menu.
 */

import { useRef, useState, useEffect } from 'react'
import { User, Building2, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export interface KnowledgeTabBarProps {
  activeTab: string
  onTabChange: (tab: string) => void
  applicationsWithDocs: Array<{ id: string; name: string }>
}

export function KnowledgeTabBar({
  activeTab,
  onTabChange,
  applicationsWithDocs,
}: KnowledgeTabBarProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const [visibleCount, setVisibleCount] = useState(Infinity)

  // Track available width and calculate how many app tabs fit
  useEffect(() => {
    if (!containerRef.current) return

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0
      // Layout budget:
      // - "My Notes" tab: ~100px
      // - Overflow dropdown button: ~40px
      // - Each app tab: ~128px (icon + truncated name + padding)
      const availableWidth = width - 100 - 40
      const tabWidth = 128
      const count = Math.max(0, Math.floor(availableWidth / tabWidth))
      setVisibleCount(count)
    })

    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  const visibleApps = applicationsWithDocs.slice(0, visibleCount)
  const overflowApps = applicationsWithDocs.slice(visibleCount)

  return (
    <div ref={containerRef} className="w-full">
      <Tabs value={activeTab} onValueChange={onTabChange}>
        <TabsList className="w-full justify-start overflow-hidden">
          <TabsTrigger value="personal" className="gap-1 text-xs shrink-0">
            <User className="h-3.5 w-3.5 shrink-0" />
            <span>My Notes</span>
          </TabsTrigger>

          {visibleApps.map((app) => (
            <TabsTrigger
              key={app.id}
              value={`app:${app.id}`}
              className="gap-1 text-xs shrink-0"
            >
              <Building2 className="h-3.5 w-3.5 shrink-0" />
              <span className="max-w-[100px] truncate">{app.name}</span>
            </TabsTrigger>
          ))}

          {overflowApps.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  className={cn(
                    'flex items-center justify-center h-8 w-8 rounded-md shrink-0',
                    'hover:bg-muted transition-colors'
                  )}
                  aria-label="More applications"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {overflowApps.map((app) => (
                  <DropdownMenuItem
                    key={app.id}
                    onClick={() => onTabChange(`app:${app.id}`)}
                    className={cn(
                      'gap-2',
                      activeTab === `app:${app.id}` && 'bg-accent'
                    )}
                  >
                    <Building2 className="h-3.5 w-3.5" />
                    <span>{app.name}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </TabsList>
      </Tabs>
    </div>
  )
}

export default KnowledgeTabBar
