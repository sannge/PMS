/**
 * Providers & Models Management Tab
 *
 * CRUD table for managing AI models under existing providers.
 * Shows all models with provider + capability filters.
 * Add/Edit via Radix Dialog, Delete via ConfirmDialog.
 *
 * Reuses hooks: useAiModels, useAiProviders, useCreateAiModel,
 * useUpdateAiModel, useDeleteAiModel from use-ai-config.ts
 */

import { useState, useCallback, useMemo } from 'react'
import {
  Plus,
  Pencil,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  useAiModels,
  useAiProviders,
  useCreateAiModel,
  useUpdateAiModel,
  useDeleteAiModel,
  type AiModelResponse,
  type AiProviderResponse,
  type AiModelCreate,
  type AiModelUpdate,
} from '@/hooks/use-ai-config'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

type Capability = 'chat' | 'embedding' | 'vision'
const ALL_PROVIDERS_SENTINEL = '__all__'
type FilterProviderType = typeof ALL_PROVIDERS_SENTINEL | 'openai' | 'anthropic' | 'ollama'
const ALL_CAPABILITIES_SENTINEL = '__all__'
type FilterCapability = typeof ALL_CAPABILITIES_SENTINEL | Capability

interface ModelFormData {
  provider_id: string
  model_id: string
  display_name: string
  capability: Capability | ''
  embedding_dimensions: string
  max_tokens: string
  is_default: boolean
  is_enabled: boolean
}

const EMPTY_FORM: ModelFormData = {
  provider_id: '',
  model_id: '',
  display_name: '',
  capability: '',
  embedding_dimensions: '',
  max_tokens: '',
  is_default: false,
  is_enabled: true,
}

const CAPABILITY_OPTIONS: { value: Capability; label: string }[] = [
  { value: 'chat', label: 'Chat' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'vision', label: 'Vision' },
]

const PROVIDER_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
]

// ============================================================================
// Model Form Dialog
// ============================================================================

interface ModelFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  form: ModelFormData
  onChange: (form: ModelFormData) => void
  onSubmit: () => void
  providers: AiProviderResponse[]
  isSubmitting: boolean
  submitLabel: string
}

function ModelFormDialog({
  open,
  onOpenChange,
  title,
  form,
  onChange,
  onSubmit,
  providers,
  isSubmitting,
  submitLabel,
}: ModelFormDialogProps) {
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      onSubmit()
    },
    [onSubmit]
  )

  const isValid = form.provider_id && form.model_id && form.display_name && form.capability

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Provider */}
          <div className="space-y-1.5">
            <Label htmlFor="model-provider">Provider</Label>
            <Select
              value={form.provider_id}
              onValueChange={(v) => onChange({ ...form, provider_id: v })}
            >
              <SelectTrigger id="model-provider">
                <SelectValue placeholder="Select provider..." />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.display_name} ({p.provider_type})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Model ID */}
          <div className="space-y-1.5">
            <Label htmlFor="model-id">Model ID</Label>
            <Input
              id="model-id"
              value={form.model_id}
              onChange={(e) => onChange({ ...form, model_id: e.target.value })}
              placeholder="e.g. gpt-4o, claude-sonnet-4-20250514"
            />
          </div>

          {/* Display Name */}
          <div className="space-y-1.5">
            <Label htmlFor="model-display-name">Display Name</Label>
            <Input
              id="model-display-name"
              value={form.display_name}
              onChange={(e) => onChange({ ...form, display_name: e.target.value })}
              placeholder="e.g. GPT-4o, Claude Sonnet"
            />
          </div>

          {/* Capability */}
          <div className="space-y-1.5">
            <Label htmlFor="model-capability">Capability</Label>
            <Select
              value={form.capability}
              onValueChange={(v) => onChange({ ...form, capability: v as Capability })}
            >
              <SelectTrigger id="model-capability">
                <SelectValue placeholder="Select capability..." />
              </SelectTrigger>
              <SelectContent>
                {CAPABILITY_OPTIONS.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Embedding Dimensions (only for embedding capability) */}
          {form.capability === 'embedding' && (
            <div className="space-y-1.5">
              <Label htmlFor="model-dimensions">Embedding Dimensions</Label>
              <Input
                id="model-dimensions"
                type="number"
                value={form.embedding_dimensions}
                onChange={(e) => onChange({ ...form, embedding_dimensions: e.target.value })}
                placeholder="e.g. 1536"
              />
            </div>
          )}

          {/* Max Tokens */}
          <div className="space-y-1.5">
            <Label htmlFor="model-max-tokens">Max Tokens</Label>
            <Input
              id="model-max-tokens"
              type="number"
              value={form.max_tokens}
              onChange={(e) => onChange({ ...form, max_tokens: e.target.value })}
              placeholder="e.g. 4096"
            />
          </div>

          {/* Toggles row */}
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(e) => onChange({ ...form, is_default: e.target.checked })}
                className="h-4 w-4 rounded accent-primary"
              />
              Default
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_enabled}
                onChange={(e) => onChange({ ...form, is_enabled: e.target.checked })}
                className="h-4 w-4 rounded accent-primary"
              />
              Enabled
            </label>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!isValid || isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// ProvidersModelsTab
