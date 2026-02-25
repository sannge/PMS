# Phase 1: LLM Abstraction Layer + Database Setup

**Goal**: Provider-agnostic LLM infrastructure with encrypted API key storage. No user-facing AI yet.

**Depends on**: Nothing (foundation phase)
**Blocks**: Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7

---

## Task 1.1: Alembic Migration — AI Configuration Tables

**File**: `fastapi-backend/alembic/versions/YYYYMMDD_add_ai_configuration.py`

Create two tables following existing migration patterns (see `20260131_drop_notes_create_documents.py`).

### `AiProviders` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | `default=uuid4` |
| name | VARCHAR(100) | "openai", "anthropic", "ollama" |
| display_name | VARCHAR(255) | "OpenAI", "Anthropic", "Ollama (Local)" |
| provider_type | VARCHAR(50) | "openai", "anthropic", "ollama" |
| base_url | TEXT NULL | Required for Ollama, optional override for others |
| api_key_encrypted | TEXT NULL | Fernet-encrypted. NULL for Ollama. |
| is_enabled | BOOLEAN DEFAULT true | |
| scope | VARCHAR(20) DEFAULT 'global' | "global" or "user" |
| user_id | UUID FK NULL | Set when scope='user' — references Users.id |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Scope design**:
- `scope='global'`: Admin-configured provider used by all users. `user_id` is NULL.
- `scope='user'`: User's personal API key override. `user_id` is set.

**Uniqueness**: `UNIQUE(provider_type, scope, user_id)` — each user can have at most one override per provider type. Global providers are unique by provider_type where user_id IS NULL.

**Resolution order** (when making LLM calls):
1. User-specific provider (scope='user', user_id=current_user) — if user set their own key
2. Global provider (scope='global') — admin-configured default
3. Raise ConfigurationError — no provider available

### `AiModels` Table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| provider_id | UUID FK -> AiProviders.id CASCADE | |
| model_id | VARCHAR(255) | "gpt-4o", "claude-sonnet-4-20250514", etc. |
| display_name | VARCHAR(255) | |
| capability | VARCHAR(50) | "chat", "embedding", "vision" |
| embedding_dimensions | INT NULL | 1536, 3072, etc. |
| max_tokens | INT NULL | |
| is_default | BOOLEAN DEFAULT false | Per-capability default |
| is_enabled | BOOLEAN DEFAULT true | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

**Constraints**:
- UNIQUE constraint: `(provider_id, model_id, capability)`

### Acceptance Criteria
- [ ] Migration runs successfully with `alembic upgrade head`
- [ ] Migration is reversible with `alembic downgrade -1`
- [ ] Both tables are created with correct column types and constraints
- [ ] FK from AiProviders.user_id to Users.id exists
- [ ] FK from AiModels.provider_id to AiProviders.id with CASCADE delete
- [ ] UNIQUE constraint on `(provider_type, scope, user_id)` prevents duplicate overrides

---

## Task 1.2: SQLAlchemy Models

### New File: `fastapi-backend/app/models/ai_provider.py`

SQLAlchemy model for the `AiProviders` table.

Follow exact patterns from `fastapi-backend/app/models/document.py`:
- `__tablename__`, `__allow_unmapped__ = True`
- UUID PK with `default=uuid.uuid4`
- `DateTime` columns with `default=datetime.utcnow`
- `TYPE_CHECKING` imports for relationships
- Relationship to `AiModel` (one-to-many)
- Optional relationship to `User` (many-to-one, nullable, for user-scoped providers)

### New File: `fastapi-backend/app/models/ai_model.py`

SQLAlchemy model for the `AiModels` table.

Follow exact patterns from `fastapi-backend/app/models/document.py`:
- Relationship back to `AiProvider` (many-to-one)
- `__table_args__` for the UNIQUE constraint on `(provider_id, model_id, capability)`

### Modify: `fastapi-backend/app/models/__init__.py`

