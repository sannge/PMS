# Phase 1: LLM Abstraction Layer + Database Setup — Task Breakdown

**Depends on**: Nothing (foundation phase)
**Blocks**: Phase 2, Phase 3.1, Phase 4, Phase 5, Phase 6, Phase 7
**Target files**: `fastapi-backend/app/ai/`, `fastapi-backend/app/routers/ai_config.py`, `fastapi-backend/app/schemas/ai_config.py`, `fastapi-backend/alembic/versions/`, `fastapi-backend/tests/`

---

## 1.1 Database — Migration

**File**: `fastapi-backend/alembic/versions/YYYYMMDD_add_ai_configuration.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.1.1 | Create Alembic migration file following existing pattern (`20260131_drop_notes_create_documents.py`) | DBE | [ ] | |
| 1.1.2 | Define `AiProviders` table with all columns: id (UUID PK), name (VARCHAR 100), display_name (VARCHAR 255), provider_type (VARCHAR 50), base_url (TEXT NULL), api_key_encrypted (TEXT NULL), is_enabled (BOOLEAN DEFAULT true), scope (VARCHAR 20 DEFAULT 'global'), user_id (UUID FK NULL), created_at (TIMESTAMP), updated_at (TIMESTAMP) | DBE | [ ] | |
| 1.1.3 | Define `AiModels` table with all columns: id (UUID PK), provider_id (UUID FK CASCADE), model_id (VARCHAR 255), display_name (VARCHAR 255), capability (VARCHAR 50), embedding_dimensions (INT NULL), max_tokens (INT NULL), is_default (BOOLEAN DEFAULT false), is_enabled (BOOLEAN DEFAULT true), created_at (TIMESTAMP), updated_at (TIMESTAMP) | DBE | [ ] | |
| 1.1.4 | Add FK from `AiProviders.user_id` to `Users.id` | DBE | [ ] | |
| 1.1.5 | Add FK from `AiModels.provider_id` to `AiProviders.id` with `CASCADE` delete | DBE | [ ] | |
| 1.1.6 | Add UNIQUE constraint on `(provider_type, scope, user_id)` on `AiProviders` | DBE | [ ] | Partial unique — NULL user_id for global |
| 1.1.7 | Add UNIQUE constraint on `(provider_id, model_id, capability)` on `AiModels` | DBE | [ ] | |
| 1.1.8 | Implement `downgrade()` function to drop both tables in correct order | DBE | [ ] | AiModels first, then AiProviders |
| 1.1.9 | CR1: Verify FK cascade from AiModels to AiProviders uses CASCADE delete | CR1 | [ ] | |
| 1.1.10 | CR1: Verify UNIQUE constraint on (provider_type, scope, user_id) handles NULL user_id correctly for global scope | CR1 | [ ] | PostgreSQL treats NULLs as distinct in UNIQUE — may need partial index |
| 1.1.11 | QE: Run `alembic upgrade head` — migration succeeds | QE | [ ] | Acceptance criterion |
| 1.1.12 | QE: Run `alembic downgrade -1` — migration is reversible | QE | [ ] | Acceptance criterion |
| 1.1.13 | QE: Verify both tables created with correct column types and constraints via psql inspection | QE | [ ] | Acceptance criterion |
| 1.1.14 | QE: Verify FK from AiProviders.user_id to Users.id exists | QE | [ ] | Acceptance criterion |
| 1.1.15 | QE: Verify FK from AiModels.provider_id to AiProviders.id with CASCADE delete | QE | [ ] | Acceptance criterion |
| 1.1.16 | QE: Verify UNIQUE constraint on (provider_type, scope, user_id) prevents duplicate overrides | QE | [ ] | Acceptance criterion |

---

## 1.2 Database — SQLAlchemy Models

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.2.1 | Create `fastapi-backend/app/models/ai_provider.py` — AiProvider model with `__tablename__`, `__allow_unmapped__ = True` | BE | [ ] | Follow `document.py` pattern |
| 1.2.2 | Define AiProvider UUID PK with `default=uuid.uuid4` | BE | [ ] | |
| 1.2.3 | Define AiProvider columns: name, display_name, provider_type, base_url, api_key_encrypted, is_enabled, scope, user_id | BE | [ ] | |
| 1.2.4 | Define AiProvider DateTime columns with `default=datetime.utcnow` for created_at and updated_at | BE | [ ] | |
| 1.2.5 | Define AiProvider relationship to AiModel (one-to-many) | BE | [ ] | `relationship("AiModel", back_populates="provider")` |
| 1.2.6 | Define AiProvider optional relationship to User (many-to-one, nullable) for user-scoped providers | BE | [ ] | |
| 1.2.7 | Add `TYPE_CHECKING` imports for relationships | BE | [ ] | |
| 1.2.8 | Create `fastapi-backend/app/models/ai_model.py` — AiModel model with `__tablename__`, `__allow_unmapped__ = True` | BE | [ ] | Follow `document.py` pattern |
| 1.2.9 | Define AiModel UUID PK with `default=uuid.uuid4` | BE | [ ] | |
| 1.2.10 | Define AiModel columns: provider_id (FK), model_id, display_name, capability, embedding_dimensions, max_tokens, is_default, is_enabled, created_at, updated_at | BE | [ ] | |
| 1.2.11 | Define AiModel relationship back to AiProvider (many-to-one) | BE | [ ] | `relationship("AiProvider", back_populates="models")` |
| 1.2.12 | Add `__table_args__` for UNIQUE constraint on (provider_id, model_id, capability) | BE | [ ] | |
| 1.2.13 | Register both models in `fastapi-backend/app/models/__init__.py` with imports and `__all__` entries | BE | [ ] | |
| 1.2.14 | CR1: Verify column types match migration exactly | CR1 | [ ] | Acceptance criterion |
| 1.2.15 | CR1: Verify relationships defined correctly (provider.models, model.provider) | CR1 | [ ] | Acceptance criterion |
| 1.2.16 | QE: Verify both models importable from `app.models` | QE | [ ] | Acceptance criterion |
| 1.2.17 | QE: Verify `__allow_unmapped__ = True` set on both models | QE | [ ] | Acceptance criterion |

---

## 1.3 Pydantic Schemas

**File**: `fastapi-backend/app/schemas/ai_config.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.3.1 | Create `AiProviderCreate` schema: name (str, max 100), display_name (str, max 255), provider_type (str, validated: openai/anthropic/ollama), base_url (str or None), api_key (str or None), is_enabled (bool = True) | BE | [ ] | |
| 1.3.2 | Create `UserProviderOverride` schema: provider_type (str, validated), api_key (str, required), base_url (str or None), preferred_model (str or None) | BE | [ ] | |
| 1.3.3 | Create `AiProviderUpdate` schema: all fields optional (partial update) | BE | [ ] | |
| 1.3.4 | Create `AiProviderResponse` schema: all columns EXCEPT api_key_encrypted, add computed `has_api_key: bool`, nested `models: list[AiModelResponse]` | BE | [ ] | |
| 1.3.5 | Create `AiModelCreate` schema: provider_id (UUID), model_id (str, max 255), display_name (str, max 255), capability (str, validated: chat/embedding/vision), embedding_dimensions (int or None), max_tokens (int or None), is_default (bool = False), is_enabled (bool = True) | BE | [ ] | |
| 1.3.6 | Create `AiModelUpdate` schema: all fields optional (partial update) | BE | [ ] | |
| 1.3.7 | Create `AiModelResponse` schema: all columns + `provider_name: str` (joined from provider) | BE | [ ] | |
| 1.3.8 | Create `AiConfigSummary` schema: providers list, default_chat_model, default_embedding_model, default_vision_model | BE | [ ] | |
| 1.3.9 | Add provider_type field validator restricting to "openai", "anthropic", "ollama" on AiProviderCreate and UserProviderOverride | BE | [ ] | |
| 1.3.10 | Add capability field validator restricting to "chat", "embedding", "vision" on AiModelCreate | BE | [ ] | |
| 1.3.11 | SA: Verify `AiProviderResponse` never exposes `api_key_encrypted` or the plain `api_key` | SA | [ ] | Acceptance criterion |
| 1.3.12 | CR1: Verify `AiProviderCreate` accepts plain `api_key` (not `api_key_encrypted`) | CR1 | [ ] | Acceptance criterion |
| 1.3.13 | QE: Verify all schemas validate correctly with sample data | QE | [ ] | Acceptance criterion |
| 1.3.14 | QE: Verify capability field validates against allowed values | QE | [ ] | Acceptance criterion |

