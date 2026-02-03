/**
 * Notes Page
 *
 * Main entry point for the Knowledge Base / Notes screen.
 * Wraps content in KnowledgeBaseProvider for shared UI state.
 *
 * Layout: sidebar on the left, editor panel on the right.
 * The sidebar provides tab bar, search, folder tree, and tag filter.
 * The editor panel shows the document editor with autosave.
 */

import { useCallback, useRef, useEffect, useState } from 'react'
import { FileText } from 'lucide-react'
import { KnowledgeBaseProvider, useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useDocument } from '@/hooks/use-documents'
import { useSaveDocumentContent } from '@/hooks/use-queries'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'
import { DocumentEditor } from '@/components/knowledge/document-editor'
import { SaveStatus } from '@/components/knowledge/SaveStatus'
import type { SaveStatus as SaveStatusType } from '@/hooks/use-auto-save'

/** Debounce delay for saving content changes (ms) */
const SAVE_DEBOUNCE_MS = 2000

/**
 * EditorPanel - Inner component for the document editor area.
 * Must be inside KnowledgeBaseProvider to access selectedDocumentId.
 */
function EditorPanel() {
  const userId = useAuthStore((s) => s.user?.id ?? '')
  const userName = useAuthStore((s) => s.user?.display_name ?? s.user?.email ?? '')
  const { selectedDocumentId } = useKnowledgeBase()

  // Document data for the editor
  const { data: document } = useDocument(selectedDocumentId)

  // Save mutation for content changes
  const saveMutation = useSaveDocumentContent()
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const rowVersionRef = useRef(1)

  // Save status state
  const [saveStatus, setSaveStatus] = useState<SaveStatusType>({ state: 'idle' })

  // Keep row version in sync
  useEffect(() => {
    if (document?.row_version) {
      rowVersionRef.current = document.row_version
    }
  }, [document?.row_version])

  // Reset save status when document changes
  useEffect(() => {
    setSaveStatus({ state: 'idle' })
  }, [selectedDocumentId])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
      }
    }
  }, [])

  const handleEditorChange = useCallback(
    (json: object) => {
      if (!selectedDocumentId) return

      // Debounced save
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
      }

      saveTimerRef.current = setTimeout(() => {
        setSaveStatus({ state: 'saving' })

        saveMutation.mutate(
          {
            documentId: selectedDocumentId,
            content_json: JSON.stringify(json),
            row_version: rowVersionRef.current,
          },
          {
            onSuccess: (data) => {
              if (data.row_version) {
                rowVersionRef.current = data.row_version
              }
              setSaveStatus({ state: 'saved', at: Date.now() })
            },
            onError: (error) => {
              setSaveStatus({ state: 'error', message: error.message })
            },
          }
        )
      }, SAVE_DEBOUNCE_MS)
    },
    [selectedDocumentId, saveMutation]
  )

  // Empty state when no document selected
  if (!selectedDocumentId || !document) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Select a document to start editing</p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Save status indicator */}
      <div className="flex items-center justify-end px-4 py-1 border-b bg-muted/30">
        <SaveStatus status={saveStatus} />
      </div>

      {/* Document editor */}
      <DocumentEditor
        content={document.content_json ? JSON.parse(document.content_json) : undefined}
        onChange={handleEditorChange}
        editable={true}
        placeholder="Start writing..."
        documentId={selectedDocumentId}
        userId={userId}
        userName={userName}
        className="flex-1"
      />
    </div>
  )
}

/**
 * NotesPage - Main component wrapped in provider.
 */
export function NotesPage(): JSX.Element {
  return (
    <KnowledgeBaseProvider>
      <div className="flex h-full">
        <KnowledgeSidebar />
        <main className="flex-1 flex flex-col">
          <EditorPanel />
        </main>
      </div>
    </KnowledgeBaseProvider>
  )
}

export default NotesPage