Register both new models:
```python
from app.models.ai_provider import AiProvider
from app.models.ai_model import AiModel
```

### Acceptance Criteria
- [ ] Both models importable from `app.models`
- [ ] Relationships defined correctly (provider.models, model.provider)
- [ ] Column types match migration exactly
- [ ] `__allow_unmapped__ = True` set on both

---

## Task 1.3: Pydantic Schemas

### New File: `fastapi-backend/app/schemas/ai_config.py`

Follow patterns from `fastapi-backend/app/schemas/document.py`.

### Schemas to Create

**`AiProviderCreate`** (admin — global providers):
- `name: str` (required, max 100)
- `display_name: str` (required, max 255)
- `provider_type: str` (required, one of: "openai", "anthropic", "ollama")
- `base_url: str | None = None`
- `api_key: str | None = None` (plain text — encrypted before storage)
- `is_enabled: bool = True`

**`UserProviderOverride`** (per-user — personal API key):
- `provider_type: str` (required, one of: "openai", "anthropic", "ollama")
- `api_key: str` (required — user must provide their own key)
- `base_url: str | None = None` (optional, e.g., custom Ollama URL)
- `preferred_model: str | None = None` (optional model override, e.g., "claude-sonnet-4-20250514")

**`AiProviderUpdate`**:
- All fields optional (partial update)

**`AiProviderResponse`**:
- All columns from table EXCEPT `api_key_encrypted`
- `has_api_key: bool` (computed: `api_key_encrypted is not None`)
- `models: list[AiModelResponse]` (nested, optional)

**`AiModelCreate`**:
- `provider_id: UUID` (required)
- `model_id: str` (required, max 255)
- `display_name: str` (required, max 255)
- `capability: str` (required, one of: "chat", "embedding", "vision")
- `embedding_dimensions: int | None = None`
- `max_tokens: int | None = None`
- `is_default: bool = False`
- `is_enabled: bool = True`

**`AiModelUpdate`**:
- All fields optional (partial update)

**`AiModelResponse`**:
- All columns from table
- `provider_name: str` (joined from provider)

**`AiConfigSummary`**:
- `providers: list[AiProviderResponse]`
- `default_chat_model: AiModelResponse | None`
- `default_embedding_model: AiModelResponse | None`
- `default_vision_model: AiModelResponse | None`

### Acceptance Criteria
- [ ] All schemas validate correctly with sample data
- [ ] `AiProviderResponse` never exposes `api_key_encrypted` or the plain key
- [ ] `AiProviderCreate` accepts plain `api_key` (not `api_key_encrypted`)
- [ ] Capability field validates against allowed values

---

## Task 1.4: LLM Provider Abstraction Layer

### New Directory: `fastapi-backend/app/ai/`

### New File: `fastapi-backend/app/ai/__init__.py`

Empty init file.

### New File: `fastapi-backend/app/ai/provider_interface.py`