---

## 1.4 Encryption Service

**File**: `fastapi-backend/app/ai/encryption.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.4.1 | Create `fastapi-backend/app/ai/` directory with `__init__.py` | BE | [ ] | |
| 1.4.2 | Implement `ApiKeyEncryption.__init__(self, encryption_key: str)` — initialize Fernet with base64-encoded key | BE | [ ] | |
| 1.4.3 | Implement `ApiKeyEncryption.encrypt(self, plaintext: str) -> str` — encrypt API key, return base64 string | BE | [ ] | |
| 1.4.4 | Implement `ApiKeyEncryption.decrypt(self, ciphertext: str) -> str` — decrypt API key, return plaintext | BE | [ ] | |
| 1.4.5 | Implement `ApiKeyEncryption.generate_key() -> str` — static method to generate valid Fernet key | BE | [ ] | |
| 1.4.6 | Implement `ApiKeyEncryption.rotate_all(self, db: AsyncSession, new_key: str) -> int` — re-encrypt all stored keys with new key, return count | BE | [ ] | |
| 1.4.7 | SA: Verify encryption uses Fernet (not custom crypto) | SA | [ ] | |
| 1.4.8 | SA: Verify plaintext keys are never logged or written to disk | SA | [ ] | |
| 1.4.9 | SA: Verify rotate_all atomically re-encrypts within a transaction | SA | [ ] | |
| 1.4.10 | QE: Verify encrypt/decrypt round-trip works correctly | QE | [ ] | Acceptance criterion |
| 1.4.11 | QE: Verify invalid key raises clear error | QE | [ ] | Acceptance criterion |
| 1.4.12 | QE: Verify key rotation re-encrypts all stored keys | QE | [ ] | Acceptance criterion |
| 1.4.13 | QE: Verify generated keys are valid Fernet keys | QE | [ ] | Acceptance criterion |

---

## 1.5 Provider Interface (Abstract Classes)

**File**: `fastapi-backend/app/ai/provider_interface.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.5.1 | Define `LLMProvider` ABC with `@abstractmethod` decorators | BE | [ ] | |
| 1.5.2 | Define `LLMProvider.chat_completion()` signature with multimodal message docs | BE | [ ] | Messages: text-only `"content": str` or multimodal `"content": list[dict]` |
| 1.5.3 | Define `LLMProvider.chat_completion_stream()` signature returning `AsyncIterator[str]` | BE | [ ] | |
| 1.5.4 | Define `LLMProvider.generate_embedding()` signature | BE | [ ] | |
| 1.5.5 | Define `LLMProvider.generate_embeddings_batch()` signature | BE | [ ] | |
| 1.5.6 | Define `VisionProvider` ABC with `describe_image()` method | BE | [ ] | |
| 1.5.7 | Define custom `LLMProviderError` exception class | BE | [ ] | |
| 1.5.8 | CR2: Verify all abstract methods use `async/await` properly | CR2 | [ ] | Acceptance criterion |
| 1.5.9 | DA: Why is embedding always global? What if two teams want different embedding models? | DA | [ ] | Document reasoning: vector space consistency required for search |

