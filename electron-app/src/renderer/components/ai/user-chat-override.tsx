/**
 * User Chat Override Component — Subscription Token Connect
 *
 * Allows any authenticated user to connect their AI subscription via
 * a session token (obtained from CLI like `claude setup-token`) or
 * fall back to a manual API key. Accessible from the chat sidebar gear icon.
 *
 * Features:
 * - Token paste form for OpenAI and Anthropic
 * - Server-side token validation before saving
 * - Connected state with test, disconnect
 * - Collapsible "Advanced: Use API Key Instead" section
 * - Status line showing effective configuration
 * - ConfirmDialog for disconnect confirmation
 */

import { useState, useCallback } from 'react'
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
  Key,
  Clipboard,
  Terminal,
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
  useSubscriptionTokenStatus,
  useSaveSubscriptionToken,
  useTestSubscriptionToken,
  useDisconnectSubscription,
  type SubscriptionTokenStatus,
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

function EffectiveConfigStatus({ tokenStatus }: { tokenStatus: SubscriptionTokenStatus | undefined }) {
  const { data: effectiveConfig, isLoading } = useUserEffectiveConfig()
  const { data: overrides } = useUserOverrides()

  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading...
      </div>
    )
  }

  // Subscription token connected
  if (tokenStatus?.connected) {
    const provider = tokenStatus.provider_type
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
// Subscription Token Form (Disconnected State)
// ============================================================================

function SubscriptionTokenForm() {
  const [providerType, setProviderType] = useState<ProviderType | ''>('')
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { mutateAsync: saveTokenAsync, isPending: isSavePending } = useSaveSubscriptionToken()

  const handleSave = useCallback(async () => {
    if (!providerType || !token.trim()) return
    setError(null)

    try {
      await saveTokenAsync({
        provider_type: providerType,
        token: token.trim(),
      })
      setToken('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save token')
    }
  }, [providerType, token, saveTokenAsync])

  const providerLabel = providerType === 'openai' ? 'OpenAI' : 'Anthropic'
  const cliCommand = providerType === 'anthropic'
    ? 'claude setup-token'
    : 'openai auth token'

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Terminal className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Connect Your Subscription</span>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Use your AI subscription instead of the company default.
          Get a session token from your provider&apos;s CLI and paste it below.
        </p>
      </div>

      {/* Provider Selection */}
      <div className="space-y-1.5">
        <Label>Provider</Label>
        <div className="flex items-center gap-4" role="radiogroup" aria-label="AI provider">
          {(['openai', 'anthropic'] as const).map((p) => (
            <label
              key={p}
              className="flex items-center gap-2 text-xs cursor-pointer"
            >
              <input
                type="radio"
                name="token-provider"
                value={p}
                checked={providerType === p}
                onChange={() => {
                  setProviderType(p)
                  setToken('')
                  setError(null)
                }}
                className="h-3 w-3 accent-primary"
              />
              {p === 'openai' ? 'OpenAI' : 'Anthropic'}
            </label>
          ))}
        </div>
      </div>

      {/* CLI Instruction */}
      {providerType && (
        <div className="rounded-md bg-muted/50 border border-border p-2.5">
          <p className="text-[10px] text-muted-foreground mb-1.5">
            Run this in your terminal to get a token:
          </p>
          <div className="flex items-center gap-2">
            <code className="text-xs bg-background rounded px-2 py-1 font-mono flex-1">
              {cliCommand}
            </code>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              onClick={() => navigator.clipboard.writeText(cliCommand)}
              aria-label="Copy command"
            >
              <Clipboard className="h-3 w-3" />
            </Button>
          </div>
        </div>
      )}

      {/* Token Input */}
      {providerType && (
        <div className="space-y-1.5">
          <Label htmlFor="subscription-token">
            {providerLabel} Session Token <span className="text-destructive">*</span>
          </Label>
          <Input
            id="subscription-token"
            type="password"
            value={token}
            onChange={(e) => {
              setToken(e.target.value)
              setError(null)
            }}
            placeholder="Paste your session token here..."
            aria-required="true"
            aria-describedby="subscription-token-hint"
          />
          <p id="subscription-token-hint" className="sr-only">
            Paste the session token obtained from your provider CLI
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          role="alert"
          className="flex items-start gap-1.5 rounded-md bg-red-500/10 border border-red-500/20 p-2.5"
        >
          <XCircle className="h-3.5 w-3.5 text-red-500 mt-0.5 shrink-0" />
          <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Save Button */}
      {providerType && (
        <Button
          size="sm"
          className="w-full"
          onClick={handleSave}
          disabled={!token.trim() || isSavePending}
        >
          {isSavePending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
          )}
          Validate & Connect
        </Button>
      )}
    </div>
  )
}

// ============================================================================
// Connected Card
// ============================================================================

interface ConnectedCardProps {
  providerType: string
  modelId: string | null
  connectedAt: string | null
  onDisconnect: () => void
  isDisconnecting: boolean
}

