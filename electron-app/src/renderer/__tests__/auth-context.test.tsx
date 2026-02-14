/**
 * Auth Context Tests
 *
 * Tests for authentication context provider and hooks.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { ReactNode } from 'react'
import {
  AuthProvider,
  useAuthStore,
  getAuthHeaders,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitialized,
  selectError,
} from '../contexts/auth-context'

// Wrapper component for hooks
function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

describe('Auth Context', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(window.localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(null)
  })

  describe('useAuthStore', () => {
    it('returns initial state', () => {
      const { result } = renderHook(() => useAuthStore(), { wrapper })

      expect(result.current.user).toBeNull()
      expect(result.current.token).toBeNull()
      expect(result.current.isAuthenticated).toBe(false)
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
    })

    it('works with selector', () => {
      const { result } = renderHook(() => useAuthStore(selectIsAuthenticated), { wrapper })
      expect(result.current).toBe(false)
    })

    it('throws error when used outside provider', () => {
      expect(() => {
        renderHook(() => useAuthStore())
      }).toThrow('useAuthStore must be used within an AuthProvider')
    })
  })

  describe('login', () => {
    it('successfully logs in user', async () => {
      const mockTokenResponse = { access_token: 'test-token', token_type: 'bearer' }
      const mockUser = {
        id: '123',
        email: 'test@test.com',
        display_name: 'Test User',
        avatar_url: null,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }

      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockTokenResponse,
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockUser,
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      let success: boolean
      await act(async () => {
        success = await result.current.login({ email: 'test@test.com', password: 'password' })
      })

      expect(success!).toBe(true)
      expect(result.current.token).toBe('test-token')
      expect(result.current.isAuthenticated).toBe(true)
      expect(result.current.user).toEqual(mockUser)
    })

    it('handles login failure', async () => {
      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 401,
        data: { detail: 'Invalid credentials' },
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      let success: boolean
      await act(async () => {
        success = await result.current.login({ email: 'test@test.com', password: 'wrong' })
      })

      expect(success!).toBe(false)
      expect(result.current.isAuthenticated).toBe(false)
      expect(result.current.error?.message).toBe('Invalid credentials')
    })
  })

  describe('logout', () => {
    it('clears auth state on logout', async () => {
      // Setup: First login
      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: { access_token: 'test-token', token_type: 'bearer' },
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: { id: '123', email: 'test@test.com', display_name: null, avatar_url: null, created_at: '', updated_at: '' },
      })
      ;(window.electronAPI.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: null,
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      await act(async () => {
        await result.current.login({ email: 'test@test.com', password: 'password' })
      })

      expect(result.current.isAuthenticated).toBe(true)

      await act(async () => {
        await result.current.logout()
      })

      expect(result.current.user).toBeNull()
      expect(result.current.token).toBeNull()
      expect(result.current.isAuthenticated).toBe(false)
    })
  })

  describe('register', () => {
    it('successfully registers user', async () => {
      const mockUser = {
        id: '123',
        email: 'new@test.com',
        display_name: 'New User',
        avatar_url: null,
        created_at: '2024-01-01',
        updated_at: '2024-01-01',
      }

      ;(window.electronAPI.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 201,
        data: mockUser,
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      let success: boolean
      await act(async () => {
        success = await result.current.register({
          email: 'new@test.com',
          password: 'password',
          display_name: 'New User',
        })
      })

      expect(success!).toBe(true)
      // Note: Registration doesn't automatically log in
      expect(result.current.isAuthenticated).toBe(false)
    })

    it('handles registration failure', async () => {
      ;(window.electronAPI.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 422,
        data: { detail: 'Email already exists' },
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      let success: boolean
      await act(async () => {
        success = await result.current.register({
          email: 'existing@test.com',
          password: 'password',
        })
      })

      expect(success!).toBe(false)
      expect(result.current.error?.message).toBe('Email already exists')
    })
  })

  describe('checkAuth', () => {
    it('validates token and fetches user when token exists', async () => {
      const mockUser = {
        id: '123',
        email: 'test@test.com',
        display_name: null,
        avatar_url: null,
        created_at: '',
        updated_at: '',
      }

      // First login to set the token
      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: { access_token: 'test-token', token_type: 'bearer' },
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockUser,
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      // Login first to set the token
      await act(async () => {
        await result.current.login({ email: 'test@test.com', password: 'password' })
      })

      // Mock the checkAuth call
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockUser,
      })

      let isValid: boolean
      await act(async () => {
        isValid = await result.current.checkAuth()
      })

      expect(isValid!).toBe(true)
      expect(result.current.isInitialized).toBe(true)
      expect(result.current.isAuthenticated).toBe(true)
    })

    it('handles invalid token', async () => {
      ;(window.localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(
        JSON.stringify({ state: { token: 'invalid-token' } })
      )

      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 401,
        data: { detail: 'Token expired' },
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      let isValid: boolean
      await act(async () => {
        isValid = await result.current.checkAuth()
      })

      expect(isValid!).toBe(false)
      expect(result.current.isInitialized).toBe(true)
      expect(result.current.isAuthenticated).toBe(false)
    })
  })

  describe('selectors', () => {
    it('selectUser returns user', () => {
      const state = {
        user: { id: '1', email: 'test@test.com', display_name: null, avatar_url: null, created_at: '', updated_at: '' },
        token: 'token',
        isAuthenticated: true,
        isLoading: false,
        isInitialized: true,
        error: null,
      } as any

      expect(selectUser(state)).toEqual(state.user)
    })

    it('selectIsAuthenticated returns boolean', () => {
      const state = { isAuthenticated: true } as any
      expect(selectIsAuthenticated(state)).toBe(true)
    })

    it('selectIsLoading returns boolean', () => {
      const state = { isLoading: true } as any
      expect(selectIsLoading(state)).toBe(true)
    })

    it('selectIsInitialized returns boolean', () => {
      const state = { isInitialized: true } as any
      expect(selectIsInitialized(state)).toBe(true)
    })

    it('selectError returns error', () => {
      const state = { error: { message: 'Error' } } as any
      expect(selectError(state)).toEqual({ message: 'Error' })
    })
  })

  describe('getAuthHeaders', () => {
    it('returns empty object when no token', () => {
      expect(getAuthHeaders(null)).toEqual({})
    })

    it('returns Authorization header with token', () => {
      expect(getAuthHeaders('my-token')).toEqual({
        Authorization: 'Bearer my-token',
      })
    })
  })

  describe('clearError', () => {
    it('clears error state', async () => {
      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 401,
        data: { detail: 'Error' },
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      await act(async () => {
        await result.current.login({ email: 'test@test.com', password: 'wrong' })
      })

      expect(result.current.error).not.toBeNull()

      act(() => {
        result.current.clearError()
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('reset', () => {
    it('resets to initial state', async () => {
      ;(window.electronAPI.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: { access_token: 'test-token', token_type: 'bearer' },
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: { id: '123', email: 'test@test.com', display_name: null, avatar_url: null, created_at: '', updated_at: '' },
      })

      const { result } = renderHook(() => useAuthStore(), { wrapper })

      await act(async () => {
        await result.current.login({ email: 'test@test.com', password: 'password' })
      })

      expect(result.current.isAuthenticated).toBe(true)

      act(() => {
        result.current.reset()
      })

      expect(result.current.user).toBeNull()
      expect(result.current.token).toBeNull()
      expect(result.current.isAuthenticated).toBe(false)
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
    })
  })
})
