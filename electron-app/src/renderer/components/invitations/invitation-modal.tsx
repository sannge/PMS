/**
 * Invitation Modal Component
 *
 * Modal dialog for sending invitations to users to join an application.
 *
 * Features:
 * - User search by email
 * - Role selection (owner, editor, viewer)
 * - Form validation
 * - Loading states
 * - Error handling
 * - Keyboard accessible
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as Select from '@radix-ui/react-select'
import { cn } from '@/lib/utils'
import { X, UserPlus, ChevronDown, Check, Search, Loader2, AlertCircle } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { useInvitationsStore, type ApplicationRole } from '@/stores/invitations-store'

// ============================================================================
// Types
// ============================================================================

/**
 * User search result for display in the modal
 */
export interface UserSearchResult {
  id: string
  email: string
  full_name: string | null
}

export interface InvitationModalProps {
  /**
   * Whether the modal is open
   */
  isOpen: boolean
  /**
   * Application ID to invite users to
   */
  applicationId: string
  /**
   * Application name for display
   */
  applicationName: string
  /**
   * Callback when modal should close
   */
  onClose: () => void
  /**
   * Callback when invitation is sent successfully
   */
  onInvitationSent?: (inviteeId: string, role: ApplicationRole) => void
  /**
   * Optional function to search users by email
   * If not provided, the component will use a default API call
   */
  searchUsers?: (email: string) => Promise<UserSearchResult[]>
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const ROLE_OPTIONS: { value: ApplicationRole; label: string; description: string }[] = [
  {
    value: 'editor',
    label: 'Editor',
    description: 'Can edit content but cannot delete the application',
  },
  {
    value: 'viewer',
    label: 'Viewer',
    description: 'Read-only access to application content',
  },
  {
    value: 'owner',
    label: 'Owner',
    description: 'Full access including delete and member management',
  },
]

// ============================================================================
// Component
// ============================================================================

export function InvitationModal({
  isOpen,
  applicationId,
  applicationName,
  onClose,
  onInvitationSent,
  searchUsers,
  className,
}: InvitationModalProps): JSX.Element {
  // State
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<UserSearchResult[]>([])
  const [selectedUser, setSelectedUser] = useState<UserSearchResult | null>(null)
  const [selectedRole, setSelectedRole] = useState<ApplicationRole>('editor')
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [showResults, setShowResults] = useState(false)

  // Refs
  const searchInputRef = useRef<HTMLInputElement>(null)
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Store hooks
  const token = useAuthStore((state) => state.token)
  const { sendInvitation, isSending, error: storeError, clearError } = useInvitationsStore()

  // Reset form when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('')
      setSearchResults([])
      setSelectedUser(null)
      setSelectedRole('editor')
      setIsSearching(false)
      setSearchError(null)
      setShowResults(false)
      clearError()
      // Focus search input after modal opens
      setTimeout(() => searchInputRef.current?.focus(), 100)
    }
  }, [isOpen, clearError])

  // Default user search function using API
  const defaultSearchUsers = useCallback(
    async (email: string): Promise<UserSearchResult[]> => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<UserSearchResult[]>(
        `/api/users/search?email=${encodeURIComponent(email)}`,
        token ? { Authorization: `Bearer ${token}` } : {}
      )

      if (response.status === 200 && response.data) {
        return response.data
      }

      // If API returns 404 or empty, return empty array
      if (response.status === 404) {
        return []
      }

      throw new Error('Failed to search users')
    },
    [token]
  )

  // Handle search input change with debounce
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setSearchQuery(query)
      setSelectedUser(null)
      setSearchError(null)

      // Clear previous timeout
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }

      // Don't search if query is too short
      if (query.length < 3) {
        setSearchResults([])
        setShowResults(false)
        return
      }

      // Debounce search
      searchTimeoutRef.current = setTimeout(async () => {
        setIsSearching(true)
        setShowResults(true)
        try {
          const searchFn = searchUsers || defaultSearchUsers
          const results = await searchFn(query)
          setSearchResults(results)
        } catch (err) {
          setSearchError(err instanceof Error ? err.message : 'Search failed')
          setSearchResults([])
        } finally {
          setIsSearching(false)
        }
      }, 300)
    },
    [searchUsers, defaultSearchUsers]
  )

  // Handle user selection
  const handleSelectUser = useCallback((user: UserSearchResult) => {
    setSelectedUser(user)
    setSearchQuery(user.email)
    setShowResults(false)
    setSearchResults([])
  }, [])

  // Handle form submission
  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()

      if (!selectedUser) {
        setSearchError('Please select a user to invite')
        return
      }

      const result = await sendInvitation(token, applicationId, {
        invitee_id: selectedUser.id,
        role: selectedRole,
      })

      if (result) {
        onInvitationSent?.(selectedUser.id, selectedRole)
        onClose()
      }
    },
    [selectedUser, selectedRole, token, applicationId, sendInvitation, onInvitationSent, onClose]
  )

  // Handle close
  const handleClose = useCallback(() => {
    // Clear any pending search
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    onClose()
  }, [onClose])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [])

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <Dialog.Portal>
        {/* Overlay */}
        <Dialog.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0'
          )}
        />

        {/* Content */}
        <Dialog.Content
          className={cn(
            'fixed left-[50%] top-[50%] z-50 w-full max-w-md translate-x-[-50%] translate-y-[-50%]',
            'rounded-lg border border-border bg-card p-6 shadow-lg',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            'data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]',
            'data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
            'duration-200',
            className
          )}
        >
          {/* Header */}
          <div className="mb-6">
            <Dialog.Title className="flex items-center gap-2 text-lg font-semibold">
              <UserPlus className="h-5 w-5 text-primary" />
              Invite User
            </Dialog.Title>
            <Dialog.Description className="mt-1 text-sm text-muted-foreground">
              Invite a user to collaborate on{' '}
              <span className="font-medium text-foreground">{applicationName}</span>
            </Dialog.Description>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* User Search */}
            <div className="space-y-2">
              <label htmlFor="user-search" className="text-sm font-medium">
                User Email
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  ref={searchInputRef}
                  id="user-search"
                  type="email"
                  value={searchQuery}
                  onChange={handleSearchChange}
                  onFocus={() => searchResults.length > 0 && setShowResults(true)}
                  placeholder="Search by email address..."
                  className={cn(
                    'w-full rounded-md border border-input bg-background py-2 pl-9 pr-3',
                    'text-sm placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    selectedUser && 'border-green-500 focus:ring-green-500'
                  )}
                  disabled={isSending}
                  autoComplete="off"
                />
                {isSearching && (
                  <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
                )}
                {selectedUser && !isSearching && (
                  <Check className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-green-500" />
                )}
              </div>

              {/* Search Results Dropdown */}
              {showResults && !selectedUser && (
                <div className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-md border border-border bg-popover shadow-md">
                  {isSearching ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      <span className="ml-2 text-sm text-muted-foreground">Searching...</span>
                    </div>
                  ) : searchResults.length > 0 ? (
                    <ul className="py-1">
                      {searchResults.map((user) => (
                        <li key={user.id}>
                          <button
                            type="button"
                            onClick={() => handleSelectUser(user)}
                            className={cn(
                              'w-full px-3 py-2 text-left text-sm',
                              'hover:bg-accent hover:text-accent-foreground',
                              'focus:bg-accent focus:text-accent-foreground focus:outline-none'
                            )}
                          >
                            <div className="font-medium">{user.email}</div>
                            {user.full_name && (
                              <div className="text-xs text-muted-foreground">{user.full_name}</div>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : searchQuery.length >= 3 ? (
                    <div className="py-4 text-center text-sm text-muted-foreground">
                      No users found with that email
                    </div>
                  ) : null}
                </div>
              )}

              {/* Selected User Display */}
              {selectedUser && (
                <div className="flex items-center gap-2 rounded-md bg-green-500/10 px-3 py-2 text-sm">
                  <Check className="h-4 w-4 text-green-500" />
                  <span>
                    <span className="font-medium">{selectedUser.full_name || selectedUser.email}</span>
                    {selectedUser.full_name && (
                      <span className="text-muted-foreground"> ({selectedUser.email})</span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedUser(null)
                      setSearchQuery('')
                      searchInputRef.current?.focus()
                    }}
                    className="ml-auto rounded p-0.5 hover:bg-green-500/20"
                    aria-label="Clear selection"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )}

              {searchError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4" />
                  {searchError}
                </div>
              )}
            </div>

            {/* Role Selection */}
            <div className="space-y-2">
              <label htmlFor="role-select" className="text-sm font-medium">
                Role
              </label>
              <Select.Root
                value={selectedRole}
                onValueChange={(value) => setSelectedRole(value as ApplicationRole)}
                disabled={isSending}
              >
                <Select.Trigger
                  id="role-select"
                  className={cn(
                    'flex w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2',
                    'text-sm',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                    'disabled:cursor-not-allowed disabled:opacity-50'
                  )}
                  aria-label="Select role"
                >
                  <Select.Value placeholder="Select a role" />
                  <Select.Icon>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </Select.Icon>
                </Select.Trigger>

                <Select.Portal>
                  <Select.Content
                    className={cn(
                      'z-50 min-w-[200px] overflow-hidden rounded-md border border-border bg-popover shadow-md',
                      'data-[state=open]:animate-in data-[state=closed]:animate-out',
                      'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
                      'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
                      'data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2'
                    )}
                    position="popper"
                    sideOffset={4}
                  >
                    <Select.Viewport className="p-1">
                      {ROLE_OPTIONS.map((option) => (
                        <Select.Item
                          key={option.value}
                          value={option.value}
                          className={cn(
                            'relative flex cursor-pointer select-none flex-col rounded-sm px-3 py-2',
                            'text-sm outline-none',
                            'focus:bg-accent focus:text-accent-foreground',
                            'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <Select.ItemIndicator>
                              <Check className="h-4 w-4" />
                            </Select.ItemIndicator>
                            <Select.ItemText>{option.label}</Select.ItemText>
                          </div>
                          <span className="ml-6 text-xs text-muted-foreground">
                            {option.description}
                          </span>
                        </Select.Item>
                      ))}
                    </Select.Viewport>
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </div>

            {/* Store Error */}
            {storeError && (
              <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <AlertCircle className="h-4 w-4" />
                {storeError.message}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={handleClose}
                className={cn(
                  'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
                disabled={isSending}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={cn(
                  'flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                  'hover:bg-primary/90',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
                disabled={isSending || !selectedUser}
              >
                {isSending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <UserPlus className="h-4 w-4" />
                    Send Invitation
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Close Button */}
          <Dialog.Close asChild>
            <button
              className={cn(
                'absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity',
                'hover:opacity-100',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'disabled:pointer-events-none'
              )}
              aria-label="Close"
              disabled={isSending}
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default InvitationModal