function ConnectedCard({ providerType, modelId, connectedAt, onDisconnect, isDisconnecting }: ConnectedCardProps) {
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false)

  const providerLabel = providerType === 'openai' ? 'OpenAI' : 'Anthropic'
  const { mutateAsync: testTokenAsync } = useTestSubscriptionToken()

  const handleTest = useCallback(async () => {
    setTestStatus('testing')
    setTestMessage(null)
    try {
      const result = await testTokenAsync()
      if (result.success) {
        setTestStatus('success')
        setTestMessage(
          `Connection valid${result.latency_ms != null ? ` (${result.latency_ms}ms)` : ''}`
        )
      } else {
        setTestStatus('error')
        setTestMessage(result.message || 'Token validation failed')
      }
    } catch (err) {
      setTestStatus('error')
      setTestMessage(err instanceof Error ? err.message : 'Test failed')
    }
  }, [testTokenAsync])

  const formattedDate = connectedAt
    ? new Date(connectedAt).toLocaleDateString('en-US', {
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

        <div className="space-y-1">
          {modelId && (
            <p className="text-xs text-muted-foreground">
              Model: {modelId}
            </p>
          )}
          {formattedDate && (
            <p className="text-xs text-muted-foreground">
              Connected: {formattedDate}
            </p>
          )}
        </div>

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
        onOpenChange={(open) => {
          // Prevent dismiss (backdrop click / Escape) while disconnect is in-flight
          if (!open && isDisconnecting) return
          setShowDisconnectConfirm(open)
        }}
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
  const { data: overrides } = useUserOverrides()

  // Hydrate initial state from existing override (survives unmount/remount
  // because overrides come from TanStack cache and are available synchronously)
  const [expanded, setExpanded] = useState(() => {
    return overrides != null && overrides.length > 0
  })
  const [providerType, setProviderType] = useState<ProviderType | ''>(() => {
    const existing = overrides?.[0]
    if (existing?.provider_type === 'openai' || existing?.provider_type === 'anthropic') {
      return existing.provider_type
    }
    return ''
  })
  const [apiKey, setApiKey] = useState('')
  const [modelId, setModelId] = useState(() => {
    return overrides?.[0]?.models?.[0]?.model_id ?? ''
  })
  const [testStatus, setTestStatus] = useState<TestStatus>('idle')
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false)

  const { mutateAsync: createOverrideAsync, isPending: isCreatePending } = useCreateUserOverride()
  const { mutateAsync: deleteOverrideAsync, isPending: isDeletePending } = useDeleteUserOverride()
  const { mutateAsync: testOverrideAsync, isPending: isTestPending } = useTestUserOverride()

  const { data: models } = useAvailableModels(
    providerType ? { provider_type: providerType, capability: 'chat' } : undefined
  )

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
      await createOverrideAsync({
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
  }, [providerType, apiKey, modelId, createOverrideAsync])

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
        await createOverrideAsync({
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
      const result = await testOverrideAsync(providerType)
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
  }, [providerType, apiKey, modelId, overrides, createOverrideAsync, testOverrideAsync])

  const handleRemove = useCallback(async () => {
    if (!providerType) return
    try {
      await deleteOverrideAsync(providerType)
      setProviderType('')
      setApiKey('')
      setModelId('')
      setTestStatus('idle')
      setTestMessage(null)
      setShowRemoveConfirm(false)
    } catch {
      // Error handled by mutation
    }
  }, [providerType, deleteOverrideAsync])

  const hasExistingOverride = overrides && overrides.length > 0
  const isMutating = isCreatePending || isDeletePending || isTestPending

  return (
    <div className="border-t border-border pt-3">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-left"
        aria-expanded={expanded}
        aria-controls="api-key-section"
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
        <div id="api-key-section" className="mt-3 space-y-3 animate-fade-in">
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
              disabled={!providerType || testStatus === 'testing' || isCreatePending}
            >
              {testStatus === 'testing' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              ) : null}
              Test
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!providerType || !apiKey || isCreatePending}
            >
              {isCreatePending ? (
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
                      disabled={isDeletePending}
                    >
                      {isDeletePending ? (
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

function UserChatOverrideContent() {
  const { data: tokenStatus } = useSubscriptionTokenStatus()
  const { mutateAsync: disconnectAsync, isPending: isDisconnecting } = useDisconnectSubscription()

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectAsync()
    } catch {
      // Error handled by mutation
    }
  }, [disconnectAsync])

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

      {/* Connected State */}
      {tokenStatus?.connected && (
        <ConnectedCard
          providerType={tokenStatus.provider_type || 'openai'}
          modelId={tokenStatus.model_id}
          connectedAt={tokenStatus.connected_at}
          onDisconnect={handleDisconnect}
          isDisconnecting={isDisconnecting}
        />
      )}

      {/* Token Form (disconnected state) */}
      {!tokenStatus?.connected && (
        <SubscriptionTokenForm />
      )}

      {/* API Key Fallback */}
      <ApiKeyFallback />

      {/* Status Line */}
      <EffectiveConfigStatus tokenStatus={tokenStatus} />

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
        <UserChatOverrideContent />
      </PopoverContent>
    </Popover>
  )
}

export default UserChatOverrideButton
