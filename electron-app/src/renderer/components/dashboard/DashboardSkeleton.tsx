/**
 * Dashboard loading skeleton matching the dashboard layout.
 */

import { Skeleton } from '@/components/ui/skeleton'

export function DashboardSkeleton(): JSX.Element {
  return (
    <div className="space-y-8" role="status" aria-label="Loading dashboard data">
      {/* Welcome banner skeleton */}
      <Skeleton className="h-40 w-full rounded-2xl" />

      {/* Stats grid skeleton */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <Skeleton className="h-12 w-12 rounded-xl" />
              {(i === 2 || i === 3) && <Skeleton className="h-6 w-16 rounded-full" />}
            </div>
            <div className="space-y-2">
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-4 w-24" />
            </div>
          </div>
        ))}
      </div>

      {/* Charts grid skeleton */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-card p-5 space-y-4">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ))}
      </div>

      {/* Lists grid skeleton */}
      <div className="grid gap-6 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-card p-5 space-y-3">
            <Skeleton className="h-5 w-36" />
            {Array.from({ length: 4 }).map((_, j) => (
              <div key={j} className="flex items-center gap-3 py-2">
                <Skeleton className="h-3 w-3 rounded-full" />
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-3 flex-1 max-w-[200px]" />
                <Skeleton className="h-5 w-14 rounded-full" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
