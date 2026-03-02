/**
 * User Chat Override Component — OAuth Subscription Connect
 *
 * Allows any authenticated user to connect their AI subscription via OAuth
 * or fall back to a manual API key. Accessible from the chat sidebar gear icon.
 *
 * Features:
 * - Provider cards for OpenAI (green) and Anthropic (amber + warning)
 * - OAuth connect flow via Electron BrowserWindow
 * - Connected state with model selector, test, disconnect
 * - Collapsible "Advanced: Use API Key Instead" section
 * - Status line showing effective configuration
 * - ConfirmDialog for disconnect confirmation
 * - Loading spinner during OAuth flow
 * - Error states with retry / fallback suggestions
 */

import { useState, useCallback, useEffect } from 'react'
import {
  Settings,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Shield,
  Trash2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Zap,
  Key,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  useAvailableModels,
  useUserOverrides,
  useCreateUserOverride,
  useDeleteUserOverride,
  useTestUserOverride,
  useUserEffectiveConfig,
  type AiModelResponse,
} from '@/hooks/use-ai-config'
import {
  useOAuthStatus,
  useOAuthInitiate,
  useOAuthDisconnect,
  type OAuthConnectionStatus,
} from '@/hooks/use-oauth-connect'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

type ProviderType = 'openai' | 'anthropic'
type TestStatus = 'idle' | 'testing' | 'success' | 'error'

// ============================================================================
// Status Line
// ============================================================================

function EffectiveConfigStatus() {
  const { data: effectiveConfig, isLoading } = useUserEffectiveConfig()
  const { data: oauthStatus } = useOAuthStatus()
  const { data: overrides } = useUserOverrides()

  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading...
      </div>
    )
  }

  // OAuth connected
  if (oauthStatus?.connected) {
    const provider = oauthStatus.provider_type
    const providerLabel = provider === 'openai' ? 'OpenAI' : provider === 'anthropic' ? 'Anthropic' : provider
    return (
      <div className="flex items-center gap-1.5 text-xs">
        <CheckCircle2 className="h-3 w-3 text-green-500" />
        <span className="text-muted-foreground">
          Currently using: Your {providerLabel} subscription
        </span>
      </div>
    )
  }

  // API key override
  const hasOverride = overrides && overrides.length > 0
  if (hasOverride) {
    const override = overrides[0]
    const modelName = override.models?.[0]?.display_name || override.provider_type
    return (
      <div className="flex items-center gap-1.5 text-xs">
        <CheckCircle2 className="h-3 w-3 text-green-500" />
        <span className="text-muted-foreground">
          Currently using: Your API key ({modelName})
        </span>
      </div>
    )
  }

  // Company default
  const defaultChat = effectiveConfig?.default_chat_model
  if (defaultChat) {
    return (
      <div className="flex items-center gap-1.5 text-xs">
        <CheckCircle2 className="h-3 w-3 text-blue-500" />
        <span className="text-muted-foreground">
          Currently using: Company default ({defaultChat.display_name})
        </span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <AlertTriangle className="h-3 w-3 text-amber-500" />
      <span className="text-muted-foreground">AI not configured. Contact your admin.</span>
    </div>
  )
}

// ============================================================================
// Provider Card (Disconnected State)
// ============================================================================

interface ProviderCardProps {
  providerType: ProviderType
  label: string
  description: string
  accentColor: 'green' | 'amber'
  warning?: string
  isConnecting: boolean
  onConnect: () => void
}

function ProviderCard({
  providerType,
  label,
  description,
  accentColor,
  warning,
  isConnecting,
  onConnect,
}: ProviderCardProps) {
  const colors = {
    green: {
      border: 'border-green-500/20 hover:border-green-500/40',
      bg: 'bg-green-500/5',
      icon: 'text-green-500',
      button: 'bg-green-600 hover:bg-green-700 text-white',
    },
    amber: {
      border: 'border-amber-500/20 hover:border-amber-500/40',
      bg: 'bg-amber-500/5',
      icon: 'text-amber-500',
      button: 'bg-amber-600 hover:bg-amber-700 text-white',
    },
  }

  const c = colors[accentColor]

  return (
    <div className={cn(
      'rounded-lg border p-3 transition-colors',
      c.border,
      c.bg,
    )}>
      <div className="flex items-center gap-2 mb-2">
        <Zap className={cn('h-4 w-4', c.icon)} />
        <span className="text-sm font-semibold">{label}</span>
      </div>

      <p className="text-xs text-muted-foreground mb-3">
        {description}
      </p>

      {warning && (
        <div className="flex items-start gap-1.5 mb-3 rounded-md bg-amber-500/10 border border-amber-500/20 p-2">
          <AlertTriangle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-[10px] text-amber-700 dark:text-amber-300 leading-relaxed">
            {warning}
          </p>
        </div>
      )}

      <Button
        size="sm"
        className={cn('w-full', c.button)}
        onClick={onConnect}
        disabled={isConnecting}
      >
        {isConnecting ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
        ) : (
          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
        )}
        Connect with {label}
      </Button>
    </div>
  )
}