---

## 1.6 OpenAI Provider Adapter

**File**: `fastapi-backend/app/ai/openai_provider.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.6.1 | Implement `OpenAIProvider.__init__(self, api_key: str, base_url: str or None)` — create `AsyncOpenAI` client | BE | [ ] | |
| 1.6.2 | Implement `OpenAIProvider.chat_completion()` — uses `client.chat.completions.create(stream=False)` | BE | [ ] | |
| 1.6.3 | Implement multimodal message conversion in chat_completion: normalized `{"type": "image", "data": ..., "media_type": ...}` to OpenAI `{"type": "image_url", "image_url": {"url": "data:{media_type};base64,{data}"}}` | BE | [ ] | |
| 1.6.4 | Implement `OpenAIProvider.chat_completion_stream()` — uses `client.chat.completions.create(stream=True)`, yields `delta.content` | BE | [ ] | |
| 1.6.5 | Implement multimodal support in chat_completion_stream (same conversion as non-streaming) | BE | [ ] | |
| 1.6.6 | Implement `OpenAIProvider.generate_embedding()` — uses `client.embeddings.create()`, supports `dimensions` parameter | BE | [ ] | |
| 1.6.7 | Implement `OpenAIProvider.generate_embeddings_batch()` — list input, returns list of vectors | BE | [ ] | |
| 1.6.8 | Implement `OpenAIProvider.describe_image()` — sends base64 image in content array with `image_url` type | BE | [ ] | VisionProvider implementation |
| 1.6.9 | Implement error handling: wrap `openai.APIError` into `LLMProviderError` | BE | [ ] | |
| 1.6.10 | Verify class implements both `LLMProvider` and `VisionProvider` interfaces | CR1 | [ ] | Acceptance criterion |

---

## 1.7 Anthropic Provider Adapter

**File**: `fastapi-backend/app/ai/anthropic_provider.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.7.1 | Implement `AnthropicProvider.__init__(self, api_key: str)` — create `AsyncAnthropic` client | BE | [ ] | |
| 1.7.2 | Implement `AnthropicProvider.chat_completion()` — uses `client.messages.create(stream=False)` | BE | [ ] | |
| 1.7.3 | Implement multimodal message conversion: normalized `{"type": "image", ...}` to Anthropic `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}` | BE | [ ] | |
| 1.7.4 | Implement `AnthropicProvider.chat_completion_stream()` — uses `client.messages.stream()`, yields text deltas | BE | [ ] | |
| 1.7.5 | Implement multimodal support in chat_completion_stream | BE | [ ] | |
| 1.7.6 | Implement `AnthropicProvider.generate_embedding()` — raise `NotImplementedError` with message to use OpenAI or Ollama | BE | [ ] | |
| 1.7.7 | Implement `AnthropicProvider.generate_embeddings_batch()` — raise `NotImplementedError` | BE | [ ] | |
| 1.7.8 | Implement `AnthropicProvider.describe_image()` — uses base64 `image` content block | BE | [ ] | VisionProvider implementation |
| 1.7.9 | Implement error handling: wrap `anthropic.APIError` into `LLMProviderError` | BE | [ ] | |
| 1.7.10 | Verify class implements both `LLMProvider` and `VisionProvider` interfaces | CR1 | [ ] | Acceptance criterion |

