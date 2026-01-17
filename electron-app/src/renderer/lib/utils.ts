import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Utility function to merge Tailwind CSS classes with clsx
 * This is the core utility used by all ShadCN UI components
 *
 * @param inputs - Class values to merge (strings, arrays, objects)
 * @returns Merged class string with Tailwind conflicts resolved
 *
 * @example
 * cn('px-2 py-1', condition && 'bg-blue-500', { 'text-white': isActive })
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
