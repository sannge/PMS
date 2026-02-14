/**
 * Time Utilities
 *
 * Functions for formatting dates and times in a human-readable way.
 */

import { useState, useEffect } from 'react'

/**
 * Format an ISO date string as relative time (e.g., "5 minutes ago").
 *
 * @param isoDate - ISO date string or null/undefined
 * @returns Human-readable relative time string
 */
export function formatRelativeTime(isoDate?: string | null): string {
  if (!isoDate) return 'Never saved'

  const date = new Date(isoDate)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffSecs / 60)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSecs < 10) return 'Just now'
  if (diffSecs < 60) return `${diffSecs} seconds ago`
  if (diffMins === 1) return '1 minute ago'
  if (diffMins < 60) return `${diffMins} minutes ago`
  if (diffHours === 1) return '1 hour ago'
  if (diffHours < 24) return `${diffHours} hours ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`

  // For older dates, show the actual date
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

/**
 * React hook that returns formatted relative time and auto-updates every minute.
 *
 * @param isoDate - ISO date string or null/undefined
 * @returns Human-readable relative time string that updates automatically
 */
export function useRelativeTime(isoDate?: string | null): string {
  const [text, setText] = useState(() => formatRelativeTime(isoDate))

  useEffect(() => {
    // Update immediately when date changes
    setText(formatRelativeTime(isoDate))

    // Update every minute for live updates
    const interval = setInterval(() => {
      setText(formatRelativeTime(isoDate))
    }, 60000)

    return () => clearInterval(interval)
  }, [isoDate])

  return text
}

/**
 * Format an ISO date string as absolute time (e.g., "Jan 25, 2026 at 3:45 PM").
 *
 * @param isoDate - ISO date string or null/undefined
 * @returns Human-readable absolute time string
 */
export function formatAbsoluteTime(isoDate?: string | null): string {
  if (!isoDate) return 'Unknown'

  const date = new Date(isoDate)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
