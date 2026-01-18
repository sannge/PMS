/**
 * Login Page
 *
 * Immersive authentication experience with dynamic gradient background.
 * Features:
 * - Animated gradient mesh background
 * - Glass morphism card design
 * - Smooth form interactions
 * - Refined input styling with focus states
 */

import { useState, useCallback, FormEvent, ChangeEvent } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, type LoginCredentials } from '@/hooks/use-auth'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import {
  Loader2,
  Mail,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
} from 'lucide-react'

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
// Background Component
// ============================================================================

function AnimatedBackground(): JSX.Element {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden">
      {/* Base gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900" />

      {/* Animated gradient orbs */}
      <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-gradient-to-br from-amber-500/30 to-orange-500/20 blur-3xl animate-float" />
      <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-gradient-to-br from-violet-500/20 to-purple-500/20 blur-3xl animate-float animation-delay-200" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-96 w-96 rounded-full bg-gradient-to-br from-amber-500/10 to-transparent blur-3xl" />

      {/* Grid overlay */}
      <div
        className="absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: '50px 50px',
        }}
      />

      {/* Noise texture */}
      <div className="absolute inset-0 bg-noise opacity-[0.015]" />
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function LoginPage({ onNavigateToRegister }: LoginPageProps): JSX.Element {
  const { login, isLoading, error, clearError } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const handleEmailChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    clearError()
    if (touched.email) {
      setFormErrors((prev) => ({ ...prev, email: validateEmail(value) }))
    }
  }, [touched.email, clearError])

  const handlePasswordChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setPassword(value)
    clearError()
    if (touched.password) {
      setFormErrors((prev) => ({ ...prev, password: validatePassword(value) }))
    }
  }, [touched.password, clearError])

  const handleBlur = useCallback((field: 'email' | 'password') => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    if (field === 'email') {
      setFormErrors((prev) => ({ ...prev, email: validateEmail(email) }))
    } else {
      setFormErrors((prev) => ({ ...prev, password: validatePassword(password) }))
    }
  }, [email, password])

  const handleSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)

    setFormErrors({ email: emailError, password: passwordError })
    setTouched({ email: true, password: true })

    if (emailError || passwordError) {
      return
    }

    const credentials: LoginCredentials = { email, password }
    await login(credentials)
  }, [email, password, login])

  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  return (
    <div className="flex h-screen flex-col">
      {/* Custom Window Title Bar */}
      <WindowTitleBar variant="auth" />

      <div className="relative flex flex-1 items-center justify-center p-6">
        <AnimatedBackground />

      <div className="w-full max-w-md animate-slide-in-up">
        {/* Header */}
        <div className="mb-8 text-center">
          {/* PMS Logo */}
          <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center">
            <svg viewBox="0 0 64 64" fill="none" className="w-full h-full drop-shadow-2xl">
              <defs>
                <linearGradient id="login-pms-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#FBBF24" />
                  <stop offset="50%" stopColor="#EA580C" />
                  <stop offset="100%" stopColor="#F59E0B" />
                </linearGradient>
                <linearGradient id="login-pms-shine" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#FDE68A" stopOpacity="0.6" />
                  <stop offset="100%" stopColor="#F59E0B" stopOpacity="0" />
                </linearGradient>
                <filter id="login-glow" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>
              <rect x="4" y="4" width="56" height="56" rx="16" fill="url(#login-pms-gradient)" filter="url(#login-glow)" />
              <rect x="4" y="4" width="56" height="28" rx="16" fill="url(#login-pms-shine)" />
              <path
                d="M20 16H36C41.5228 16 46 20.4772 46 26C46 31.5228 41.5228 36 36 36H28V48H20V16Z"
                fill="white"
                fillOpacity="0.95"
              />
              <path
                d="M28 22V30H35C37.2091 30 39 28.2091 39 26C39 23.7909 37.2091 22 35 22H28Z"
                fill="url(#login-pms-gradient)"
              />
            </svg>
          </div>

          <h1 className="text-3xl font-bold tracking-tight text-white">
            Welcome back
          </h1>
          <p className="mt-2 text-slate-400">
            Sign in to continue to PMS
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
              <div className={cn(
                'flex items-center gap-3 rounded-xl p-4',
                'bg-red-500/10 border border-red-500/20',
                'text-sm text-red-400',
                'animate-fade-in'
              )}>
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span>{error.message}</span>
              </div>
            )}

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
                <p className="text-xs text-red-400 animate-fade-in">{formErrors.email}</p>
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
                  placeholder="Enter your password"
                  disabled={isLoading}
                  autoComplete="current-password"
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
                  className={cn(
                    'absolute right-4 top-1/2 -translate-y-1/2',
                    'text-slate-500 hover:text-slate-300 transition-colors',
                    'disabled:pointer-events-none'
                  )}
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
                <p className="text-xs text-red-400 animate-fade-in">{formErrors.password}</p>
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
                  Signing in...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  Sign in
                  <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                </span>
              )}
            </button>
          </form>
        </div>

        {/* Register Link */}
        <p className="mt-8 text-center text-sm text-slate-400">
          Don't have an account?{' '}
          <button
            onClick={onNavigateToRegister}
            disabled={isLoading}
            className={cn(
              'font-semibold text-amber-400 underline-offset-4',
              'transition-colors duration-200',
              'hover:text-amber-300 hover:underline',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
          >
            Create account
          </button>
        </p>

        {/* Footer */}
        <p className="mt-8 text-center text-xs text-slate-500">
          By signing in, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
      </div>
    </div>
  )
}

export default LoginPage
