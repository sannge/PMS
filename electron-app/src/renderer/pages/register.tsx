/**
 * Register Page
 *
 * Provides user registration with email, password, and display name.
 * After successful registration, redirects to login page.
 *
 * Features:
 * - Email, password, and display name form validation
 * - Password confirmation field
 * - Loading state during registration
 * - Error display for failed attempts
 * - Link to login page
 * - Theme-aware styling
 */

import { useState, useCallback, FormEvent, ChangeEvent } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, type RegisterData } from '@/hooks/use-auth'
import { Loader2, Mail, Lock, User, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface RegisterPageProps {
  onNavigateToLogin: () => void
}

interface FormErrors {
  email?: string
  password?: string
  confirmPassword?: string
  displayName?: string
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

function validateConfirmPassword(password: string, confirmPassword: string): string | undefined {
  if (!confirmPassword) {
    return 'Please confirm your password'
  }
  if (password !== confirmPassword) {
    return 'Passwords do not match'
  }
  return undefined
}

function validateDisplayName(displayName: string): string | undefined {
  // Display name is optional, but if provided should be reasonable
  if (displayName && displayName.length > 100) {
    return 'Display name must be less than 100 characters'
  }
  return undefined
}

// ============================================================================
// Component
// ============================================================================

export function RegisterPage({ onNavigateToLogin }: RegisterPageProps): JSX.Element {
  // Auth state and actions
  const { register, isLoading, error, clearError } = useAuth()

  // Form state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [registrationSuccess, setRegistrationSuccess] = useState(false)

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
    if (touched.confirmPassword) {
      setFormErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(value, confirmPassword),
      }))
    }
  }, [touched.password, touched.confirmPassword, confirmPassword, clearError])

  // Handle confirm password change
  const handleConfirmPasswordChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setConfirmPassword(value)
    clearError()
    if (touched.confirmPassword) {
      setFormErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(password, value),
      }))
    }
  }, [touched.confirmPassword, password, clearError])

  // Handle display name change
  const handleDisplayNameChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setDisplayName(value)
    clearError()
    if (touched.displayName) {
      setFormErrors((prev) => ({ ...prev, displayName: validateDisplayName(value) }))
    }
  }, [touched.displayName, clearError])

  // Handle field blur for validation
  const handleBlur = useCallback((field: keyof FormErrors) => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    switch (field) {
      case 'email':
        setFormErrors((prev) => ({ ...prev, email: validateEmail(email) }))
        break
      case 'password':
        setFormErrors((prev) => ({ ...prev, password: validatePassword(password) }))
        break
      case 'confirmPassword':
        setFormErrors((prev) => ({
          ...prev,
          confirmPassword: validateConfirmPassword(password, confirmPassword),
        }))
        break
      case 'displayName':
        setFormErrors((prev) => ({ ...prev, displayName: validateDisplayName(displayName) }))
        break
    }
  }, [email, password, confirmPassword, displayName])

  // Handle form submission
  const handleSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()

    // Validate all fields
    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmPasswordError = validateConfirmPassword(password, confirmPassword)
    const displayNameError = validateDisplayName(displayName)

    setFormErrors({
      email: emailError,
      password: passwordError,
      confirmPassword: confirmPasswordError,
      displayName: displayNameError,
    })
    setTouched({
      email: true,
      password: true,
      confirmPassword: true,
      displayName: true,
    })

    // Don't submit if there are validation errors
    if (emailError || passwordError || confirmPasswordError || displayNameError) {
      return
    }

    const data: RegisterData = {
      email,
      password,
      display_name: displayName || undefined,
    }

    const success = await register(data)
    if (success) {
      setRegistrationSuccess(true)
    }
  }, [email, password, confirmPassword, displayName, register])

  // Toggle password visibility
  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  // Toggle confirm password visibility
  const toggleConfirmPasswordVisibility = useCallback(() => {
    setShowConfirmPassword((prev) => !prev)
  }, [])

  // Show success message after registration
  if (registrationSuccess) {
    return (
      <div className="flex min-h-full flex-col items-center justify-center bg-background p-4">
        <div className="w-full max-w-md">
          <div className="rounded-lg border border-border bg-card p-6 text-center shadow-sm">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
              <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <h2 className="mb-2 text-xl font-semibold text-foreground">
              Registration Successful!
            </h2>
            <p className="mb-6 text-muted-foreground">
              Your account has been created. You can now sign in with your credentials.
            </p>
            <button
              onClick={onNavigateToLogin}
              className={cn(
                'w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                'transition-colors duration-200'
              )}
            >
              Go to Sign In
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xl">
            PM
          </div>
          <h1 className="text-2xl font-bold text-foreground">Create an account</h1>
          <p className="mt-2 text-muted-foreground">
            Get started with PM Desktop
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

            {/* Display Name Field (Optional) */}
            <div className="space-y-2">
              <label
                htmlFor="displayName"
                className="text-sm font-medium text-foreground"
              >
                Display Name <span className="text-muted-foreground">(optional)</span>
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="displayName"
                  type="text"
                  value={displayName}
                  onChange={handleDisplayNameChange}
                  onBlur={() => handleBlur('displayName')}
                  placeholder="Your name"
                  disabled={isLoading}
                  autoComplete="name"
                  className={cn(
                    'w-full rounded-md border bg-background py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    formErrors.displayName && touched.displayName
                      ? 'border-destructive focus:ring-destructive'
                      : 'border-input'
                  )}
                />
              </div>
              {formErrors.displayName && touched.displayName && (
                <p className="text-xs text-destructive">{formErrors.displayName}</p>
              )}
            </div>

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
                  placeholder="Create a password"
                  disabled={isLoading}
                  autoComplete="new-password"
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
              <p className="text-xs text-muted-foreground">
                Must be at least 8 characters
              </p>
            </div>

            {/* Confirm Password Field */}
            <div className="space-y-2">
              <label
                htmlFor="confirmPassword"
                className="text-sm font-medium text-foreground"
              >
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={handleConfirmPasswordChange}
                  onBlur={() => handleBlur('confirmPassword')}
                  placeholder="Confirm your password"
                  disabled={isLoading}
                  autoComplete="new-password"
                  className={cn(
                    'w-full rounded-md border bg-background py-2 pl-10 pr-10 text-sm text-foreground placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    formErrors.confirmPassword && touched.confirmPassword
                      ? 'border-destructive focus:ring-destructive'
                      : 'border-input'
                  )}
                />
                <button
                  type="button"
                  onClick={toggleConfirmPasswordVisibility}
                  disabled={isLoading}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground disabled:pointer-events-none"
                  tabIndex={-1}
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
              {formErrors.confirmPassword && touched.confirmPassword && (
                <p className="text-xs text-destructive">{formErrors.confirmPassword}</p>
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
                  Creating account...
                </span>
              ) : (
                'Create account'
              )}
            </button>
          </form>
        </div>

        {/* Login Link */}
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <button
            onClick={onNavigateToLogin}
            disabled={isLoading}
            className="font-medium text-primary underline-offset-4 hover:underline disabled:pointer-events-none disabled:opacity-50"
          >
            Sign in
          </button>
        </p>
      </div>
    </div>
  )
}

export default RegisterPage
