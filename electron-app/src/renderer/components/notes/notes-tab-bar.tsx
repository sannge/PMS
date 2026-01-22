/**
 * Notes Tab Bar Component
 *
 * Displays a horizontal tab bar for managing multiple open notes.
 *
 * Features:
 * - Tab display with note titles
 * - Active tab highlighting
 * - Close button on each tab
 * - Dirty indicator for unsaved changes
 * - Tab scrolling for overflow
 * - Context menu for tab actions
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import type { NoteTab } from '@/stores/notes-store'
import {
  X,
  Circle,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface NotesTabBarProps {
  /**
   * List of open tabs
   */
  tabs: NoteTab[]
  /**
   * ID of the currently active tab
   */
  activeTabId: string | null
  /**
   * Callback when a tab is selected
   */
  onSelectTab?: (tabId: string) => void
  /**
   * Callback when a tab is closed
   */
  onCloseTab?: (tabId: string) => void
  /**
   * Callback when closing all tabs
   */
  onCloseAllTabs?: () => void
  /**
   * Callback when closing other tabs
   */
  onCloseOtherTabs?: (tabId: string) => void
  /**
   * Callback when saving a tab
   */
  onSaveTab?: (tabId: string) => void
  /**
   * Optional className for the container
   */
  className?: string
}

interface TabContextMenuProps {
  tab: NoteTab
  position: { x: number; y: number }
  onClose: () => void
  onCloseTab: () => void
  onCloseOthers: () => void
  onCloseAll: () => void
  onSave?: () => void
}

// ============================================================================
// Tab Context Menu Component
// ============================================================================

function TabContextMenu({
  tab,
  position,
  onClose,
  onCloseTab,
  onCloseOthers,
  onCloseAll,
  onSave,
}: TabContextMenuProps): JSX.Element {
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault()
          onClose()
        }}
      />
      {/* Menu */}
      <div
        className={cn(
          'fixed z-50 min-w-[180px] rounded-md border border-border bg-popover p-1 shadow-md',
          'animate-in fade-in-0 zoom-in-95'
        )}
        style={{ top: position.y, left: position.x }}
      >
        {onSave && tab.isDirty && (
          <>
            <button
              onClick={() => {
                onSave()
                onClose()
              }}
              className={cn(
                'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none'
              )}
            >
              Save
            </button>
            <div className="my-1 h-px bg-border" />
          </>
        )}
        <button
          onClick={() => {
            onCloseTab()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none'
          )}
        >
          Close
        </button>
        <button
          onClick={() => {
            onCloseOthers()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none'
          )}
        >
          Close Others
        </button>
        <button
          onClick={() => {
            onCloseAll()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none'
          )}
        >
          Close All
        </button>
      </div>
    </>
  )
}

// ============================================================================
// Tab Component
// ============================================================================

interface TabProps {
  tab: NoteTab
  isActive: boolean
  onSelect: () => void
  onClose: () => void
  onContextMenu: (e: React.MouseEvent) => void
}