Abstract base classes defining the contract:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class LLMProvider(ABC):
    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs
    ) -> str:
        """
        Single-shot chat completion. Returns response text.

        Messages can contain multimodal content (text + images).
        Each message dict has a "role" key and either:
        - "content": str  (text-only)
        - "content": list[dict]  (multimodal — mixed text and image blocks)

        Image content blocks use a normalized format:
        {"type": "image", "data": "<base64>", "media_type": "image/png"}

        Each provider adapter converts this normalized format to the
        provider-specific API format (OpenAI image_url, Anthropic image
        source, Ollama images array).
        """

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Streaming chat completion. Yields text chunks.
        Supports same multimodal message format as chat_completion."""

    @abstractmethod
    async def generate_embedding(
        self,
        text: str,
        model: str
    ) -> list[float]:
        """Generate embedding vector for a single text."""

    @abstractmethod
    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str
    ) -> list[list[float]]:
        """Generate embedding vectors for multiple texts."""


class VisionProvider(ABC):
    @abstractmethod
    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        model: str
    ) -> str:
        """
        Analyze an image and return a text description.
        Used for background image processing (document import, attachment indexing).
        For interactive chat with images, use LLMProvider.chat_completion()
        with multimodal content blocks instead.
        """
```

### New File: `fastapi-backend/app/ai/openai_provider.py`

Uses `openai` SDK. Implements both `LLMProvider` and `VisionProvider` (GPT-4o has vision).

Key implementation details:
- Constructor takes `api_key: str`, `base_url: str | None`
- Creates `AsyncOpenAI` client
- `chat_completion`: Uses `client.chat.completions.create(stream=False)`
  - Handles multimodal messages: converts normalized `{"type": "image", "data": ..., "media_type": ...}` blocks to OpenAI's `{"type": "image_url", "image_url": {"url": "data:{media_type};base64,{data}"}}` format
- `chat_completion_stream`: Uses `client.chat.completions.create(stream=True)`, yields `delta.content`
  - Same multimodal support as non-streaming
- `generate_embedding`: Uses `client.embeddings.create()`, supports `dimensions` parameter for truncation
- `generate_embeddings_batch`: Same but with list input, returns list of vectors
- `describe_image`: Sends base64 image in content array with `image_url` type (for background processing)
- Error handling: Wraps `openai.APIError` into custom `LLMProviderError`

### New File: `fastapi-backend/app/ai/anthropic_provider.py`

Uses `anthropic` SDK. Implements both `LLMProvider` and `VisionProvider`.

Key implementation details:
- Constructor takes `api_key: str`
- Creates `AsyncAnthropic` client
- `chat_completion`: Uses `client.messages.create(stream=False)`
  - Handles multimodal messages: converts normalized `{"type": "image", ...}` blocks to Anthropic's `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}` format
- `chat_completion_stream`: Uses `client.messages.stream()`, yields text deltas
  - Same multimodal support as non-streaming
- `generate_embedding`: Anthropic doesn't have embeddings — raise `NotImplementedError` with message to use OpenAI or Ollama for embeddings
- `generate_embeddings_batch`: Same as above
- `describe_image`: Uses base64 `image` content block in messages (for background processing)
- Error handling: Wraps `anthropic.APIError` into `LLMProviderError`

### New File: `fastapi-backend/app/ai/ollama_provider.py`

Uses `httpx` against configurable Ollama URL. Implements `LLMProvider`. `VisionProvider` only if model supports it (llava, etc.).

Key implementation details:
- Constructor takes `base_url: str` (defaults to `http://localhost:11434`)
- Uses `httpx.AsyncClient` for all requests
- `chat_completion`: `POST {base_url}/api/chat` with `stream=false`
- `chat_completion_stream`: `POST {base_url}/api/chat` with `stream=true`, reads NDJSON lines
- `generate_embedding`: `POST {base_url}/api/embeddings`
- `generate_embeddings_batch`: Loop over `generate_embedding` (Ollama doesn't support batch natively)
- `describe_image`: `POST {base_url}/api/chat` with base64 images array (works with llava, bakllava, etc.)
- Error handling: Wraps `httpx.HTTPError` into `LLMProviderError`

### New File: `fastapi-backend/app/ai/provider_registry.py`

Factory that loads config from DB, creates/caches adapter instances:

```python
class ProviderRegistry:
    """
    Singleton registry that loads provider configs from DB
    and caches adapter instances. Thread-safe.
    """

    async def get_chat_provider(
        self,
        user_id: UUID | None = None
    ) -> tuple[LLMProvider, str]:
        """
        Returns (provider_instance, default_model_id).
        Resolution order:
          1. User-specific provider (if user has set their own API key)
          2. Global default provider
          3. Raise ConfigurationError
        """

    async def get_embedding_provider(self) -> tuple[LLMProvider, str]:
        """
        Embedding always uses global provider (not user-overridable).
        Embeddings must be consistent across all users for vector search
        to work (same model = same vector space).
        """

    async def get_vision_provider(
        self,
        user_id: UUID | None = None
    ) -> tuple[VisionProvider, str]:
        """
        Same user > global resolution for vision capability.
        User's key is used if available, otherwise global.
        """

    async def refresh(self) -> None:
        """Clear cached instances. Called when config changes."""
```

### New File: `fastapi-backend/app/ai/embedding_normalizer.py`

Handles dimension differences across providers:

```python
class EmbeddingNormalizer:
    """
    Normalizes embedding vectors to a target dimension.

    - OpenAI: Use the `dimensions` parameter for native truncation
    - Ollama: Zero-pad if shorter, truncate if longer than target
    - Always L2-normalize after adjustment
    """

    def __init__(self, target_dimensions: int = 1536):
        self.target_dimensions = target_dimensions

    def normalize(self, embedding: list[float]) -> list[float]:
        """Adjust to target dimensions and L2-normalize."""
```

### Acceptance Criteria
- [ ] All three providers implement the `LLMProvider` interface
- [ ] OpenAI and Anthropic implement `VisionProvider`
- [ ] `ProviderRegistry` resolves app-specific > global > error
- [ ] `ProviderRegistry` caches instances (doesn't recreate on every call)
- [ ] `EmbeddingNormalizer` handles dimension mismatches correctly
- [ ] Custom `LLMProviderError` exception class defined
- [ ] All async methods use `async/await` properly

---

## Task 1.5: API Key Encryption

### New File: `fastapi-backend/app/ai/encryption.py`

```python
from cryptography.fernet import Fernet, MultiFernet

class ApiKeyEncryption:
    """
    Fernet-based encryption for LLM provider API keys.

    Uses AI_ENCRYPTION_KEY from settings.
    Supports key rotation: when key changes, call rotate_all()
    to re-encrypt all stored keys with the new key.
    """

    def __init__(self, encryption_key: str):
        """Initialize with base64-encoded Fernet key."""
        self.fernet = Fernet(encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt an API key. Returns base64 string."""

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an API key. Returns plaintext string."""

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key. Use for initial setup."""
        return Fernet.generate_key().decode()

    async def rotate_all(self, db: AsyncSession, new_key: str) -> int:
        """
        Re-encrypt all stored API keys with new_key.
        1. Decrypt each key with current key
        2. Re-encrypt with new key
        3. Update DB records
        Returns count of rotated keys.
        """