// ============================================================================

export function ProvidersModelsTab() {
  const { data: models, isLoading: modelsLoading } = useAiModels()
  const { data: providers, isLoading: providersLoading } = useAiProviders()
  const createModel = useCreateAiModel()
  const updateModel = useUpdateAiModel()
  const deleteModel = useDeleteAiModel()

  // Filters
  const [filterProviderType, setFilterProviderType] = useState<FilterProviderType>(ALL_PROVIDERS_SENTINEL)
  const [filterCapability, setFilterCapability] = useState<FilterCapability>(ALL_CAPABILITIES_SENTINEL)

  // Dialogs
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [editingModel, setEditingModel] = useState<AiModelResponse | null>(null)
  const [deletingModel, setDeletingModel] = useState<AiModelResponse | null>(null)

  // Form state
  const [addForm, setAddForm] = useState<ModelFormData>({ ...EMPTY_FORM })
  const [editForm, setEditForm] = useState<ModelFormData>({ ...EMPTY_FORM })

  // Filtered models
  const filteredModels = useMemo(() => {
    if (!models) return []
    return models.filter((m) => {
      if (filterProviderType !== ALL_PROVIDERS_SENTINEL) {
        // Derive provider_type from provider name or ID
        const provider = providers?.find((p) => p.id === m.provider_id)
        if (provider && provider.provider_type !== filterProviderType) return false
      }
      if (filterCapability !== ALL_CAPABILITIES_SENTINEL && m.capability !== filterCapability) return false
      return true
    })
  }, [models, providers, filterProviderType, filterCapability])

  // Provider lookup map for display
  const providerMap = useMemo(() => {
    const map = new Map<string, AiProviderResponse>()
    providers?.forEach((p) => map.set(p.id, p))
    return map
  }, [providers])

  // Add model
  const handleOpenAdd = useCallback(() => {
    setAddForm({ ...EMPTY_FORM })
    setShowAddDialog(true)
  }, [])

  const handleAdd = useCallback(async () => {
    const body: AiModelCreate = {
      provider_id: addForm.provider_id,
      model_id: addForm.model_id,
      display_name: addForm.display_name,
      capability: addForm.capability,
      embedding_dimensions: addForm.embedding_dimensions ? parseInt(addForm.embedding_dimensions, 10) : null,
      max_tokens: addForm.max_tokens ? parseInt(addForm.max_tokens, 10) : null,
      is_default: addForm.is_default,
      is_enabled: addForm.is_enabled,
    }
    try {
      await createModel.mutateAsync(body)
      setShowAddDialog(false)
    } catch {
      // Error handled by mutation
    }
  }, [addForm, createModel])

  // Edit model
  const handleOpenEdit = useCallback((model: AiModelResponse) => {
    setEditingModel(model)
    setEditForm({
      provider_id: model.provider_id,
      model_id: model.model_id,
      display_name: model.display_name,
      capability: model.capability as Capability,
      embedding_dimensions: model.embedding_dimensions?.toString() ?? '',
      max_tokens: model.max_tokens?.toString() ?? '',
      is_default: model.is_default,
      is_enabled: model.is_enabled,
    })
  }, [])

  const handleEdit = useCallback(async () => {
    if (!editingModel) return
    const body: AiModelUpdate = {
      model_id: editForm.model_id,
      display_name: editForm.display_name,
      capability: editForm.capability || undefined,
      embedding_dimensions: editForm.embedding_dimensions ? parseInt(editForm.embedding_dimensions, 10) : null,
      max_tokens: editForm.max_tokens ? parseInt(editForm.max_tokens, 10) : null,
      is_default: editForm.is_default,
      is_enabled: editForm.is_enabled,
    }
    try {
      await updateModel.mutateAsync({ modelId: editingModel.id, body })
      setEditingModel(null)
    } catch {
      // Error handled by mutation
    }
  }, [editingModel, editForm, updateModel])

  // Delete model
  const handleDelete = useCallback(async () => {
    if (!deletingModel) return
    try {
      await deleteModel.mutateAsync(deletingModel.id)
      setDeletingModel(null)
    } catch {
      // Error handled by mutation
    }
  }, [deletingModel, deleteModel])

  const isLoading = modelsLoading || providersLoading

  if (isLoading) {
    return (
      <div aria-busy="true" aria-label="Loading providers and models" className="space-y-4">
        {/* Header with filters + Add button */}
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-36 rounded-md" />
          <Skeleton className="h-8 w-36 rounded-md" />
          <div className="flex-1" />
          <Skeleton className="h-8 w-24 rounded-md" />
        </div>
        {/* Table */}
        <div className="border rounded-lg overflow-hidden">
          {/* Table header: Model ID | Display Name | Provider | Capability | Dimensions | Default | Enabled | Actions */}
          <div className="flex items-center gap-4 px-3 py-2 border-b bg-muted/40">
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-3.5 w-18" />
            <Skeleton className="h-3.5 w-22" />
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3.5 w-16" />
            <Skeleton className="h-3.5 w-16" />
            <div className="flex-1" />
            <Skeleton className="h-3.5 w-16" />
          </div>
          {/* Table rows */}
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-3 py-2.5 border-b last:border-b-0">
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="h-3.5 w-20" />
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-3.5 w-14" />
              <Skeleton className="h-3.5 w-10" />
              <Skeleton className="h-4 w-4 rounded-full" />
              <Skeleton className="h-2 w-2 rounded-full" />
              <div className="flex-1" />
              <div className="flex items-center gap-1">
                <Skeleton className="h-7 w-7 rounded" />
                <Skeleton className="h-7 w-7 rounded" />
              </div>
            </div>
          ))}
        </div>
        {/* Count */}
        <Skeleton className="h-3 w-20" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header with filters + Add button */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select
          value={filterProviderType}
          onValueChange={(v) => setFilterProviderType(v as FilterProviderType)}
        >
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue placeholder="All Providers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_PROVIDERS_SENTINEL}>All Providers</SelectItem>
            {PROVIDER_TYPE_OPTIONS.map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filterCapability}
          onValueChange={(v) => setFilterCapability(v as FilterCapability)}
        >
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue placeholder="All Capabilities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CAPABILITIES_SENTINEL}>All Capabilities</SelectItem>
            {CAPABILITY_OPTIONS.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex-1" />

        <Button size="sm" onClick={handleOpenAdd} className="h-8">
          <Plus className="h-3.5 w-3.5 mr-1.5" />
          Add Model
        </Button>
      </div>

      {/* Models table */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40">
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Model ID</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Display Name</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Provider</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Capability</th>
              <th className="text-left px-3 py-2 font-medium text-muted-foreground">Dimensions</th>
              <th className="text-center px-3 py-2 font-medium text-muted-foreground">Default</th>
              <th className="text-center px-3 py-2 font-medium text-muted-foreground">Enabled</th>
              <th className="text-right px-3 py-2 font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredModels.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  No models found.{' '}
                  {(filterProviderType !== ALL_PROVIDERS_SENTINEL || filterCapability !== ALL_CAPABILITIES_SENTINEL) && (
                    <button
                      type="button"
                      className="text-primary hover:underline"
                      onClick={() => {
                        setFilterProviderType(ALL_PROVIDERS_SENTINEL)
                        setFilterCapability(ALL_CAPABILITIES_SENTINEL)
                      }}
                    >
                      Clear filters
                    </button>
                  )}
                </td>
              </tr>
            )}
            {filteredModels.map((model) => {
              const provider = providerMap.get(model.provider_id)
              return (
                <tr
                  key={model.id}
                  className="border-b last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="px-3 py-2 font-mono text-xs">{model.model_id}</td>
                  <td className="px-3 py-2">{model.display_name}</td>
                  <td className="px-3 py-2">
                    <span className={cn(
                      'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                      provider?.provider_type === 'openai' && 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
                      provider?.provider_type === 'anthropic' && 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-400',
                      provider?.provider_type === 'ollama' && 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
                    )}>
                      {provider?.display_name ?? model.provider_name}
                    </span>
                  </td>
                  <td className="px-3 py-2 capitalize">{model.capability}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {model.embedding_dimensions ?? '-'}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {model.is_default ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                    ) : (
                      <XCircle className="h-4 w-4 text-muted-foreground/30 mx-auto" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className={cn(
                        'inline-block h-2 w-2 rounded-full',
                        model.is_enabled ? 'bg-green-500' : 'bg-red-400'
                      )}
                      title={model.is_enabled ? 'Enabled' : 'Disabled'}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handleOpenEdit(model)}
                        aria-label={`Edit ${model.display_name}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => setDeletingModel(model)}
                        aria-label={`Delete ${model.display_name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Total count */}
      <p className="text-xs text-muted-foreground">
        {filteredModels.length} model{filteredModels.length !== 1 ? 's' : ''}
        {(filterProviderType !== ALL_PROVIDERS_SENTINEL || filterCapability !== ALL_CAPABILITIES_SENTINEL) && ` (filtered from ${models?.length ?? 0})`}
      </p>

      {/* Add Model Dialog */}
      <ModelFormDialog
        open={showAddDialog}
        onOpenChange={setShowAddDialog}
        title="Add Model"
        form={addForm}
        onChange={setAddForm}
        onSubmit={handleAdd}
        providers={providers ?? []}
        isSubmitting={createModel.isPending}
        submitLabel="Add Model"
      />

      {/* Edit Model Dialog */}
      <ModelFormDialog
        open={!!editingModel}
        onOpenChange={(open) => { if (!open) setEditingModel(null) }}
        title="Edit Model"
        form={editForm}
        onChange={setEditForm}
        onSubmit={handleEdit}
        providers={providers ?? []}
        isSubmitting={updateModel.isPending}
        submitLabel="Save Changes"
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingModel}
        onOpenChange={(open) => { if (!open) setDeletingModel(null) }}
        title="Delete Model"
        description={`Delete model "${deletingModel?.display_name}"? This cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleDelete}
        isLoading={deleteModel.isPending}
      />
    </div>
  )
}

export default ProvidersModelsTab
