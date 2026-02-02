/**
 * Knowledge Tab Bar
 *
 * Horizontal tab bar for switching between knowledge scopes.
 * Shows "My Notes" as the first permanent tab, followed by
 * one tab per application that has documents.
 *
 * Uses Radix Tabs for accessible, keyboard-navigable tab switching.
 * Tab values use the encoding: 'personal' | 'app:{id}'
 */

import { User, Building2 } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

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
  return (
    <Tabs value={activeTab} onValueChange={onTabChange}>
      <TabsList className="w-full justify-start">
        <TabsTrigger value="personal" className="gap-1 text-xs">
          <User className="h-3.5 w-3.5 shrink-0" />
          <span>My Notes</span>
        </TabsTrigger>
        {applicationsWithDocs.map((app) => (
          <TabsTrigger
            key={app.id}
            value={`app:${app.id}`}
            className="gap-1 text-xs"
          >
            <Building2 className="h-3.5 w-3.5 shrink-0" />
            <span className="max-w-[120px] truncate">{app.name}</span>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

export default KnowledgeTabBar