```

### Acceptance Criteria
- [ ] Encrypt/decrypt round-trip works correctly
- [ ] Invalid key raises clear error
- [ ] Key rotation re-encrypts all stored keys
- [ ] Generated keys are valid Fernet keys

---

## Task 1.6: Admin Router + User Override Endpoints

### New File: `fastapi-backend/app/routers/ai_config.py`

Two sets of endpoints: **Admin** (global provider management) and **User** (personal API key overrides).

### Admin Endpoints (prefix: `/api/ai/config`)

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/providers` | GET | List all global providers | Application Owner |
| `/providers` | POST | Create global provider | Application Owner |
| `/providers/{id}` | PUT | Update global provider | Application Owner |
| `/providers/{id}` | DELETE | Delete global provider | Application Owner |
| `/providers/{id}/test` | POST | Test connectivity (makes a minimal API call) | Application Owner |
| `/models` | GET | List all models | Application Owner |
| `/models` | POST | Register model | Application Owner |
| `/models/{id}` | PUT | Update model | Application Owner |
| `/models/{id}` | DELETE | Delete model | Application Owner |
| `/summary` | GET | Full config summary (providers + defaults) | Application Owner |

### User Override Endpoints (prefix: `/api/ai/config/me`)

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/me/providers` | GET | List current user's personal provider overrides | Any authenticated user |
| `/me/providers` | POST | Set personal API key override for a provider type | Any authenticated user |
| `/me/providers/{provider_type}` | PUT | Update personal API key / model preference | Any authenticated user |
| `/me/providers/{provider_type}` | DELETE | Remove personal override (revert to global) | Any authenticated user |
| `/me/providers/{provider_type}/test` | POST | Test personal API key connectivity | Any authenticated user |
| `/me/summary` | GET | Effective config for current user (resolved: user override > global) | Any authenticated user |

### Implementation Details

**Admin Auth**: Reuse `PermissionService.get_user_application_role()` from `fastapi-backend/app/services/permission_service.py`. Require that the user is an owner of at least one application.

**User Override Auth**: Any authenticated user. Users can only CRUD their own overrides (enforced by `current_user.id` in queries).

**Provider Test** (`POST /providers/{id}/test` or `POST /me/providers/{type}/test`):
- For OpenAI: Call `client.models.list()` (minimal API call to verify key)
- For Anthropic: Call `client.messages.create()` with minimal content
- For Ollama: Call `GET {base_url}/api/tags` (list local models)
- Returns `{ "success": true, "message": "Connected successfully" }` or error details

**Admin Provider Create** (`POST /providers`):
- Accepts plain `api_key` in request body
- Encrypts using `ApiKeyEncryption.encrypt()` before storing
- Sets `scope='global'`, `user_id=NULL`
- Returns `AiProviderResponse` (no key exposed)

**User Override Create** (`POST /me/providers`):
- Accepts `UserProviderOverride` schema (provider_type, api_key, optional base_url, preferred_model)
- Encrypts API key before storage
- Sets `scope='user'`, `user_id=current_user.id`
- If override already exists for this provider_type + user, returns 409 Conflict
- Returns `AiProviderResponse`

**User Summary** (`GET /me/summary`):
- For each provider type (openai, anthropic, ollama):
  - Check if user has a personal override
  - If yes: show user's provider as "active", global as "fallback"
  - If no: show global as "active"
- Shows effective chat model, vision model, embedding model (always global)

**Provider Update** (`PUT /providers/{id}` or `PUT /me/providers/{type}`):
- If `api_key` is provided (non-null), re-encrypt and update
- If `api_key` is null/absent, leave existing encrypted key unchanged

### Modify: `fastapi-backend/app/main.py`

Mount the router:
```python
from app.routers import ai_config
app.include_router(ai_config.router)
```

### Acceptance Criteria
- [ ] All admin CRUD operations work for global providers and models
- [ ] All user override CRUD operations work for personal API keys
- [ ] Provider test endpoint validates connectivity (both admin and user keys)
- [ ] API keys are encrypted before storage, never returned in responses
- [ ] Only application owners can access admin endpoints
- [ ] Any authenticated user can manage their own overrides
- [ ] Users can only see/edit their own overrides (not other users')
- [ ] User summary correctly resolves effective provider (user override > global)
- [ ] 409 Conflict on duplicate user override for same provider_type
- [ ] Proper error responses (404, 403, 409, 422)

---

## Task 1.7: Configuration

### Modify: `fastapi-backend/app/config.py`

Add the following settings:

```python
# AI Configuration
ai_encryption_key: str = ""           # Fernet key for API key encryption
ai_default_embedding_dimensions: int = 1536
ai_default_provider: str = "openai"   # Default provider name
```

### Acceptance Criteria
- [ ] Settings load from environment variables (`AI_ENCRYPTION_KEY`, etc.)
- [ ] Default values are sensible for development
- [ ] Empty `ai_encryption_key` doesn't crash app on startup (only when AI features used)

---

## Task 1.8: Dependencies

### Modify: `fastapi-backend/requirements.txt`

Add:
```
openai>=1.30.0
anthropic>=0.40.0
cryptography>=42.0.0
```

### Acceptance Criteria
- [ ] `pip install -r requirements.txt` succeeds
- [ ] No version conflicts with existing dependencies

---

## Task 1.9: Tests

### New File: `fastapi-backend/tests/test_ai_providers.py`

Unit tests for each provider adapter:

```
test_openai_chat_completion_returns_string
test_openai_chat_completion_stream_yields_chunks
test_openai_generate_embedding_returns_vector
test_openai_generate_embeddings_batch_returns_list
test_openai_describe_image_returns_description
test_openai_chat_with_image_content_block
test_anthropic_chat_completion_returns_string
test_anthropic_chat_completion_stream_yields_chunks
test_anthropic_embedding_raises_not_implemented
test_anthropic_describe_image_returns_description
test_anthropic_chat_with_image_content_block
test_ollama_chat_completion_returns_string
test_ollama_chat_completion_stream_yields_chunks
test_ollama_generate_embedding_returns_vector
test_provider_registry_resolves_user_override_first
test_provider_registry_falls_back_to_global
test_provider_registry_raises_on_no_config
test_provider_registry_embedding_always_global
test_provider_registry_vision_user_override
test_embedding_normalizer_pads_short_vectors
test_embedding_normalizer_truncates_long_vectors
test_embedding_normalizer_l2_normalizes
test_encryption_roundtrip
test_encryption_invalid_key_raises
test_encryption_generate_key_valid
```

Use mocks for actual API calls (mock `openai.AsyncOpenAI`, `anthropic.AsyncAnthropic`, `httpx.AsyncClient`).

### New File: `fastapi-backend/tests/test_ai_config_router.py`

API tests for admin + user override routes:

```
# Admin endpoints
test_list_providers_empty
test_create_provider_openai
test_create_provider_ollama_no_key
test_create_provider_validates_type
test_create_provider_encrypts_key
test_get_provider_does_not_expose_key
test_update_provider_preserves_key_if_not_sent
test_update_provider_re_encrypts_new_key
test_delete_provider_cascades_models
test_test_provider_connectivity_success
test_test_provider_connectivity_failure
test_create_model
test_create_model_unique_constraint
test_update_model
test_delete_model
test_config_summary
test_non_owner_gets_403

