/**
 * Animated gradient mesh background for auth pages.
 * Shared across login, register, verify-email, forgot-password, reset-password.
 */

export function AnimatedBackground(): JSX.Element {
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
