/**
 * Forgot Password Page
 *
 * Email input form to request a password reset code.
 * Matches login.tsx glass-morphism styling.
 */

import { useState, useCallback, FormEvent, ChangeEvent } from 'react'
import { cn } from '@/lib/utils'
import { validateEmail } from '@/lib/validation'
import { useAuth } from '@/hooks/use-auth'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { AnimatedBackground } from '@/components/auth/animated-background'
import { Loader2, Mail, AlertCircle, ArrowLeft, ArrowRight, KeyRound } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface ForgotPasswordPageProps {
  initialEmail?: string
  onNavigateToLogin: () => void
  onNavigateToResetPassword: (email: string) => void
}

// ============================================================================
// Component
// ============================================================================

export function ForgotPasswordPage({
  initialEmail = '',
  onNavigateToLogin,
  onNavigateToResetPassword,
}: ForgotPasswordPageProps): JSX.Element {
  const { forgotPassword, isLoading, error, clearError } = useAuth()

  const [email, setEmail] = useState(initialEmail)
  const [emailError, setEmailError] = useState<string | undefined>()
  const [touched, setTouched] = useState(false)

  const handleEmailChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    clearError()
    if (touched) {
      setEmailError(validateEmail(value))
    }
  }, [touched, clearError])

  const handleBlur = useCallback(() => {
    setTouched(true)
    setEmailError(validateEmail(email))
  }, [email])

  const handleSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()

    const err = validateEmail(email)
    setEmailError(err)
    setTouched(true)

    if (err) return

    const success = await forgotPassword(email)
    if (success) {
      onNavigateToResetPassword(email)
    }
  }, [email, forgotPassword, onNavigateToResetPassword])

  return (
    <div className="flex h-screen flex-col">
      <WindowTitleBar variant="auth" />

      <div className="relative flex flex-1 items-center justify-center p-6">
        <AnimatedBackground />

        <div className="w-full max-w-md animate-slide-in-up">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/10 border border-amber-500/20">
              <KeyRound className="h-8 w-8 text-amber-400" />
            </div>

            <h1 className="text-3xl font-bold tracking-tight text-white">
              Forgot password?
            </h1>
            <p className="mt-2 text-slate-400">
              Enter your email and we'll send you a reset code
            </p>
          </div>

          {/* Card */}
          <div className={cn(
            'rounded-2xl p-8',
            'bg-white/[0.03] backdrop-blur-xl',
            'border border-white/10',
            'shadow-2xl shadow-black/20'
          )}>
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Error */}
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

              {/* Email Field */}
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium text-slate-300">
                  Email address
                </label>
                <div className="relative">
                  <Mail className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    emailError && touched ? 'text-red-400' : 'text-slate-500'
                  )} />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={handleEmailChange}
                    onBlur={handleBlur}
                    placeholder="name@company.com"
                    disabled={isLoading}
                    autoComplete="email"
                    autoFocus
                    className={cn(
                      'w-full rounded-xl py-3.5 pl-12 pr-4 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      emailError && touched
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                </div>
                {emailError && touched && (
                  <p className="text-xs text-red-400 animate-fade-in">{emailError}</p>
                )}
              </div>

              {/* Submit */}
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
                    Sending code...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    Send reset code
                    <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                  </span>
                )}
              </button>
            </form>
          </div>

          {/* Back to login */}
          <div className="mt-8 text-center">
            <button
              onClick={onNavigateToLogin}
              disabled={isLoading}
              className={cn(
                'inline-flex items-center gap-2 text-sm text-slate-400',
                'transition-colors duration-200',
                'hover:text-slate-300',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
            >
              <ArrowLeft className="h-4 w-4" />
              Back to sign in
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ForgotPasswordPage
