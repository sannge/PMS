/**
 * Verify Email Page
 *
 * 6-digit code verification with auto-advance, paste support, and auto-submit.
 * Matches login.tsx glass-morphism styling.
 */

import { useState, useCallback, useEffect, useRef, KeyboardEvent, ClipboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/use-auth'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { AnimatedBackground } from '@/components/auth/animated-background'
import { Loader2, AlertCircle, Mail, Shield, ArrowLeft } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface VerifyEmailPageProps {
  email: string
  context?: 'registration' | 'login'
  onNavigateToLogin: () => void
}

// ============================================================================
// Component
// ============================================================================

export function VerifyEmailPage({ email, context = 'registration', onNavigateToLogin }: VerifyEmailPageProps): JSX.Element {
  const { verifyEmail, verifyLogin, resendVerification, isLoading, error, clearError } = useAuth()
  const isLogin = context === 'login'

  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [countdown, setCountdown] = useState(60)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])
  const hasSubmittedRef = useRef(false)

  // Countdown timer for resend
  useEffect(() => {
    if (countdown <= 0) return
    const timer = setTimeout(() => {
      setCountdown((prev) => prev - 1)
    }, 1000)
    return () => clearTimeout(timer)
  }, [countdown])

  // Auto-submit when all 6 digits are filled
  useEffect(() => {
    if (isLoading) return
    const code = digits.join('')
    if (code.length === 6 && digits.every((d) => d !== '') && !hasSubmittedRef.current) {
      hasSubmittedRef.current = true
      if (isLogin) {
        verifyLogin(email, code)
      } else {
        verifyEmail(email, code)
      }
    }
  }, [digits, email, verifyEmail, verifyLogin, isLoading, isLogin])

  // Focus first input on mount
  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  const handleDigitChange = useCallback((index: number, value: string) => {
    if (!/^\d?$/.test(value)) return

    clearError()
    hasSubmittedRef.current = false
    setDigits((prev) => {
      const next = [...prev]
      next[index] = value
      return next
    })

    // Auto-advance to next input
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
    hasSubmittedRef.current = false
    const newDigits = Array.from({ length: 6 }, (_, i) => pasted[i] || '')
    setDigits(newDigits)

    // Focus the next empty input or the last one
    const nextEmpty = newDigits.findIndex((d) => d === '')
    inputRefs.current[nextEmpty >= 0 ? nextEmpty : 5]?.focus()
  }, [clearError])

  const handleResend = useCallback(async () => {
    const success = await resendVerification(email)
    if (success) {
      setCountdown(60)
      setDigits(['', '', '', '', '', ''])
      hasSubmittedRef.current = false
      inputRefs.current[0]?.focus()
    }
  }, [email, resendVerification])

  return (
    <div className="flex h-screen flex-col">
      <WindowTitleBar variant="auth" />

      <div className="relative flex flex-1 items-center justify-center p-6">
        <AnimatedBackground />

        <div className="w-full max-w-md animate-slide-in-up">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className={cn(
              'mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full border',
              isLogin
                ? 'bg-blue-500/10 border-blue-500/20'
                : 'bg-amber-500/10 border-amber-500/20'
            )}>
              {isLogin ? (
                <Shield className="h-8 w-8 text-blue-400" />
              ) : (
                <Mail className="h-8 w-8 text-amber-400" />
              )}
            </div>

            <h1 className="text-3xl font-bold tracking-tight text-white">
              {isLogin ? 'Enter your login code' : 'Check your email'}
            </h1>
            <p className="mt-2 text-slate-400">
              {isLogin
                ? 'A verification code was sent to '
                : 'We sent a 6-digit code to '}
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
            {/* Error */}
            {error && (
              <div role="alert" className={cn(
                'mb-5 flex items-center gap-3 rounded-xl p-4',
                'bg-red-500/10 border border-red-500/20',
                'text-sm text-red-400',
                'animate-fade-in'
              )}>
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span>{error.message}</span>
              </div>
            )}

            {/* 6-digit code inputs */}
            <div className="flex justify-center gap-3 mb-6">
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
                    isLogin
                      ? 'border-white/10 focus:border-blue-500/50 focus:ring-blue-500/20'
                      : 'border-white/10 focus:border-amber-500/50 focus:ring-amber-500/20'
                  )}
                  aria-label={`Digit ${index + 1}`}
                />
              ))}
            </div>

            {/* Loading indicator */}
            {isLoading && (
              <div className="flex items-center justify-center gap-2 mb-4 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Verifying...
              </div>
            )}

            {/* Resend */}
            <div className="text-center text-sm text-slate-400">
              Didn't receive the code?{' '}
              {countdown > 0 ? (
                <span className="text-slate-500">Resend in {countdown}s</span>
              ) : (
                <button
                  onClick={handleResend}
                  disabled={isLoading}
                  className={cn(
                    'font-semibold underline-offset-4',
                    'transition-colors duration-200',
                    'disabled:pointer-events-none disabled:opacity-50',
                    isLogin
                      ? 'text-blue-400 hover:text-blue-300 hover:underline'
                      : 'text-amber-400 hover:text-amber-300 hover:underline'
                  )}
                >
                  Resend code
                </button>
              )}
            </div>
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

export default VerifyEmailPage
