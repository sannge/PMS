/**
 * Time Utilities
 *
 * Functions for formatting dates and times in a human-readable way.
 */

import { useState, useEffect } from 'react'

/**
 * Parse a backend ISO date string, treating bare strings (without timezone) as UTC.
 * Backend sends ISO strings without timezone (e.g., "2024-01-15T10:30:00.123456")
 * which should be interpreted as UTC.
 */
export function parseBackendDate(dateString: string): Date {
  let s = dateString
  if (!s.endsWith('Z') && !s.includes('+') && !s.includes('-', 10)) {
    s = s + 'Z'
  }
  return new Date(s)
}

/**
 * Format an ISO date string as relative time (e.g., "5 minutes ago").
 *
 * @param isoDate - ISO date string or null/undefined
 * @returns Human-readable relative time string
 */
export function formatRelativeTime(isoDate?: string | null): string {
  if (!isoDate) return 'Never saved'

  const date = parseBackendDate(isoDate)
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

  // For older dates, show the actual date in local time
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

  const date = parseBackendDate(isoDate)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/**
 * Get the local timezone abbreviation (e.g., "CST", "EST", "PST") for a given date.
 */
export function getLocalTimezoneAbbr(d: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZoneName: 'short',
  }).formatToParts(d)
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? 'LT'
}

/**
 * Format an ISO date string as a date in local time (e.g., "Feb 24, 2026").
 */
export function formatLocalDate(isoDate: string): string {
  const date = parseBackendDate(isoDate)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Get today's date string in local time (YYYY-MM-DD format).
 */
export function getLocalToday(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Format a date string for an HTML date input (YYYY-MM-DD).
 * Uses string manipulation to avoid UTC date-only parsing bugs.
 */
export function formatDateForInput(dateString: string | null): string {
  if (!dateString) return ''
  // Extract date part only (handle both "YYYY-MM-DD" and "YYYY-MM-DDTHH:mm:ss" formats)
  const datePart = dateString.split('T')[0]
  const parts = datePart.split('-')
  if (parts.length !== 3) return ''
  // Validate it's a real date
  const [year, month, day] = parts.map(Number)
  if (isNaN(year) || isNaN(month) || isNaN(day)) return ''
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