---

## 1.8 Ollama Provider Adapter

**File**: `fastapi-backend/app/ai/ollama_provider.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.8.1 | Implement `OllamaProvider.__init__(self, base_url: str)` — default `http://localhost:11434`, create `httpx.AsyncClient` | BE | [ ] | |
| 1.8.2 | Implement `OllamaProvider.chat_completion()` — `POST {base_url}/api/chat` with `stream=false` | BE | [ ] | |
| 1.8.3 | Implement `OllamaProvider.chat_completion_stream()` — `POST {base_url}/api/chat` with `stream=true`, read NDJSON lines | BE | [ ] | |
| 1.8.4 | Implement `OllamaProvider.generate_embedding()` — `POST {base_url}/api/embeddings` | BE | [ ] | |
| 1.8.5 | Implement `OllamaProvider.generate_embeddings_batch()` — loop over `generate_embedding` (Ollama has no native batch) | BE | [ ] | |
| 1.8.6 | Implement `OllamaProvider.describe_image()` — `POST {base_url}/api/chat` with base64 images array (llava, bakllava) | BE | [ ] | VisionProvider only if model supports it |
| 1.8.7 | Implement error handling: wrap `httpx.HTTPError` into `LLMProviderError` | BE | [ ] | |
| 1.8.8 | CR2: Verify httpx client is properly closed/disposed (no resource leaks) | CR2 | [ ] | |
| 1.8.9 | DA: What happens when Ollama is offline? Verify timeout and retry behavior are defined | DA | [ ] | |

---

## 1.9 Embedding Normalizer

