/**
 * Login Page
 *
 * Provides user authentication via email and password.
 * Uses OAuth2 password flow for authentication.
 *
 * Features:
 * - Email and password form validation
 * - Loading state during authentication
 * - Error display for failed attempts
 * - Link to registration page
 * - Theme-aware styling
 */

import { useState, useCallback, FormEvent, ChangeEvent } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, type LoginCredentials } from '@/hooks/use-auth'
import { Loader2, Mail, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface LoginPageProps {
  onNavigateToRegister: () => void
}

interface FormErrors {
  email?: string
  password?: string
}

// ============================================================================
// Validation
// ============================================================================

function validateEmail(email: string): string | undefined {
  if (!email.trim()) {
    return 'Email is required'
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(email)) {
    return 'Please enter a valid email address'
  }
  return undefined
}

function validatePassword(password: string): string | undefined {
  if (!password) {
    return 'Password is required'
  }
  if (password.length < 8) {
    return 'Password must be at least 8 characters'
  }
  return undefined
}

// ============================================================================
// Component
// ============================================================================

export function LoginPage({ onNavigateToRegister }: LoginPageProps): JSX.Element {
  // Auth state and actions
  const { login, isLoading, error, clearError } = useAuth()

  // Form state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  // Handle email change
  const handleEmailChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    clearError()
    if (touched.email) {
      setFormErrors((prev) => ({ ...prev, email: validateEmail(value) }))
    }
  }, [touched.email, clearError])

  // Handle password change
  const handlePasswordChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPassword(value)
    clearError()
    if (touched.password) {
      setFormErrors((prev) => ({ ...prev, password: validatePassword(value) }))
    }
  }, [touched.password, clearError])

  // Handle field blur for validation
  const handleBlur = useCallback((field: 'email' | 'password') => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    if (field === 'email') {
      setFormErrors((prev) => ({ ...prev, email: validateEmail(email) }))
    } else {
      setFormErrors((prev) => ({ ...prev, password: validatePassword(password) }))
    }
  }, [email, password])

  // Handle form submission
  const handleSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()

    // Validate all fields
    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)

    setFormErrors({ email: emailError, password: passwordError })
    setTouched({ email: true, password: true })

    // Don't submit if there are validation errors
    if (emailError || passwordError) {
      return
    }

    const credentials: LoginCredentials = { email, password }
    await login(credentials)
  }, [email, password, login])

  // Toggle password visibility
  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xl">
            PM
          </div>
          <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
          <p className="mt-2 text-muted-foreground">
            Sign in to your account to continue
          </p>
        </div>

        {/* Form Card */}
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* API Error Message */}
            {error && (
              <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span>{error.message}</span>
              </div>
            )}

            {/* Email Field */}
            <div className="space-y-2">
              <label
                htmlFor="email"
                className="text-sm font-medium text-foreground"
              >
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={handleEmailChange}
                  onBlur={() => handleBlur('email')}
                  placeholder="name@example.com"
                  disabled={isLoading}
                  autoComplete="email"
                  className={cn(
                    'w-full rounded-md border bg-background py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    formErrors.email && touched.email
                      ? 'border-destructive focus:ring-destructive'
                      : 'border-input'
                  )}
                />
              </div>
              {formErrors.email && touched.email && (
                <p className="text-xs text-destructive">{formErrors.email}</p>
              )}
            </div>

            {/* Password Field */}
            <div className="space-y-2">
              <label
                htmlFor="password"
                className="text-sm font-medium text-foreground"
              >
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={handlePasswordChange}
                  onBlur={() => handleBlur('password')}
                  placeholder="Enter your password"
                  disabled={isLoading}
                  autoComplete="current-password"
                  className={cn(
                    'w-full rounded-md border bg-background py-2 pl-10 pr-10 text-sm text-foreground placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    formErrors.password && touched.password
                      ? 'border-destructive focus:ring-destructive'
                      : 'border-input'
                  )}
                />
                <button
                  type="button"
                  onClick={togglePasswordVisibility}
                  disabled={isLoading}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground disabled:pointer-events-none"
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
              {formErrors.password && touched.password && (
                <p className="text-xs text-destructive">{formErrors.password}</p>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className={cn(
                'w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                'disabled:cursor-not-allowed disabled:opacity-50',
                'transition-colors duration-200'
              )}
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </form>
        </div>

        {/* Register Link */}
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Don't have an account?{' '}
          <button
            onClick={onNavigateToRegister}
            disabled={isLoading}
            className="font-medium text-primary underline-offset-4 hover:underline disabled:pointer-events-none disabled:opacity-50"
          >
            Create an account
          </button>
        </p>
      </div>
    </div>
  )
}

export default LoginPage