# User override endpoints
test_user_create_override_openai
test_user_create_override_encrypts_key
test_user_create_override_duplicate_409
test_user_list_own_overrides
test_user_update_override_model_preference
test_user_delete_override_reverts_to_global
test_user_test_own_key_connectivity
test_user_summary_with_override
test_user_summary_without_override_shows_global
test_user_cannot_see_other_users_overrides
test_user_override_does_not_affect_global
test_any_authenticated_user_can_set_override
```

### Acceptance Criteria
- [ ] All tests pass with `pytest tests/test_ai_providers.py tests/test_ai_config_router.py -v`
- [ ] Provider tests use mocks (no real API calls)
- [ ] Router tests use test database (follow existing test patterns)
- [ ] Edge cases covered (invalid input, unauthorized access, cascade deletes)
- [ ] User override isolation tested (user A can't see user B's keys)
- [ ] Provider resolution order tested (user > global > error)

---

## Verification Checklist

```bash
cd fastapi-backend

# 1. Run migration
alembic upgrade head

# 2. Verify tables exist
# psql: \dt AiProviders; \dt AiModels;

# 3. Run all Phase 1 tests
pytest tests/test_ai_providers.py tests/test_ai_config_router.py -v

# 4. Test admin: create global provider
# POST /api/ai/config/providers (create OpenAI provider with api_key)
# POST /api/ai/config/providers/{id}/test (test connectivity)

# 5. Verify API key encryption
# POST provider with api_key="sk-test123"
# GET provider — has_api_key=true, no key in response
# Verify DB column is encrypted (not plaintext)

# 6. Test user override: set personal API key
# POST /api/ai/config/me/providers (set user's own OpenAI key)
# GET /api/ai/config/me/summary (verify user override shows as active)
# POST /api/ai/config/me/providers/openai/test (test user's key)

# 7. Test override resolution
# With user override: chat provider should use user's key
# DELETE /api/ai/config/me/providers/openai (remove override)
# Chat provider should fall back to global key
```