**File**: `fastapi-backend/app/ai/embedding_normalizer.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.9.1 | Implement `EmbeddingNormalizer.__init__(self, target_dimensions: int = 1536)` | BE | [ ] | |
| 1.9.2 | Implement `EmbeddingNormalizer.normalize()` — zero-pad short vectors to target dimension | BE | [ ] | |
| 1.9.3 | Implement `EmbeddingNormalizer.normalize()` — truncate long vectors to target dimension | BE | [ ] | |
| 1.9.4 | Implement L2-normalization after dimension adjustment | BE | [ ] | |
| 1.9.5 | Handle edge case: zero vector (all zeros) — avoid division by zero in L2 norm | BE | [ ] | |
| 1.9.6 | QE: Verify normalizer handles dimension mismatches correctly | QE | [ ] | Acceptance criterion |
| 1.9.7 | CR2: Verify numerical stability of L2 normalization (epsilon for near-zero norms) | CR2 | [ ] | |

---

## 1.10 Provider Registry

**File**: `fastapi-backend/app/ai/provider_registry.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.10.1 | Implement `ProviderRegistry` as singleton (thread-safe) | BE | [ ] | |
| 1.10.2 | Implement `get_chat_provider(self, user_id: UUID or None) -> tuple[LLMProvider, str]` — resolution: user-specific > global > ConfigurationError | BE | [ ] | |
| 1.10.3 | Implement `get_embedding_provider(self) -> tuple[LLMProvider, str]` — always uses global provider (not user-overridable) | BE | [ ] | |
| 1.10.4 | Implement `get_vision_provider(self, user_id: UUID or None) -> tuple[VisionProvider, str]` — same user > global resolution | BE | [ ] | |
| 1.10.5 | Implement `refresh(self) -> None` — clear cached instances when config changes | BE | [ ] | |
| 1.10.6 | Implement instance caching — don't recreate adapters on every call | BE | [ ] | |
| 1.10.7 | Implement DB config loading — query AiProviders + AiModels to build adapters | BE | [ ] | |
| 1.10.8 | Implement decryption of api_key_encrypted when creating adapter instances | BE | [ ] | |
| 1.10.9 | QE: Verify ProviderRegistry resolves user-specific > global > error | QE | [ ] | Acceptance criterion |
| 1.10.10 | QE: Verify ProviderRegistry caches instances (doesn't recreate on every call) | QE | [ ] | Acceptance criterion |
| 1.10.11 | CR1: Verify cache invalidation strategy — refresh() called on config CRUD | CR1 | [ ] | |
| 1.10.12 | DA: What if global provider is disabled but user has no override? Should it raise or silently skip? | DA | [ ] | |

---

## 1.11 Admin Router — Provider Endpoints

**File**: `fastapi-backend/app/routers/ai_config.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.11.1 | Implement `GET /api/ai/config/providers` — list all global providers | BE | [ ] | Auth: Application Owner |
| 1.11.2 | Implement `POST /api/ai/config/providers` — create global provider (encrypts api_key, sets scope='global', user_id=NULL) | BE | [ ] | Auth: Application Owner |
| 1.11.3 | Implement `PUT /api/ai/config/providers/{id}` — update global provider (re-encrypt if api_key provided, preserve if absent) | BE | [ ] | Auth: Application Owner |
| 1.11.4 | Implement `DELETE /api/ai/config/providers/{id}` — delete global provider (cascades to models) | BE | [ ] | Auth: Application Owner |
| 1.11.5 | Implement `POST /api/ai/config/providers/{id}/test` — test connectivity for global provider | BE | [ ] | Auth: Application Owner |
| 1.11.6 | Implement test logic: OpenAI calls `client.models.list()` | BE | [ ] | |
| 1.11.7 | Implement test logic: Anthropic calls `client.messages.create()` with minimal content | BE | [ ] | |
| 1.11.8 | Implement test logic: Ollama calls `GET {base_url}/api/tags` | BE | [ ] | |
| 1.11.9 | Implement admin auth dependency: require user is owner of at least one application via `PermissionService.get_user_application_role()` | BE | [ ] | |
| 1.11.10 | SA: Verify admin endpoints return 403 for non-owners | SA | [ ] | |
| 1.11.11 | SA: Verify POST /providers encrypts api_key before DB write | SA | [ ] | |
| 1.11.12 | SA: Verify PUT /providers/{id} re-encrypts new key, preserves old if key not sent | SA | [ ] | |
| 1.11.13 | SA: Verify GET /providers never returns api_key_encrypted in response body | SA | [ ] | |

---

## 1.12 Admin Router — Model Endpoints

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.12.1 | Implement `GET /api/ai/config/models` — list all models | BE | [ ] | Auth: Application Owner |
| 1.12.2 | Implement `POST /api/ai/config/models` — register model | BE | [ ] | Auth: Application Owner |
| 1.12.3 | Implement `PUT /api/ai/config/models/{id}` — update model | BE | [ ] | Auth: Application Owner |
| 1.12.4 | Implement `DELETE /api/ai/config/models/{id}` — delete model | BE | [ ] | Auth: Application Owner |
| 1.12.5 | Implement `GET /api/ai/config/summary` — full config summary (providers + defaults per capability) | BE | [ ] | Auth: Application Owner |
| 1.12.6 | CR1: Verify model UNIQUE constraint (provider_id, model_id, capability) is enforced and returns proper error | CR1 | [ ] | |
| 1.12.7 | SA: Verify model endpoints return 403 for non-owners | SA | [ ] | |

---

## 1.13 User Override Endpoints

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.13.1 | Implement `GET /api/ai/config/me/providers` — list current user's personal overrides | BE | [ ] | Auth: any authenticated user |
| 1.13.2 | Implement `POST /api/ai/config/me/providers` — set personal API key override (encrypts key, scope='user', user_id=current_user.id) | BE | [ ] | 409 if duplicate |
| 1.13.3 | Implement `PUT /api/ai/config/me/providers/{provider_type}` — update personal key / model preference | BE | [ ] | |
| 1.13.4 | Implement `DELETE /api/ai/config/me/providers/{provider_type}` — remove override, revert to global | BE | [ ] | |
| 1.13.5 | Implement `POST /api/ai/config/me/providers/{provider_type}/test` — test user's personal key | BE | [ ] | |
| 1.13.6 | Implement `GET /api/ai/config/me/summary` — effective config for current user (resolved: user override > global) | BE | [ ] | |
| 1.13.7 | Implement user summary logic: for each provider type, show user override as "active" or global as "active" / "fallback" | BE | [ ] | |
| 1.13.8 | Implement 409 Conflict response on duplicate user override for same provider_type | BE | [ ] | |
| 1.13.9 | SA: Verify user queries always filter by `current_user.id` — user A cannot see user B's overrides | SA | [ ] | |
| 1.13.10 | SA: Verify user override creation encrypts API key before storage | SA | [ ] | |
| 1.13.11 | SA: Verify user endpoints accessible by any authenticated user (not just owners) | SA | [ ] | |
| 1.13.12 | CR2: Verify DELETE override correctly reverts provider resolution to global | CR2 | [ ] | |
| 1.13.13 | DA: What if user sets an override for a provider type that has no global config? Should it still work? | DA | [ ] | User key is self-sufficient |

---

## 1.14 Configuration & Dependencies

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.14.1 | Add to `fastapi-backend/app/config.py`: `ai_encryption_key: str = ""` | BE | [ ] | Loads from `AI_ENCRYPTION_KEY` env var |
| 1.14.2 | Add to `fastapi-backend/app/config.py`: `ai_default_embedding_dimensions: int = 1536` | BE | [ ] | |
| 1.14.3 | Add to `fastapi-backend/app/config.py`: `ai_default_provider: str = "openai"` | BE | [ ] | |
| 1.14.4 | Add `openai>=1.30.0` to `fastapi-backend/requirements.txt` | BE | [ ] | |
| 1.14.5 | Add `anthropic>=0.40.0` to `fastapi-backend/requirements.txt` | BE | [ ] | |
| 1.14.6 | Add `cryptography>=42.0.0` to `fastapi-backend/requirements.txt` | BE | [ ] | |
| 1.14.7 | Update `fastapi-backend/.env.example` with `AI_ENCRYPTION_KEY=` placeholder | BE | [ ] | |
| 1.14.8 | Mount router in `fastapi-backend/app/main.py`: `app.include_router(ai_config.router)` | BE | [ ] | |
| 1.14.9 | QE: Verify settings load from environment variables (`AI_ENCRYPTION_KEY`, etc.) | QE | [ ] | Acceptance criterion |
| 1.14.10 | QE: Verify default values are sensible for development | QE | [ ] | Acceptance criterion |
| 1.14.11 | QE: Verify empty `ai_encryption_key` doesn't crash app on startup | QE | [ ] | Acceptance criterion |
| 1.14.12 | QE: Verify `pip install -r requirements.txt` succeeds with no version conflicts | QE | [ ] | Acceptance criterion |

---

## 1.15 Code Reviews & Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.15.1 | CR1: Full review of migration file — column types, constraints, cascades, reversibility | CR1 | [ ] | |
| 1.15.2 | CR1: Full review of SQLAlchemy models — relationships, __table_args__, column definitions | CR1 | [ ] | |
| 1.15.3 | CR1: Full review of Pydantic schemas — field validators, response exclusions, model_config | CR1 | [ ] | |
| 1.15.4 | CR2: Full review of provider adapters — error handling, async patterns, resource management | CR2 | [ ] | |
| 1.15.5 | CR2: Full review of provider registry — singleton pattern, cache thread-safety, resolution logic | CR2 | [ ] | |
| 1.15.6 | CR2: Full review of router — endpoint signatures, dependencies, response models, status codes | CR2 | [ ] | |
| 1.15.7 | SA: Verify api_key_encrypted column never appears in any Pydantic response schema | SA | [ ] | |
| 1.15.8 | SA: Verify all API key encryption/decryption paths — no plaintext in logs, responses, or error messages | SA | [ ] | |
| 1.15.9 | SA: Verify admin auth — all admin endpoints require Application Owner role | SA | [ ] | |
| 1.15.10 | SA: Verify user isolation — user override queries always scoped to current_user.id | SA | [ ] | |
| 1.15.11 | SA: Verify Fernet key is not hardcoded and loads exclusively from environment | SA | [ ] | |
| 1.15.12 | DA: What happens if AI_ENCRYPTION_KEY is rotated but rotate_all() is not called? Document the procedure | DA | [ ] | |
| 1.15.13 | DA: Why three separate provider adapters instead of a unified HTTP adapter with config? Justify architecture | DA | [ ] | SDKs provide better typing, streaming, error handling |

---

## 1.16 Unit Tests — Provider Adapters

**File**: `fastapi-backend/tests/test_ai_providers.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.16.1 | Write `test_openai_chat_completion_returns_string` — mock AsyncOpenAI, verify string response | TE | [ ] | |
| 1.16.2 | Write `test_openai_chat_completion_stream_yields_chunks` — mock streaming, verify async iterator yields strings | TE | [ ] | |
| 1.16.3 | Write `test_openai_generate_embedding_returns_vector` — mock embeddings.create, verify list[float] | TE | [ ] | |
| 1.16.4 | Write `test_openai_generate_embeddings_batch_returns_list` — mock batch, verify list[list[float]] | TE | [ ] | |
| 1.16.5 | Write `test_openai_describe_image_returns_description` — mock vision call, verify string | TE | [ ] | |
| 1.16.6 | Write `test_openai_chat_with_image_content_block` — verify multimodal message conversion to OpenAI format | TE | [ ] | |
| 1.16.7 | Write `test_anthropic_chat_completion_returns_string` — mock AsyncAnthropic, verify string response | TE | [ ] | |
| 1.16.8 | Write `test_anthropic_chat_completion_stream_yields_chunks` — mock streaming, verify yields | TE | [ ] | |
| 1.16.9 | Write `test_anthropic_embedding_raises_not_implemented` — verify NotImplementedError with helpful message | TE | [ ] | |
| 1.16.10 | Write `test_anthropic_describe_image_returns_description` — mock vision call | TE | [ ] | |
| 1.16.11 | Write `test_anthropic_chat_with_image_content_block` — verify multimodal message conversion to Anthropic format | TE | [ ] | |
| 1.16.12 | Write `test_ollama_chat_completion_returns_string` — mock httpx, verify string response | TE | [ ] | |
| 1.16.13 | Write `test_ollama_chat_completion_stream_yields_chunks` — mock NDJSON streaming | TE | [ ] | |
| 1.16.14 | Write `test_ollama_generate_embedding_returns_vector` — mock embeddings endpoint | TE | [ ] | |

---

## 1.17 Unit Tests — Encryption & Registry

**File**: `fastapi-backend/tests/test_ai_providers.py` (continued)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.17.1 | Write `test_encryption_roundtrip` — encrypt then decrypt returns original | TE | [ ] | |
| 1.17.2 | Write `test_encryption_invalid_key_raises` — bad key raises clear error | TE | [ ] | |
| 1.17.3 | Write `test_encryption_generate_key_valid` — generated key is usable by Fernet | TE | [ ] | |
| 1.17.4 | Write `test_provider_registry_resolves_user_override_first` — user provider returned when both exist | TE | [ ] | |
| 1.17.5 | Write `test_provider_registry_falls_back_to_global` — global returned when no user override | TE | [ ] | |
| 1.17.6 | Write `test_provider_registry_raises_on_no_config` — ConfigurationError when nothing configured | TE | [ ] | |
| 1.17.7 | Write `test_provider_registry_embedding_always_global` — embedding never uses user override | TE | [ ] | |
| 1.17.8 | Write `test_provider_registry_vision_user_override` — vision respects user > global resolution | TE | [ ] | |
| 1.17.9 | Write `test_embedding_normalizer_pads_short_vectors` — short vector zero-padded to target | TE | [ ] | |
| 1.17.10 | Write `test_embedding_normalizer_truncates_long_vectors` — long vector truncated to target | TE | [ ] | |
| 1.17.11 | Write `test_embedding_normalizer_l2_normalizes` — output vector has L2 norm of 1.0 | TE | [ ] | |

---

## 1.18 Integration Tests — Admin Router

**File**: `fastapi-backend/tests/test_ai_config_router.py`

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.18.1 | Write `test_list_providers_empty` — returns empty list when no providers configured | TE | [ ] | |
| 1.18.2 | Write `test_create_provider_openai` — creates OpenAI provider, returns AiProviderResponse | TE | [ ] | |
| 1.18.3 | Write `test_create_provider_ollama_no_key` — Ollama created with NULL api_key_encrypted | TE | [ ] | |
| 1.18.4 | Write `test_create_provider_validates_type` — rejects invalid provider_type with 422 | TE | [ ] | |
| 1.18.5 | Write `test_create_provider_encrypts_key` — verify DB column is encrypted (not plaintext) | TE | [ ] | |
| 1.18.6 | Write `test_get_provider_does_not_expose_key` — response has `has_api_key: true` but no key field | TE | [ ] | |
| 1.18.7 | Write `test_update_provider_preserves_key_if_not_sent` — PUT without api_key keeps existing encrypted key | TE | [ ] | |
| 1.18.8 | Write `test_update_provider_re_encrypts_new_key` — PUT with new api_key updates encrypted value | TE | [ ] | |
| 1.18.9 | Write `test_delete_provider_cascades_models` — deleting provider removes its models | TE | [ ] | |
| 1.18.10 | Write `test_test_provider_connectivity_success` — mock successful connectivity check | TE | [ ] | |
| 1.18.11 | Write `test_test_provider_connectivity_failure` — mock failed connectivity, returns error details | TE | [ ] | |
| 1.18.12 | Write `test_create_model` — register model on a provider | TE | [ ] | |
| 1.18.13 | Write `test_create_model_unique_constraint` — duplicate (provider_id, model_id, capability) returns error | TE | [ ] | |
| 1.18.14 | Write `test_update_model` — partial update of model fields | TE | [ ] | |
| 1.18.15 | Write `test_delete_model` — remove model by ID | TE | [ ] | |
| 1.18.16 | Write `test_config_summary` — returns providers list + default per capability | TE | [ ] | |
| 1.18.17 | Write `test_non_owner_gets_403` — non-owner user receives 403 on admin endpoints | TE | [ ] | |

---

## 1.19 Integration Tests — User Override Router

**File**: `fastapi-backend/tests/test_ai_config_router.py` (continued)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.19.1 | Write `test_user_create_override_openai` — user sets personal OpenAI key | TE | [ ] | |
| 1.19.2 | Write `test_user_create_override_encrypts_key` — verify personal key is encrypted in DB | TE | [ ] | |
| 1.19.3 | Write `test_user_create_override_duplicate_409` — second override for same provider_type returns 409 | TE | [ ] | |
| 1.19.4 | Write `test_user_list_own_overrides` — user sees only their own overrides | TE | [ ] | |
| 1.19.5 | Write `test_user_update_override_model_preference` — update preferred_model on existing override | TE | [ ] | |
| 1.19.6 | Write `test_user_delete_override_reverts_to_global` — after delete, summary shows global as active | TE | [ ] | |
| 1.19.7 | Write `test_user_test_own_key_connectivity` — mock connectivity test for user's personal key | TE | [ ] | |
| 1.19.8 | Write `test_user_summary_with_override` — user with override sees it as "active", global as "fallback" | TE | [ ] | |
| 1.19.9 | Write `test_user_summary_without_override_shows_global` — user without override sees global as "active" | TE | [ ] | |
| 1.19.10 | Write `test_user_cannot_see_other_users_overrides` — user A queries, user B's overrides not returned | TE | [ ] | |
| 1.19.11 | Write `test_user_override_does_not_affect_global` — user override doesn't modify global provider | TE | [ ] | |
| 1.19.12 | Write `test_any_authenticated_user_can_set_override` — non-owner user can still set personal key | TE | [ ] | |

---

## 1.20 Phase 1 Verification & Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 1.20.1 | Run `alembic upgrade head` — verify migration applies cleanly | QE | [ ] | |
| 1.20.2 | Run `alembic downgrade -1` then `alembic upgrade head` — verify reversibility | QE | [ ] | |
| 1.20.3 | Run `pytest tests/test_ai_providers.py -v` — all provider unit tests pass | QE | [ ] | |
| 1.20.4 | Run `pytest tests/test_ai_config_router.py -v` — all router integration tests pass | QE | [ ] | |
| 1.20.5 | Run `ruff check fastapi-backend/app/ai/ fastapi-backend/app/routers/ai_config.py fastapi-backend/app/schemas/ai_config.py` — no lint errors | QE | [ ] | |
| 1.20.6 | Manual test: POST global OpenAI provider with api_key, GET provider — verify has_api_key=true, no key in response | QE | [ ] | |
| 1.20.7 | Manual test: POST /providers/{id}/test — verify connectivity check succeeds with valid key | QE | [ ] | |
| 1.20.8 | Manual test: POST user override, GET /me/summary — verify user override shows as active | QE | [ ] | |
| 1.20.9 | Manual test: DELETE user override, GET /me/summary — verify fallback to global | QE | [ ] | |
| 1.20.10 | Manual test: Verify DB column contains encrypted (not plaintext) api_key via psql | QE | [ ] | |
| 1.20.11 | CR1 sign-off: Database layer (migration, models, schemas) approved | CR1 | [ ] | |
| 1.20.12 | CR2 sign-off: AI layer (providers, registry, encryption) approved | CR2 | [ ] | |
| 1.20.13 | SA sign-off: Security review passed (encryption, auth, data isolation, no key leakage) | SA | [ ] | |
| 1.20.14 | DA sign-off: Architecture concerns documented and resolved | DA | [ ] | |
| 1.20.15 | QE sign-off: All acceptance criteria verified, all tests passing | QE | [ ] | |

---

## Task Count Summary

| Section | Tasks |
|---------|-------|
| 1.1 Database — Migration | 16 |
| 1.2 Database — SQLAlchemy Models | 17 |
| 1.3 Pydantic Schemas | 14 |
| 1.4 Encryption Service | 13 |
| 1.5 Provider Interface (Abstract Classes) | 9 |
| 1.6 OpenAI Provider Adapter | 10 |
| 1.7 Anthropic Provider Adapter | 10 |
| 1.8 Ollama Provider Adapter | 9 |
| 1.9 Embedding Normalizer | 7 |
| 1.10 Provider Registry | 12 |
| 1.11 Admin Router — Provider Endpoints | 13 |
| 1.12 Admin Router — Model Endpoints | 7 |
| 1.13 User Override Endpoints | 13 |
| 1.14 Configuration & Dependencies | 12 |
| 1.15 Code Reviews & Security Analysis | 13 |
| 1.16 Unit Tests — Provider Adapters | 14 |
| 1.17 Unit Tests — Encryption & Registry | 11 |
| 1.18 Integration Tests — Admin Router | 17 |
| 1.19 Integration Tests — User Override Router | 12 |
| 1.20 Phase 1 Verification & Sign-Off | 15 |
| **Total** | **244** |
