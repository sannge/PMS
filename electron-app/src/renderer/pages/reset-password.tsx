/**
 * Reset Password Page
 *
 * 6-digit code input + new password fields.
 * Matches login.tsx glass-morphism styling.
 */

import { useState, useCallback, useEffect, useRef, FormEvent, KeyboardEvent, ClipboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { validatePassword } from '@/lib/validation'
import { useAuth } from '@/hooks/use-auth'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { AnimatedBackground } from '@/components/auth/animated-background'
import {
  Loader2,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  KeyRound,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface ResetPasswordPageProps {
  email: string
  onNavigateToLogin: () => void
}

function validateConfirmPassword(password: string, confirm: string): string | undefined {
  if (!confirm) return 'Please confirm your password'
  if (password !== confirm) return 'Passwords do not match'
  return undefined
}

// ============================================================================
// Component
// ============================================================================

export function ResetPasswordPage({ email, onNavigateToLogin }: ResetPasswordPageProps): JSX.Element {
  const { resetPassword, forgotPassword, isLoading, error, clearError } = useAuth()

  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [passwordError, setPasswordError] = useState<string | undefined>()
  const [confirmError, setConfirmError] = useState<string | undefined>()
  const [touchedPassword, setTouchedPassword] = useState(false)
  const [touchedConfirm, setTouchedConfirm] = useState(false)
  const [countdown, setCountdown] = useState(60)
  const [success, setSuccess] = useState(false)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) return
    const timer = setTimeout(() => {
      setCountdown((prev) => prev - 1)
    }, 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  // Focus first input on mount
  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  const handleDigitChange = useCallback((index: number, value: string) => {
    if (!/^\d?$/.test(value)) return

    clearError()
    setDigits((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })

    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }
  }, [clearError])

  const handleKeyDown = useCallback((index: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
      setDigits((prev) => {
        const next = [...prev]
        next[index - 1] = ''
        return next
      })
    }
  }, [digits])

  const handlePaste = useCallback((e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 0) return

    clearError()
    const newDigits = Array.from({ length: 6 }, (_, i) => pasted[i] || '')
    setDigits(newDigits)

    const nextEmpty = newDigits.findIndex((d) => d === '')
    inputRefs.current[nextEmpty >= 0 ? nextEmpty : 5]?.focus()
  }, [clearError])

  const handleResend = useCallback(async () => {
    const sent = await forgotPassword(email)
    if (sent) {
      setCountdown(60)
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    }
  }, [email, forgotPassword])

  const handleSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()

    const code = digits.join('')
    if (code.length !== 6) return

    const pwErr = validatePassword(password)
    const confErr = validateConfirmPassword(password, confirmPassword)
    setPasswordError(pwErr)
    setConfirmError(confErr)
    setTouchedPassword(true)
    setTouchedConfirm(true)

    if (pwErr || confErr) return

    const ok = await resetPassword(email, code, password)
    if (ok) {
      setSuccess(true)
    }
  }, [digits, password, confirmPassword, email, resetPassword])

  // Success state
  if (success) {
    return (
      <div className="flex h-screen flex-col">
        <WindowTitleBar variant="auth" />

        <div className="relative flex flex-1 items-center justify-center p-6">
          <AnimatedBackground />

          <div className="w-full max-w-md animate-slide-in-up">
            <div className={cn(
              'rounded-2xl p-8 text-center',
              'bg-white/[0.03] backdrop-blur-xl',
              'border border-white/10',
              'shadow-2xl shadow-black/20'
            )}>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10 border border-green-500/20">
                <CheckCircle className="h-8 w-8 text-green-400" />
              </div>
              <h2 className="mb-2 text-xl font-bold text-white">Password reset!</h2>
              <p className="mb-6 text-slate-400">
                Your password has been updated. You can now sign in with your new password.
              </p>
              <button
                onClick={onNavigateToLogin}
                className={cn(
                  'group w-full rounded-xl py-3.5 text-sm font-semibold',
                  'bg-gradient-to-r from-amber-500 to-orange-500 text-white',
                  'transition-all duration-300',
                  'hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/30',
                  'focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:ring-offset-2 focus:ring-offset-slate-900'
                )}
              >
                <span className="flex items-center justify-center gap-2">
                  Go to sign in
                  <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const codeComplete = digits.every((d) => d !== '')

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
              Reset your password
            </h1>
            <p className="mt-2 text-slate-400">
              We sent a code to{' '}
              <span className="font-medium text-slate-300">{email}</span>
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

              {/* Code inputs */}
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-300">
                  Verification code
                </label>
                <div className="flex justify-center gap-3">
                  {digits.map((digit, index) => (
                    <input
                      key={index}
                      ref={(el) => { inputRefs.current[index] = el }}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleDigitChange(index, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(index, e)}
                      onPaste={handlePaste}
                      disabled={isLoading}
                      className={cn(
                        'h-14 w-12 rounded-xl text-center text-2xl font-bold',
                        'bg-white/5 border text-white',
                        'transition-all duration-200',
                        'focus:outline-none focus:ring-2 focus:bg-white/10',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                        'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                      )}
                      aria-label={`Digit ${index + 1}`}
                    />
                  ))}
                </div>

                {/* Resend */}
                <div className="mt-3 text-center text-sm text-slate-400">
                  Didn't receive the code?{' '}
                  {countdown > 0 ? (
                    <span className="text-slate-500">Resend in {countdown}s</span>
                  ) : (
                    <button
                      type="button"
                      onClick={handleResend}
                      disabled={isLoading}
                      className="font-semibold text-amber-400 hover:text-amber-300 hover:underline underline-offset-4 disabled:pointer-events-none disabled:opacity-50"
                    >
                      Resend code
                    </button>
                  )}
                </div>
              </div>

              {/* New Password */}
              <div className="space-y-2">
                <label htmlFor="new-password" className="text-sm font-medium text-slate-300">
                  New password
                </label>
                <div className="relative">
                  <Lock className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    passwordError && touchedPassword ? 'text-red-400' : 'text-slate-500'
                  )} />
                  <input
                    id="new-password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value)
                      clearError()
                      if (touchedPassword) setPasswordError(validatePassword(e.target.value))
                      if (touchedConfirm) setConfirmError(validateConfirmPassword(e.target.value, confirmPassword))
                    }}
                    onBlur={() => { setTouchedPassword(true); setPasswordError(validatePassword(password)) }}
                    placeholder="Enter new password"
                    disabled={isLoading}
                    autoComplete="new-password"
                    className={cn(
                      'w-full rounded-xl py-3.5 pl-12 pr-12 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      passwordError && touchedPassword
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((p) => !p)}
                    disabled={isLoading}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors disabled:pointer-events-none"
                    tabIndex={-1}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
                {passwordError && touchedPassword && (
                  <p className="text-xs text-red-400 animate-fade-in">{passwordError}</p>
                )}
              </div>

              {/* Confirm Password */}
              <div className="space-y-2">
                <label htmlFor="confirm-password" className="text-sm font-medium text-slate-300">
                  Confirm new password
                </label>
                <div className="relative">
                  <Lock className={cn(
                    'absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 transition-colors duration-200',
                    confirmError && touchedConfirm ? 'text-red-400' : 'text-slate-500'
                  )} />
                  <input
                    id="confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value)
                      clearError()
                      if (touchedConfirm) setConfirmError(validateConfirmPassword(password, e.target.value))
                    }}
                    onBlur={() => { setTouchedConfirm(true); setConfirmError(validateConfirmPassword(password, confirmPassword)) }}
                    placeholder="Confirm new password"
                    disabled={isLoading}
                    autoComplete="new-password"
                    className={cn(
                      'w-full rounded-xl py-3.5 pl-12 pr-12 text-sm',
                      'bg-white/5 border text-white placeholder:text-slate-500',
                      'transition-all duration-200',
                      'focus:outline-none focus:ring-2 focus:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      confirmError && touchedConfirm
                        ? 'border-red-500/50 focus:ring-red-500/30'
                        : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((p) => !p)}
                    disabled={isLoading}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors disabled:pointer-events-none"
                    tabIndex={-1}
                    aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                  >
                    {showConfirmPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
                {confirmError && touchedConfirm && (
                  <p className="text-xs text-red-400 animate-fade-in">{confirmError}</p>
                )}
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={isLoading || !codeComplete}
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
                    Resetting password...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    Reset password
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

export default ResetPasswordPage
