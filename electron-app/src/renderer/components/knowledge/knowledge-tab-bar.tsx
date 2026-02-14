/**
 * Knowledge Tab Bar
 *
 * Full-width horizontal tab bar for switching between knowledge scopes.
 * Shows "My Notes" as the first permanent tab, followed by application tabs.
 * Designed to span the entire screen width like OneNote.
 *
 * Tab values use the encoding: 'personal' | 'app:{id}'
 *
 * Includes overflow handling: when there are too many tabs to fit,
 * excess tabs are shown in a dropdown with search filtering.
 *
 * Application tabs show tooltips with full name and description on hover.
 */

import { useRef, useState, useEffect, useMemo } from 'react'
import { User, Building2, ChevronDown, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'

export interface KnowledgeTabBarProps {
  activeTab: string
  onTabChange: (tab: string) => void
  applicationsWithDocs: Array<{ id: string; name: string; description?: string | null }>
  /** Show skeleton loading state */
  isLoading?: boolean
}

function TabSkeleton(): JSX.Element {
  return (
    <div className="flex items-center gap-2 px-4 py-2 shrink-0">
      <div className="h-4 w-4 rounded bg-muted animate-pulse" />
      <div className="h-4 w-16 rounded bg-muted animate-pulse" />
    </div>
  )
}

export function KnowledgeTabBar({
  activeTab,
  onTabChange,
  applicationsWithDocs,
  isLoading = false,
}: KnowledgeTabBarProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const [visibleCount, setVisibleCount] = useState(Infinity)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Track available width and calculate how many app tabs fit
  useEffect(() => {
    if (!containerRef.current) return

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0
      // Layout budget:
      // - "My Notes" tab: ~100px
      // - Overflow dropdown button: ~120px
      // - Each app tab: ~140px (icon + name + padding)
      // - Some padding: ~20px
      const availableWidth = width - 100 - 120 - 20
      const tabWidth = 140
      const count = Math.max(0, Math.floor(availableWidth / tabWidth))
      setVisibleCount(count)
    })

    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  const visibleApps = applicationsWithDocs.slice(0, visibleCount)
  const overflowApps = applicationsWithDocs.slice(visibleCount)
  const hasOverflow = overflowApps.length > 0

  // Filter overflow apps by search query
  const filteredOverflowApps = useMemo(() => {
    if (!searchQuery.trim()) return overflowApps
    const query = searchQuery.toLowerCase()
    return overflowApps.filter((app) =>
      app.name.toLowerCase().includes(query)
    )
  }, [overflowApps, searchQuery])

  // Reset search when dropdown closes
  useEffect(() => {
    if (!dropdownOpen) {
      setSearchQuery('')
    }
  }, [dropdownOpen])

  // Find active overflow app name for dropdown button
  const activeOverflowApp = overflowApps.find(
    (app) => activeTab === `app:${app.id}`
  )

  const handleTabClick = (tabValue: string) => {
    onTabChange(tabValue)
  }

  const handleOverflowItemClick = (appId: string) => {
    onTabChange(`app:${appId}`)
    setDropdownOpen(false)
  }

  return (
    <div
      ref={containerRef}
      className="flex items-center w-full border-b border-border bg-muted/30"
    >
      {/* My Notes tab - always visible */}
      <button
        onClick={() => handleTabClick('personal')}
        className={cn(
          'flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors shrink-0',
          activeTab === 'personal'
            ? 'border-primary text-foreground bg-background'
            : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50'
        )}
      >
        <User className="h-4 w-4" />
        <span>My Notes</span>
      </button>

      {/* Loading skeletons for application tabs */}
      {isLoading && applicationsWithDocs.length === 0 && (
        <>
          <TabSkeleton />
          <TabSkeleton />
        </>
      )}

      {/* Visible application tabs with tooltips */}
      <TooltipProvider delayDuration={300}>
        {visibleApps.map((app) => (
          <Tooltip key={app.id}>
            <TooltipTrigger asChild>
              <button
                onClick={() => handleTabClick(`app:${app.id}`)}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors shrink-0',
                  activeTab === `app:${app.id}`
                    ? 'border-primary text-foreground bg-background'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50'
                )}
              >
                <Building2 className="h-4 w-4" />
                <span className="max-w-[120px] truncate">{app.name}</span>
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs">
              <p className="font-medium">{app.name}</p>
              {app.description && (
                <p className="text-xs text-muted-foreground mt-1">{app.description}</p>
              )}
            </TooltipContent>
          </Tooltip>
        ))}
      </TooltipProvider>

      {/* Spacer to push overflow dropdown to the right when there's room */}
      <div className="flex-1" />

      {/* Overflow dropdown with search */}
      {hasOverflow && (
        <Popover open={dropdownOpen} onOpenChange={setDropdownOpen}>
          <PopoverTrigger asChild>
            <button
              className={cn(
                'flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 transition-colors shrink-0 mr-2',
                activeOverflowApp
                  ? 'border-primary text-foreground bg-background'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50'
              )}
            >
              {activeOverflowApp ? (
                <>
                  <Building2 className="h-4 w-4" />
                  <span className="max-w-[100px] truncate">
                    {activeOverflowApp.name}
                  </span>
                </>
              ) : (
                <span>More Apps</span>
              )}
              <ChevronDown className="h-4 w-4" />
              {!activeOverflowApp && (
                <span className="ml-1 text-xs bg-muted rounded-full px-1.5 py-0.5">
                  {overflowApps.length}
                </span>
              )}
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="end"
            className="w-64 p-0"
            onOpenAutoFocus={(e) => e.preventDefault()}
          >
            {/* Search input */}
            <div className="p-2 border-b border-border">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search applications..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-8 text-sm"
                  autoFocus
                />
              </div>
            </div>

            {/* Application list */}
            <ScrollArea className="max-h-[300px]">
              <div className="p-1">
                {filteredOverflowApps.length === 0 ? (
                  <div className="py-4 text-center text-sm text-muted-foreground">
                    No applications found
                  </div>
                ) : (
                  filteredOverflowApps.map((app) => (
                    <button
                      key={app.id}
                      onClick={() => handleOverflowItemClick(app.id)}
                      className={cn(
                        'flex flex-col items-start w-full px-2 py-1.5 text-sm rounded-md transition-colors text-left',
                        activeTab === `app:${app.id}`
                          ? 'bg-accent text-accent-foreground'
                          : 'hover:bg-muted'
                      )}
                    >
                      <div className="flex items-center gap-2 w-full">
                        <Building2 className="h-4 w-4 shrink-0" />
                        <span className="truncate">{app.name}</span>
                      </div>
                      {app.description && (
                        <span className="text-xs text-muted-foreground ml-6 line-clamp-2">
                          {app.description}
                        </span>
                      )}
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}

export default KnowledgeTabBar
