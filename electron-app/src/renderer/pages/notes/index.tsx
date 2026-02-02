/**
 * Notes Page
 *
 * Main entry point for the Knowledge Base / Notes screen.
 * Wraps content in KnowledgeBaseProvider for shared UI state.
 *
 * Layout: sidebar on the left, main content area on the right.
 * The sidebar provides tab bar, search, folder tree, and tag filter.
 * The content area will host the document editor (placeholder for now).
 */

import { FileText } from 'lucide-react'
import { KnowledgeBaseProvider } from '@/contexts/knowledge-base-context'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'

export function NotesPage(): JSX.Element {
  return (
    <KnowledgeBaseProvider>
      <div className="flex h-full">
        <KnowledgeSidebar />
        <main className="flex-1 flex flex-col">
          {/* Main content area -- placeholder for future editor */}
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
            <FileText className="h-12 w-12 text-muted-foreground/30" />
            <p className="text-sm">Select a document to start editing</p>
          </div>
        </main>
      </div>
    </KnowledgeBaseProvider>
  )
}

export default NotesPage