function Tab({
  tab,
  isActive,
  onSelect,
  onClose,
  onContextMenu,
}: TabProps): JSX.Element {
  const handleClose = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      onClose()
    },
    [onClose]
  )

  const handleMiddleClick = useCallback(
    (e: React.MouseEvent) => {
      // Middle mouse button
      if (e.button === 1) {
        e.preventDefault()
        onClose()
      }
    },
    [onClose]
  )

  return (
    <div
      className={cn(
        'group flex h-9 min-w-[120px] max-w-[200px] items-center gap-2 border-r border-border px-3',
        'cursor-pointer select-none',
        'hover:bg-accent/50',
        isActive
          ? 'bg-background border-b-2 border-b-primary'
          : 'bg-muted/30'
      )}
      onClick={onSelect}
      onMouseDown={handleMiddleClick}
      onContextMenu={onContextMenu}
      role="tab"
      aria-selected={isActive}
      tabIndex={isActive ? 0 : -1}
    >
      {/* Dirty Indicator */}
      {tab.isDirty && (
        <Circle className="h-2 w-2 flex-shrink-0 fill-current text-primary" />
      )}

      {/* Title */}
      <span className="flex-1 truncate text-sm">{tab.title}</span>

      {/* Close Button */}
      <button
        onClick={handleClose}
        className={cn(
          'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded',
          'opacity-0 group-hover:opacity-100',
          'hover:bg-accent text-muted-foreground hover:text-foreground',
          'focus:outline-none focus:opacity-100',
          // Always show if dirty
          tab.isDirty && 'opacity-100'
        )}
        tabIndex={-1}
        title="Close"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

// ============================================================================
// Notes Tab Bar Component
// ============================================================================

export function NotesTabBar({
  tabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onCloseAllTabs,
  onCloseOtherTabs,
  onSaveTab,
  className,
}: NotesTabBarProps): JSX.Element | null {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const [contextMenu, setContextMenu] = useState<{
    tab: NoteTab
    position: { x: number; y: number }
  } | null>(null)

  // Check scroll state
  const updateScrollState = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return

    setCanScrollLeft(container.scrollLeft > 0)
    setCanScrollRight(
      container.scrollLeft < container.scrollWidth - container.clientWidth - 1
    )
  }, [])

  // Monitor scroll and resize
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    updateScrollState()

    container.addEventListener('scroll', updateScrollState)
    window.addEventListener('resize', updateScrollState)

    return () => {
      container.removeEventListener('scroll', updateScrollState)
      window.removeEventListener('resize', updateScrollState)
    }
  }, [updateScrollState, tabs])

  // Scroll left
  const handleScrollLeft = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return
    container.scrollBy({ left: -200, behavior: 'smooth' })
  }, [])

  // Scroll right
  const handleScrollRight = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return
    container.scrollBy({ left: 200, behavior: 'smooth' })
  }, [])

  // Handle context menu
  const handleContextMenu = useCallback(
    (tab: NoteTab, e: React.MouseEvent) => {
      e.preventDefault()
      setContextMenu({
        tab,
        position: { x: e.clientX, y: e.clientY },
      })
    },
    []
  )

  // No tabs case
  if (tabs.length === 0) {
    return null
  }

  return (
    <div
      className={cn(
        'flex h-9 items-stretch border-b border-border bg-muted/50',
        className
      )}
      role="tablist"
      aria-label="Open notes"
    >
      {/* Scroll Left Button */}
      {canScrollLeft && (
        <button
          onClick={handleScrollLeft}
          className={cn(
            'flex h-full w-8 items-center justify-center border-r border-border',
            'text-muted-foreground hover:text-foreground hover:bg-accent/50',
            'focus:outline-none'
          )}
          tabIndex={-1}
          title="Scroll left"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      )}

      {/* Tabs Container */}
      <div
        ref={scrollContainerRef}
        className="flex flex-1 overflow-x-auto scrollbar-hide"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        {tabs.map((tab) => (
          <Tab
            key={tab.id}
            tab={tab}
            isActive={tab.id === activeTabId}
            onSelect={() => onSelectTab?.(tab.id)}
            onClose={() => onCloseTab?.(tab.id)}
            onContextMenu={(e) => handleContextMenu(tab, e)}
          />
        ))}
      </div>

      {/* Scroll Right Button */}
      {canScrollRight && (
        <button
          onClick={handleScrollRight}
          className={cn(
            'flex h-full w-8 items-center justify-center border-l border-border',
            'text-muted-foreground hover:text-foreground hover:bg-accent/50',
            'focus:outline-none'
          )}
          tabIndex={-1}
          title="Scroll right"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      )}

      {/* Tab Menu (for close all, etc.) */}
      {tabs.length > 1 && (
        <div className="flex items-center border-l border-border px-2">
          <button
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              setContextMenu({
                tab: tabs[0], // Dummy, we'll just use menu for close all
                position: { x: rect.right - 180, y: rect.bottom + 4 },
              })
            }}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded',
              'text-muted-foreground hover:text-foreground hover:bg-accent',
              'focus:outline-none'
            )}
            title="Tab actions"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <TabContextMenu
          tab={contextMenu.tab}
          position={contextMenu.position}
          onClose={() => setContextMenu(null)}
          onCloseTab={() => onCloseTab?.(contextMenu.tab.id)}
          onCloseOthers={() => onCloseOtherTabs?.(contextMenu.tab.id)}
          onCloseAll={() => onCloseAllTabs?.()}
          onSave={onSaveTab ? () => onSaveTab(contextMenu.tab.id) : undefined}
        />
      )}
    </div>
  )
}

export default NotesTabBar
