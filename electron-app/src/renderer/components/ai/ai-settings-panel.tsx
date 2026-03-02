/**
 * Developer AI Settings Panel
 *
 * Gated on current_user.is_developer. Provides per-capability
 * configuration for Chat, Embedding, and Vision AI providers.
 *
 * Layout: Radix Tabs with 3 tabs:
 * - AI Config: CapabilityConfigSection x3
 * - Indexing: Document embedding status table with reindex actions
 * - Blair's Personality: System prompt customization
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import {
  Settings2,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Eye,
  MessageSquare,
  Database,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
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
import { useCurrentUser } from '@/hooks/use-auth'
import { useAuthToken, getAuthHeaders } from '@/contexts/auth-context'
import { toast } from 'sonner'
import {
  useAiModels,
  useAiProviders,
  useSaveCapabilityConfig,
  useCapabilityConfig,
  type AiModelResponse,
  type AiProviderResponse,
  type TestProviderResult,
} from '@/hooks/use-ai-config'
import { IndexingTab } from './indexing-tab'
import { PersonalityTab } from './personality-tab'
import { ProvidersModelsTab } from './providers-models-tab'

// ============================================================================
// Types
// ============================================================================

type Capability = 'chat' | 'embedding' | 'vision'
type ProviderType = 'openai' | 'anthropic' | 'ollama'
type TestStatus = 'idle' | 'testing' | 'success' | 'error'

interface CapabilityState {
  providerType: ProviderType | ''
  apiKey: string
  modelId: string
  baseUrl: string
  testStatus: TestStatus
  testResult: TestProviderResult | null
  isDirty: boolean
}

const PROVIDER_OPTIONS: { value: ProviderType; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
]

const CAPABILITY_LABELS: Record<Capability, string> = {
  chat: 'Chat',
  embedding: 'Embedding',
  vision: 'Vision',
}

const CAPABILITY_ICONS: Record<Capability, typeof MessageSquare> = {
  chat: MessageSquare,
  embedding: Database,
  vision: Eye,
}

const PROVIDER_LABELS: Record<string, string> = Object.fromEntries(
  PROVIDER_OPTIONS.map((p) => [p.value, p.label])
)

// Sentinel value displayed in the password field when a key already exists.
// Shows as dots in type="password". Never sent to the backend.
const EXISTING_KEY_SENTINEL = '__EXISTING_KEY__'

// ============================================================================
// CapabilityConfigSection
// ============================================================================

interface CapabilityConfigSectionProps {
  capability: Capability
  providers: AiProviderResponse[] | undefined
}

function CapabilityConfigSection({
  capability,
  providers,
}: CapabilityConfigSectionProps) {
  const [state, setState] = useState<CapabilityState>({
    providerType: '',
    apiKey: '',
    modelId: '',
    baseUrl: '',
    testStatus: 'idle',
    testResult: null,
    isDirty: false,
  })

  const token = useAuthToken()
  const { data: currentConfig, isLoading: configLoading, isError: configError } = useCapabilityConfig(capability)
  const saveConfig = useSaveCapabilityConfig()

  // Sync server config into local form state when config changes and form is clean.
  // Uses a fingerprint ref to avoid re-triggering on the same data.
  const lastSyncedRef = useRef<string | null>(null)
  useEffect(() => {
    if (!currentConfig) return
    const fingerprint = `${currentConfig.provider_type ?? ''}|${currentConfig.model_id ?? ''}|${currentConfig.has_api_key}|${currentConfig.base_url ?? ''}`
    if (fingerprint !== lastSyncedRef.current && !state.isDirty) {
      setState((prev) => ({
        ...prev,
        providerType: (currentConfig.provider_type as ProviderType) || '',
        modelId: currentConfig.model_id || '',
        baseUrl: currentConfig.base_url || '',
        // Fill sentinel when provider already has a key stored
        apiKey: currentConfig.has_api_key ? EXISTING_KEY_SENTINEL : '',
      }))
      lastSyncedRef.current = fingerprint
    }
  }, [currentConfig, state.isDirty])

  // Filter providers: embedding excludes Anthropic
  const availableProviders = useMemo(() => {
    if (capability === 'embedding') {
      return PROVIDER_OPTIONS.filter((p) => p.value !== 'anthropic')
    }
    return PROVIDER_OPTIONS
  }, [capability])

  // Fetch models for selected provider + capability
  const { data: models } = useAiModels(
    state.providerType
      ? { provider_type: state.providerType, capability }
      : undefined
  )

  // Check if the selected provider already has a key stored in the DB.
  // This covers cross-capability key awareness: if Chat saved an OpenAI key,
  // Embedding and Vision sections for OpenAI will show "Key configured".
  const providerHasKey = useMemo(() => {
    if (!state.providerType || !providers) return false
    return providers.some(
      (p) => p.provider_type === state.providerType && p.has_api_key
    )
  }, [state.providerType, providers])

  const handleProviderChange = useCallback((value: string) => {
    // Check if the newly selected provider already has a key stored
    const newProviderHasKey = providers?.some(
      (p) => p.provider_type === value && p.has_api_key
    ) ?? false

    setState((prev) => ({
      ...prev,
      providerType: value as ProviderType,
      apiKey: newProviderHasKey ? EXISTING_KEY_SENTINEL : '',
      modelId: '',
      baseUrl: value === 'ollama' ? 'http://localhost:11434' : '',
      testStatus: 'idle',
      testResult: null,
      isDirty: true,
    }))
  }, [providers])

  const handleModelChange = useCallback((value: string) => {
    setState((prev) => ({
      ...prev,
      modelId: value,
      isDirty: true,
      testStatus: 'idle',
      testResult: null,
    }))
  }, [])

  // Clear sentinel on focus so user can type a fresh key
  const handleApiKeyFocus = useCallback(() => {
    setState((prev) => {
      if (prev.apiKey === EXISTING_KEY_SENTINEL) {
        return { ...prev, apiKey: '' }
      }
      return prev
    })
  }, [])

  // Restore sentinel on blur if user didn't type anything
  const handleApiKeyBlur = useCallback(() => {
    setState((prev) => {
      if (!prev.apiKey && (currentConfig?.has_api_key || providerHasKey)) {
        // Restore sentinel but preserve isDirty if other fields were changed
        return { ...prev, apiKey: EXISTING_KEY_SENTINEL }
      }
      return prev
    })
  }, [currentConfig?.has_api_key, providerHasKey])

  const handleApiKeyChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setState((prev) => ({
        ...prev,
        apiKey: e.target.value,
        isDirty: true,
        testStatus: 'idle',
        testResult: null,
      }))
    },
    []
  )

  const handleBaseUrlChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setState((prev) => ({
      ...prev,
      baseUrl: e.target.value,
      isDirty: true,
      testStatus: 'idle',
      testResult: null,
    }))
  }, [])

  // Resolve the actual API key to send — sentinel means "use existing" (undefined)
  const resolveApiKey = useCallback(() => {
    if (!state.apiKey || state.apiKey === EXISTING_KEY_SENTINEL) return undefined
    return state.apiKey
  }, [state.apiKey])

  const handleTest = useCallback(async () => {
    if (!state.providerType || !state.modelId || !token) return
    if (state.testStatus === 'testing') return // prevent rapid double-clicks

    setState((prev) => ({ ...prev, testStatus: 'testing', testResult: null }))

    try {
      // Send config inline so test works without saving first
      if (!window.electronAPI) throw new Error('Electron API not available')
      const response = await window.electronAPI.post<TestProviderResult>(
        `/api/ai/config/test/${capability}`,
        {
          provider_type: state.providerType,
          api_key: resolveApiKey(),
          model_id: state.modelId,
          base_url: state.baseUrl || undefined,
        },
        getAuthHeaders(token),
      )

      if (response.status === 200 && response.data) {
        const result = response.data
        setState((prev) => ({
          ...prev,
          testStatus: result.success ? 'success' : 'error',
          testResult: result,
        }))
      } else {
        setState((prev) => ({
          ...prev,
          testStatus: 'error',
          testResult: { success: false, error: 'Test request failed' },
        }))
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        testStatus: 'error',
        testResult: {
          success: false,
          error: err instanceof Error ? err.message : 'Test failed',
        },
      }))
    }
  }, [capability, state.providerType, state.modelId, state.baseUrl, token, resolveApiKey])

  const handleSave = useCallback(async () => {
    if (!state.providerType) return

    try {
      await saveConfig.mutateAsync({
        capability,
        body: {
          provider_type: state.providerType,
          api_key: resolveApiKey(),
          model_id: state.modelId || undefined,
          base_url: state.baseUrl || undefined,
        },
      })
      // After save, show sentinel (key is now stored) — skip for Ollama (no API key)
      setState((prev) => ({
        ...prev,
        isDirty: false,
        apiKey: prev.providerType === 'ollama' ? '' : EXISTING_KEY_SENTINEL,
      }))
      toast.success(`${CAPABILITY_LABELS[capability]} configuration saved`)
    } catch {
      toast.error(`Failed to save ${CAPABILITY_LABELS[capability]} configuration`)
    }
  }, [capability, state.providerType, state.modelId, state.baseUrl, saveConfig, resolveApiKey])

  const Icon = CAPABILITY_ICONS[capability]

  if (configLoading) {
    return (
      <div aria-busy="true" aria-label={`Loading ${CAPABILITY_LABELS[capability]} configuration`} className="rounded-lg border border-border p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-5 rounded" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        {/* Provider dropdown */}
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-14" />
          <Skeleton className="h-9 w-full rounded-md" />
        </div>
        {/* API Key */}
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-9 w-full rounded-md" />
        </div>
        {/* Model dropdown */}
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-9 w-full rounded-md" />
        </div>
        {/* Buttons */}
        <div className="flex items-center gap-2 pt-1">
          <Skeleton className="h-8 w-24 rounded-md" />
          <Skeleton className="h-8 w-16 rounded-md" />
        </div>
      </div>
    )
  }

  if (configError) {
    return (
      <div className="rounded-lg border border-destructive/50 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-destructive" />
          <h3 className="text-sm font-semibold">{CAPABILITY_LABELS[capability]}</h3>
        </div>
        <p className="text-xs text-destructive">
          Failed to load configuration. Check your connection and try again.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{CAPABILITY_LABELS[capability]}</h3>
        </div>
        <StatusIndicator status={state.testStatus} />
      </div>

      {/* Provider Dropdown */}
      <div className="space-y-1.5">
        <Label htmlFor={`provider-${capability}`}>Provider</Label>
        <Select value={state.providerType} onValueChange={handleProviderChange}>
          <SelectTrigger id={`provider-${capability}`}>
            <SelectValue placeholder="Select provider..." />
          </SelectTrigger>
          <SelectContent>
            {availableProviders.map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* API Key Input */}
      {state.providerType && state.providerType !== 'ollama' && (
        <div className="space-y-1.5">
          <Label htmlFor={`apikey-${capability}`}>
            API Key <span className="text-destructive">*</span>
          </Label>
          <Input
            id={`apikey-${capability}`}
            type="password"
            value={state.apiKey}
            onChange={handleApiKeyChange}
            onFocus={handleApiKeyFocus}
            onBlur={handleApiKeyBlur}
            placeholder="Enter API key..."
            aria-description={providerHasKey ? 'An API key is already configured. Leave empty to keep the existing key.' : undefined}
          />
          {providerHasKey && state.apiKey === EXISTING_KEY_SENTINEL && (
            <p className="text-xs text-muted-foreground">
              Shared with other {PROVIDER_LABELS[state.providerType] ?? state.providerType} capabilities. Updating here will apply to all.
            </p>
          )}
        </div>
      )}

      {/* Base URL (Ollama only) */}
      {state.providerType === 'ollama' && (
        <div className="space-y-1.5">
          <Label htmlFor={`baseurl-${capability}`}>Base URL</Label>
          <Input
            id={`baseurl-${capability}`}
            type="url"
            value={state.baseUrl}
            onChange={handleBaseUrlChange}
            placeholder="http://localhost:11434"
          />
        </div>
      )}

      {/* Model Dropdown */}
      {state.providerType && (
        <div className="space-y-1.5">
          <Label htmlFor={`model-${capability}`}>Model</Label>
          <Select
            value={state.modelId}
            onValueChange={handleModelChange}
            disabled={!state.providerType}
          >
            <SelectTrigger id={`model-${capability}`}>
              <SelectValue placeholder="Select model..." />
            </SelectTrigger>
            <SelectContent>
              {models?.map((m: AiModelResponse) => (
                <SelectItem key={m.id} value={m.model_id}>
                  {m.display_name}
                </SelectItem>
              ))}
              {(!models || models.length === 0) && (
                <div className="px-2 py-1.5 text-sm text-muted-foreground">
                  No models available
                </div>
              )}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Embedding model change warning */}
      {capability === 'embedding' && state.isDirty && currentConfig?.model_id && state.modelId !== currentConfig.model_id && (
        <div role="alert" className="flex items-start gap-2 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 p-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <p className="text-xs text-amber-800 dark:text-amber-200">
            Changing the embedding model requires re-embedding all documents.
            This may take significant time and API cost.
          </p>
        </div>
      )}

      {/* Test Result */}
      {state.testResult && (
        <div
          role="alert"
          className={`rounded-md p-3 text-xs ${
            state.testResult.success
              ? 'bg-green-50 dark:bg-green-950/30 text-green-800 dark:text-green-200 border border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800'
          }`}
        >
          {state.testResult.success
            ? `${state.testResult.message || 'Connection successful'}${state.testResult.latency_ms != null ? ` (${state.testResult.latency_ms}ms)` : ''}`
            : state.testResult.error || state.testResult.message || 'Connection failed'}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={handleTest}
          disabled={!state.providerType || !state.modelId || state.testStatus === 'testing' || saveConfig.isPending}
        >
          {state.testStatus === 'testing' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
          ) : null}
          Test {CAPABILITY_LABELS[capability]}
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!state.providerType || !state.modelId || !state.isDirty || saveConfig.isPending || state.testStatus === 'testing'}
        >
          {saveConfig.isPending && state.testStatus !== 'testing' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
          ) : null}
          Save
        </Button>
      </div>
    </div>
  )
}

