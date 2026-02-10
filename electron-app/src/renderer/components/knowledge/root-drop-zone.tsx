/**
 * Root Drop Zone
 *
 * A droppable area that appears at the bottom of the tree during drag
 * operations. Dropping an item here moves it to the root level
 * (folder_id=null for documents, parent_id=null for folders).
 */

import { useDroppable } from '@dnd-kit/core'
import { cn } from '@/lib/utils'

export const ROOT_DROP_ZONE_ID = '__root-drop-zone__'

export function RootDropZone(): JSX.Element {
  const { setNodeRef, isOver } = useDroppable({ id: ROOT_DROP_ZONE_ID })

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'mx-2 mt-1 rounded-md border border-dashed py-2 text-center text-xs text-muted-foreground transition-colors',
        isOver ? 'border-primary bg-primary/10 text-primary' : 'border-transparent'
      )}
    >
      {isOver ? 'Drop here to move to root' : ''}
    </div>
  )
}