// ============================================================================
// Connected Card
// ============================================================================

interface ConnectedCardProps {
  status: OAuthConnectionStatus
  onDisconnect: () => void
  isDisconnecting: boolean
}

function ConnectedCard({ status, onDisconnect, isDisconnecting }: ConnectedCardProps) {
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false)

  const providerType = (status.provider_type || 'openai') as ProviderType
  const providerLabel = providerType === 'openai' ? 'OpenAI' : 'Anthropic'

  const testOverride = useTestUserOverride()

  const handleTest = useCallback(async () => {
    setTestStatus('testing')
    setTestMessage(null)
    try {
      const result = await testOverride.mutateAsync(providerType)
      if (result.success) {
        setTestStatus('success')
        setTestMessage(
          `Connection successful${result.latency_ms != null ? ` (${result.latency_ms}ms)` : ''}`
        )
      } else {
        setTestStatus('error')
        setTestMessage(result.error || 'Connection failed')
      }
    } catch (err) {
      setTestStatus('error')
      setTestMessage(err instanceof Error ? err.message : 'Test failed')
    }
  }, [providerType, testOverride])

  const connectedAt = status.connected_at
    ? new Date(status.connected_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null

  return (
    <>
      <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3 space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-500" />
          <span className="text-sm font-semibold">Connected to {providerLabel}</span>
        </div>

        {connectedAt && (
          <p className="text-xs text-muted-foreground">
            Connected: {connectedAt}
          </p>
        )}

        {/* Test result */}
        {testMessage && (
          <div
            role="alert"
            className={cn(
              'rounded-md p-2 text-xs',
              testStatus === 'success'
                ? 'bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800'
            )}
          >
            <div className="flex items-center gap-1.5">
              {testStatus === 'success' ? (
                <CheckCircle2 className="h-3 w-3 text-green-600" />
              ) : (
                <XCircle className="h-3 w-3 text-red-600" />
              )}
              {testMessage}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleTest}
            disabled={testStatus === 'testing'}
          >
            {testStatus === 'testing' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : null}
            Test Connection
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDisconnectConfirm(true)}
            className="text-destructive hover:text-destructive ml-auto"
            disabled={isDisconnecting}
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Disconnect
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={showDisconnectConfirm}
        onOpenChange={setShowDisconnectConfirm}
        title="Disconnect AI Subscription?"
        description={`Your ${providerLabel} subscription will be disconnected. You'll fall back to the company default AI provider.`}
        confirmLabel="Disconnect"
        variant="destructive"
        onConfirm={() => {
          setShowDisconnectConfirm(false)
          onDisconnect()
        }}
        isLoading={isDisconnecting}
      />
    </>
  )
}

// ============================================================================
// API Key Fallback (Collapsible)
// ============================================================================