// ============================================================================
// Status Indicator
// ============================================================================

function StatusIndicator({
  status,
}: {
  status: TestStatus
}) {
  const content = (() => {
    switch (status) {
      case 'testing':
        return (
          <span className="flex items-center gap-1 text-xs text-amber-600">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Testing...
          </span>
        )
      case 'success':
        return (
          <span className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Connected
          </span>
        )
      case 'error':
        return (
          <span className="flex items-center gap-1 text-xs text-red-600">
            <XCircle className="h-3.5 w-3.5" />
            Error
          </span>
        )
      default:
        return null
    }
  })()

  return <span role="status" aria-live="polite">{content}</span>
}

// ============================================================================
// AiSettingsPanel (Main Export)
// ============================================================================

export function AiSettingsPanel() {
  const user = useCurrentUser()

  // Fetch global providers once — passed to each section for cross-capability
  // key awareness (e.g., OpenAI key saved for Chat also applies to Vision).
  const { data: providers } = useAiProviders()

  // Gate on is_developer
  if (!user?.is_developer) {
    return null
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Settings2 className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-sm font-semibold">AI Settings</h2>
      </div>

      <Tabs defaultValue="config" className="flex flex-col flex-1 min-h-0">
        <TabsList aria-label="AI settings tabs">
          <TabsTrigger value="config">AI Config</TabsTrigger>
          <TabsTrigger value="indexing">Indexing</TabsTrigger>
          <TabsTrigger value="personality">Blair's Personality</TabsTrigger>
          <TabsTrigger value="providers-models">Providers & Models</TabsTrigger>
        </TabsList>

        <TabsContent value="config" className="flex-1 overflow-y-auto p-4 space-y-4">
          <CapabilityConfigSection
            capability="chat"
            providers={providers}
          />
          <CapabilityConfigSection
            capability="embedding"
            providers={providers}
          />
          <CapabilityConfigSection
            capability="vision"
            providers={providers}
          />
        </TabsContent>

        <TabsContent value="indexing" className="flex-1 overflow-y-auto p-4">
          <IndexingTab applicationId={null} />
        </TabsContent>

        <TabsContent value="personality" className="flex-1 overflow-y-auto p-4">
          <PersonalityTab />
        </TabsContent>

        <TabsContent value="providers-models" className="flex-1 overflow-y-auto p-4">
          <ProvidersModelsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default AiSettingsPanel
