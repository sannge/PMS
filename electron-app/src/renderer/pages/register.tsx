/**
 * Register Page
 *
 * Provides user registration with email, password, and display name.
 * After successful registration, redirects to email verification page.
 *
 * Features:
 * - Glass-morphism design matching login page
 * - AnimatedBackground with gradient mesh
 * - Email, password, and display name form validation
 * - Password confirmation field
 * - Loading state during registration
 * - Error display for failed attempts
 * - Link to login page
 */

import { useState, useCallback, FormEvent, ChangeEvent } from 'react'
import { cn } from '@/lib/utils'
import { validateEmail, validatePassword } from '@/lib/validation'
import { useAuth, type RegisterData } from '@/hooks/use-auth'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { AnimatedBackground } from '@/components/auth/animated-background'
import { Loader2, Mail, Lock, User, Eye, EyeOff, AlertCircle, ArrowRight } from 'lucide-react'

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

    // On success, auth context sets pendingVerificationEmail
    // which triggers AuthPages to show VerifyEmailPage
    await register(data)
  }, [email, password, confirmPassword, displayName, register])

  // Toggle password visibility
  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  // Toggle confirm password visibility
  const toggleConfirmPasswordVisibility = useCallback(() => {
    setShowConfirmPassword((prev) => !prev)
  }, [])

  return (
    <div className="flex h-screen flex-col">
      <WindowTitleBar variant="auth" />

      <div className="relative flex flex-1 items-center justify-center p-6">
        <AnimatedBackground />

        <div className="w-full max-w-md animate-slide-in-up">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/10 border border-amber-500/20">
              <User className="h-8 w-8 text-amber-400" />
            </div>

            <h1 className="text-3xl font-bold tracking-tight text-white">
              Create an account
            </h1>
            <p className="mt-2 text-slate-400">
              Get started with PM Desktop
            </p>
          </div>

          {/* Form Card */}
          <div className={cn(
            'rounded-2xl p-8',
            'bg-white/[0.03] backdrop-blur-xl',
            'border border-white/10',
            'shadow-2xl shadow-black/20'
          )}>
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* API Error Message */}
              {error && (
                <div role="alert" className={cn(
                  'flex items-center gap-3 rounded-xl p-4',
                  'bg-red-500/10 border border-red-500/20',
                  'text-sm text-red-400',
                  'animate-fade-in'
                )}>
                  <AlertCircle className="h-5 w-5 flex-shrink-0" />
                  <span>{error.message}</span>
                </div>
              )}

              {/* Display Name Field (Optional) */}
              <div className="space-y-2">
                <label
                  htmlFor="displayName"
                  className="text-sm font-medium text-slate-300"
                >
                  Display name <span className="text-slate-500">(optional)</span>
                </label>
                <div className="relative">
                  <User className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    formErrors.displayName && touched.displayName ? 'text-red-400' : 'text-slate-500'
                  )} />
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
                      'w-full rounded-xl py-3.5 pl-12 pr-4 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      formErrors.displayName && touched.displayName
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                </div>
                {formErrors.displayName && touched.displayName && (
                  <p role="alert" className="text-xs text-red-400 animate-fade-in">{formErrors.displayName}</p>
                )}
              </div>

              {/* Email Field */}
              <div className="space-y-2">
                <label
                  htmlFor="email"
                  className="text-sm font-medium text-slate-300"
                >
                  Email address
                </label>
                <div className="relative">
                  <Mail className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    formErrors.email && touched.email ? 'text-red-400' : 'text-slate-500'
                  )} />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={handleEmailChange}
                    onBlur={() => handleBlur('email')}
                    placeholder="name@company.com"
                    disabled={isLoading}
                    autoComplete="email"
                    className={cn(
                      'w-full rounded-xl py-3.5 pl-12 pr-4 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      formErrors.email && touched.email
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                </div>
                {formErrors.email && touched.email && (
                  <p role="alert" className="text-xs text-red-400 animate-fade-in">{formErrors.email}</p>
                )}
              </div>

              {/* Password Field */}
              <div className="space-y-2">
                <label
                  htmlFor="password"
                  className="text-sm font-medium text-slate-300"
                >
                  Password
                </label>
                <div className="relative">
                  <Lock className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    formErrors.password && touched.password ? 'text-red-400' : 'text-slate-500'
                  )} />
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
                      'w-full rounded-xl py-3.5 pl-12 pr-12 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      formErrors.password && touched.password
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                  <button
                    type="button"
                    onClick={togglePasswordVisibility}
                    disabled={isLoading}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors disabled:pointer-events-none"
                    tabIndex={-1}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? (
                      <EyeOff className="h-5 w-5" />
                    ) : (
                      <Eye className="h-5 w-5" />
                    )}
                  </button>
                </div>
                {formErrors.password && touched.password && (
                  <p role="alert" className="text-xs text-red-400 animate-fade-in">{formErrors.password}</p>
                )}
                <p className="text-xs text-slate-500">
                  Must be at least 8 characters
                </p>
              </div>

              {/* Confirm Password Field */}
              <div className="space-y-2">
                <label
                  htmlFor="confirmPassword"
                  className="text-sm font-medium text-slate-300"
                >
                  Confirm password
                </label>
                <div className="relative">
                  <Lock className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    formErrors.confirmPassword && touched.confirmPassword ? 'text-red-400' : 'text-slate-500'
                  )} />
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
                      'w-full rounded-xl py-3.5 pl-12 pr-12 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      formErrors.confirmPassword && touched.confirmPassword
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                  <button
                    type="button"
                    onClick={toggleConfirmPasswordVisibility}
                    disabled={isLoading}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors disabled:pointer-events-none"
                    tabIndex={-1}
                    aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="h-5 w-5" />
                    ) : (
                      <Eye className="h-5 w-5" />
                    )}
                  </button>
                </div>
                {formErrors.confirmPassword && touched.confirmPassword && (
                  <p role="alert" className="text-xs text-red-400 animate-fade-in">{formErrors.confirmPassword}</p>
                )}
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading}
                className={cn(
                  'group relative w-full rounded-xl py-3.5 text-sm font-semibold',
                  'bg-gradient-to-r from-amber-500 to-orange-500 text-white',
                  'transition-all duration-300',
                  'hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/30',
                  'focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:ring-offset-2 focus:ring-offset-slate-900',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
              >
                {isLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Creating account...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    Create account
                    <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                  </span>
                )}
              </button>
            </form>
          </div>

          {/* Login Link */}
          <p className="mt-8 text-center text-sm text-slate-400">
            Already have an account?{' '}
            <button
              onClick={onNavigateToLogin}
              disabled={isLoading}
              className={cn(
                'font-semibold text-amber-400 underline-offset-4',
                'transition-colors duration-200',
                'hover:text-amber-300 hover:underline',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}

export default RegisterPage