function ApiKeyFallback() {
  const [expanded, setExpanded] = useState(false)
  const [providerType, setProviderType] = useState<ProviderType | ''>('')
  const [apiKey, setApiKey] = useState('')
  const [modelId, setModelId] = useState('')
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false)

  const { data: overrides } = useUserOverrides()
  const createOverride = useCreateUserOverride()
  const deleteOverride = useDeleteUserOverride()
  const testOverride = useTestUserOverride()

  const { data: models } = useAvailableModels(
    providerType ? { provider_type: providerType, capability: 'chat' } : undefined
  )

  // Populate from existing override
  useEffect(() => {
    if (overrides && overrides.length > 0) {
      const existing = overrides[0]
      setProviderType(existing.provider_type as ProviderType)
      if (existing.models?.length > 0) {
        setModelId(existing.models[0].model_id)
      }
      // Auto-expand if user has an existing API key override
      setExpanded(true)
    }
  }, [overrides])

  const handleProviderChange = useCallback((value: string) => {
    setProviderType(value as ProviderType)
    setApiKey('')
    setModelId('')
    setTestStatus('idle')
    setTestMessage(null)
  }, [])

  const handleSave = useCallback(async () => {
    if (!providerType || !apiKey) return
    try {
      await createOverride.mutateAsync({
        provider_type: providerType,
        api_key: apiKey,
        preferred_model: modelId || undefined,
      })
      setApiKey('')
      setTestStatus('idle')
      setTestMessage(null)
    } catch {
      // Error handled by mutation
    }
  }, [providerType, apiKey, modelId, createOverride])

  const handleTest = useCallback(async () => {
    if (!providerType) return
    const hasExisting = overrides && overrides.some((o) => o.provider_type === providerType)
    if (!hasExisting) {
      if (!apiKey) {
        setTestStatus('error')
        setTestMessage('Please enter an API key first')
        return
      }
      try {
        await createOverride.mutateAsync({
          provider_type: providerType,
          api_key: apiKey,
          preferred_model: modelId || undefined,
        })
      } catch {
        setTestStatus('error')
        setTestMessage('Failed to save before testing')
        return
      }
    }

    setTestStatus('testing')
    setTestMessage(null)
    try {
      const result = await testOverride.mutateAsync(providerType)
      if (result.success) {
        setTestStatus('success')
        setTestMessage(result.message || 'Connection successful')
      } else {
        setTestStatus('error')
        setTestMessage(result.error || 'Connection failed')
      }
    } catch (err) {
      setTestStatus('error')
      setTestMessage(err instanceof Error ? err.message : 'Test failed')
    }
  }, [providerType, apiKey, modelId, overrides, createOverride, testOverride])

  const handleRemove = useCallback(async () => {
    if (!providerType) return
    try {
      await deleteOverride.mutateAsync(providerType)
      setProviderType('')
      setApiKey('')
      setModelId('')
      setTestStatus('idle')
      setTestMessage(null)
      setShowRemoveConfirm(false)
    } catch {
      // Error handled by mutation
    }
  }, [providerType, deleteOverride])

  const hasExistingOverride = overrides && overrides.length > 0
  const isMutating = createOverride.isPending || deleteOverride.isPending || testOverride.isPending

  return (
    <div className="border-t border-border pt-3">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-left"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Key className="h-3 w-3" />
        Advanced: Use API Key Instead
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 animate-fade-in">
          {/* Provider Selection */}
          <div className="space-y-1.5">
            <Label>Provider</Label>
            <div className="flex items-center gap-4" role="radiogroup" aria-label="AI provider">
              {(['openai', 'anthropic'] as const).map((p) => (
                <label
                  key={p}
                  className={cn(
                    'flex items-center gap-2 text-xs',
                    isMutating ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
                  )}
                >
                  <input
                    type="radio"
                    name="override-provider"
                    value={p}
                    checked={providerType === p}
                    onChange={() => handleProviderChange(p)}
                    disabled={isMutating}
                    className="h-3 w-3 accent-primary"
                  />
                  {p === 'openai' ? 'OpenAI' : 'Anthropic'}
                </label>
              ))}
            </div>
          </div>

          {/* API Key */}
          {providerType && (
            <div className="space-y-1.5">
              <Label htmlFor="override-apikey">
                API Key <span className="text-destructive">*</span>
              </Label>
              <Input
                id="override-apikey"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  hasExistingOverride
                    ? 'Key configured (enter new to replace)'
                    : 'Enter your personal API key...'
                }
              />
            </div>
          )}

          {/* Model Dropdown */}
          {providerType && (
            <div className="space-y-1.5">
              <Label htmlFor="override-model">Model</Label>
              <Select value={modelId} onValueChange={setModelId}>
                <SelectTrigger id="override-model">
                  <SelectValue placeholder="Select model..." />
                </SelectTrigger>
                <SelectContent>
                  {models?.map((m: AiModelResponse) => (
                    <SelectItem key={m.id} value={m.model_id}>
                      {m.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Test Result */}
          {testMessage && (
            <div
              role="alert"
              className={cn(
                'rounded-md p-2.5 text-xs',
                testStatus === 'success'
                  ? 'bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800'
              )}
            >
              <div className="flex items-center gap-1.5">
                {testStatus === 'success' ? (
                  <CheckCircle2 className="h-3 w-3 text-green-600" />
                ) : (
                  <XCircle className="h-3 w-3 text-red-600" />
                )}
                {testMessage}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleTest}
              disabled={!providerType || testStatus === 'testing' || createOverride.isPending}
            >
              {testStatus === 'testing' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : null}
              Test
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!providerType || !apiKey || createOverride.isPending}
            >
              {createOverride.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : null}
              Save
            </Button>
            {hasExistingOverride && (
              <>
                {!showRemoveConfirm ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowRemoveConfirm(true)}
                    className="text-destructive hover:text-destructive ml-auto"
                    aria-label="Remove API key override"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                ) : (
                  <div className="flex items-center gap-1 ml-auto">
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleRemove}
                      disabled={deleteOverride.isPending}
                    >
                      {deleteOverride.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                      ) : null}
                      Remove
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowRemoveConfirm(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// UserChatOverride (main content)
// ============================================================================

function UserChatOverrideContent(_props: { onClose: () => void }) {
  const { data: oauthStatus } = useOAuthStatus()
  const initiate = useOAuthInitiate()
  const disconnect = useOAuthDisconnect()
  const [oauthError, setOAuthError] = useState<string | null>(null)

  const handleConnect = useCallback(async (providerType: ProviderType) => {
    setOAuthError(null)
    try {
      await initiate.mutateAsync({ provider_type: providerType })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'OAuth flow failed'
      setOAuthError(message)
    }
  }, [initiate])

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnect.mutateAsync()
    } catch {
      // Error handled by mutation
    }
  }, [disconnect])

  const isConnecting = initiate.isPending

  return (
    <div className="w-80 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Settings className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">AI Settings</h3>
      </div>

      <p className="text-xs text-muted-foreground">
        Connect your AI subscription to power Blair.
        Otherwise, the company default will be used.
      </p>

      {/* OAuth Error Banner */}
      {oauthError && (
        <div role="alert" className="flex items-start gap-2 rounded-md bg-red-500/10 border border-red-500/20 p-2.5">
          <XCircle className="h-3.5 w-3.5 text-red-500 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p className="text-xs text-red-700 dark:text-red-300">{oauthError}</p>
            {oauthError.includes('cancelled') || oauthError.includes('timed out') ? (
              <button
                type="button"
                onClick={() => setOAuthError(null)}
                className="text-[10px] text-red-600 dark:text-red-400 underline hover:no-underline"
              >
                Try again
              </button>
            ) : (
              <p className="text-[10px] text-red-600 dark:text-red-400">
                Try using an API key instead (expand "Advanced" below).
              </p>
            )}
          </div>
        </div>
      )}

      {/* Connected State */}
      {oauthStatus?.connected && (
        <ConnectedCard
          status={oauthStatus}
          onDisconnect={handleDisconnect}
          isDisconnecting={disconnect.isPending}
        />
      )}

      {/* Provider Cards (disconnected state) */}
      {!oauthStatus?.connected && (
        <div className="space-y-2">
          <ProviderCard
            providerType="openai"
            label="OpenAI"
            description="Connect your ChatGPT Plus or Pro subscription to use GPT models."
            accentColor="green"
            isConnecting={isConnecting}
            onConnect={() => handleConnect('openai')}
          />

          <ProviderCard
            providerType="anthropic"
            label="Anthropic"
            description="Connect your Claude subscription."
            accentColor="amber"
            warning="Anthropic may block third-party apps from using subscription tokens. If connection fails, use an API key instead."
            isConnecting={isConnecting}
            onConnect={() => handleConnect('anthropic')}
          />
        </div>
      )}

      {/* API Key Fallback */}
      <ApiKeyFallback />

      {/* Status Line */}
      <EffectiveConfigStatus />

      {/* Security Note */}
      <div className="flex items-start gap-1.5">
        <Shield className="h-3 w-3 text-muted-foreground mt-0.5 shrink-0" />
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          Your credentials are encrypted and never shared. Remove anytime to use company default.
        </p>
      </div>
    </div>
  )
}

// ============================================================================
// Popover Trigger (for sidebar header)
// ============================================================================

export function UserChatOverrideButton() {
  const [open, setOpen] = useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-lg hover:bg-muted/80"
          aria-label="Chat settings"
        >
          <Settings className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="bottom" align="end" className="w-auto p-4">
        <UserChatOverrideContent onClose={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  )
}

export default UserChatOverrideButton
