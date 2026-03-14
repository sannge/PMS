/**
 * Chat message loading skeletons for session switching.
 */

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function ChatMessageSkeleton({ role }: { role: 'user' | 'assistant' }): JSX.Element {
  if (role === 'user') {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="space-y-1.5 max-w-[70%]">
          <Skeleton className="h-3 w-32 ml-auto" />
          <Skeleton className="h-3 w-20 ml-auto" />
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-2.5 px-4 py-2">
      <Skeleton className="h-5 w-5 rounded-md shrink-0" />
      <div className="space-y-1.5 flex-1">
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  )
}

export function ChatSkeleton(): JSX.Element {
  return (
    <div className={cn('flex flex-col gap-3 p-4 animate-in fade-in duration-300')}>
      <ChatMessageSkeleton role="user" />
      <ChatMessageSkeleton role="assistant" />
      <ChatMessageSkeleton role="user" />
      <ChatMessageSkeleton role="assistant" />
    </div>
  )
}
