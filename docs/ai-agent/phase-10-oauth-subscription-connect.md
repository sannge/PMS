# Phase 10: OAuth Subscription Connect + Login 2FA

**Goal**: Replace API key-based user AI override with OAuth subscription connection for OpenAI Codex (ChatGPT Plus/Pro) and Anthropic Claude, with appropriate warnings about third-party token restrictions. Additionally, implement login-time 2FA via email verification code on every login.

**Depends on**: Phase 7 (user chat override UI, provider registry, AiProviders table)
**Downstream**: None (final user-facing AI feature)

---

## Task 10.0a: Bug Fix — Wire AiToggleButton + AiSidebar into Dashboard

**Problem**: The `AiToggleButton` and `AiSidebar` components were built in Phase 5 but never wired into `dashboard.tsx`. The Blair AI button does not appear in the title bar, making the AI sidebar (and its gear icon for AI Settings) completely inaccessible.

**Blocker for**: Task 10.5 (Frontend UI Redesign) — the OAuth connection UI lives inside `user-chat-override.tsx`, accessed via the sidebar gear icon. Without the sidebar, Phase 10's frontend is unreachable.

### Modify: `electron-app/src/renderer/pages/dashboard.tsx`

1. Import `AiToggleButton` and `AiSidebar` from `@/components/ai`
2. Pass `AiToggleButton` as `extraControls` to `WindowTitleBar`:

```tsx
import { AiToggleButton, AiSidebar } from '@/components/ai'

<WindowTitleBar
  theme={theme}
  onThemeChange={onThemeChange}
  extraControls={<AiToggleButton />}
/>
```

3. Render `<AiSidebar />` adjacent to `<main>` inside the layout flex container:

```tsx
<div className="flex flex-1 overflow-hidden">
  <Sidebar ... />
  <main ...>{renderContent()}</main>
  <AiSidebar />
</div>
```

### Acceptance Criteria

- [ ] Blair sparkles icon visible in title bar (between theme toggle and user menu)
- [ ] Clicking the icon toggles the AI sidebar open/closed
- [ ] Sidebar state persists across page navigation (localStorage)
- [ ] AI Settings gear icon accessible inside the sidebar
- [ ] No layout shift when sidebar opens (sidebar pushes or overlays content)

---

## Task 10.0b: Bug Fix — Add Missing `/ai/config/system-prompt` Endpoint

**Problem**: The frontend `PersonalityTab` component (`electron-app/src/renderer/components/ai/personality-tab.tsx`) makes `GET` and `PUT` calls to `/api/ai/config/system-prompt`, but no backend endpoint exists — resulting in a **404 Not Found** on every page load. The system prompt for Blair is currently hardcoded in `graph.py:48`.

**Blocker for**: Task 10.8 (Frontend UI Redesign) — the personality tab is part of the AI Settings panel and shows errors without this endpoint.

### New Files

- `fastapi-backend/alembic/versions/20260228_add_ai_system_prompt.py` — Migration creating `ai_system_prompts` single-row table (id UUID PK, prompt Text NOT NULL, updated_at TimestampTZ)
- `fastapi-backend/app/models/ai_system_prompt.py` — `AiSystemPrompt` SQLAlchemy model
- `fastapi-backend/tests/test_system_prompt.py` — 6 tests: GET empty, PUT create, GET after PUT, PUT empty resets, >2000 chars 422, non-developer 403

### Modified Files

- `fastapi-backend/app/models/__init__.py` — Add `AiSystemPrompt` import + `__all__` entry
- `fastapi-backend/app/schemas/ai_config.py` — Add `SystemPromptResponse` and `SystemPromptUpdate` schemas
- `fastapi-backend/app/routers/ai_config.py` — Add `GET /system-prompt` and `PUT /system-prompt` endpoints (both require `require_developer`)
- `fastapi-backend/app/ai/agent/graph.py` — Query `AiSystemPrompt` in agent_node's DB session block, use stored prompt as override (fallback to hardcoded `SYSTEM_PROMPT`)

### Endpoint Behavior

**`GET /system-prompt`** (require_developer):
- Row exists → `{ "prompt": row.prompt }`
- No row → `{ "prompt": "" }` (frontend falls back to its own default)

**`PUT /system-prompt`** (require_developer):
- Non-empty prompt → upsert row, return `{ "prompt": saved_value }`
- Empty prompt `""` → delete row (reset to default), return `{ "prompt": "" }`

### Agent Integration

In `graph.py` `agent_node`, extend the existing `if not _cached_chat_model:` DB session block to also query `AiSystemPrompt`. Cache the custom prompt alongside the chat model. Use it in place of the hardcoded `SYSTEM_PROMPT` when available.

### Acceptance Criteria

- [ ] `GET /api/ai/config/system-prompt` returns 200 (not 404)
- [ ] `PUT /api/ai/config/system-prompt` creates/updates/deletes the stored prompt
- [ ] Hardcoded `SYSTEM_PROMPT` in `graph.py` remains as fallback when no custom prompt is set
- [ ] Blair uses the stored custom prompt when one exists
- [ ] Non-developer users get 403 on both endpoints
- [ ] Prompt text limited to 2000 characters (422 on overflow)
- [ ] 6 tests pass in `test_system_prompt.py`

---

## Task 10.0: Documentation

Create and update documentation files for Phase 10.

### New Files

- `docs/ai-agent/phase-10-oauth-subscription-connect.md` — This spec
- `docs/ai-agent/tasks/phase-10-tasks.md` — Granular task breakdown

### Modified Files

- `docs/ai-agent/README.md` — Add Phase 10 to Table of Contents + Decisions Summary
- `docs/ai-agent/tasks/index.md` — Add Phase 10 to Phase Summary + Dependency Graph
- `docs/ai-agent/file-manifest.md` — Add Phase 10 new/modified files

### Acceptance Criteria

- [ ] Spec matches format of existing phase docs
- [ ] Tasks file has granular breakdown with ~150 tasks
- [ ] All index files updated with Phase 10 references

---

## Task 10.1: Database Schema — OAuth Columns on AiProviders

### Modify: `fastapi-backend/app/models/ai_provider.py`

Add OAuth-related columns to the existing `AiProviders` table:

```python
# Authentication method discriminator
auth_method = Column(
    String(20),
    nullable=False,
    default="api_key",
    server_default="api_key",
)  # 'api_key' | 'oauth'

# OAuth token storage (Fernet-encrypted, reuse existing encryption)
oauth_access_token = Column(Text, nullable=True)   # Encrypted
oauth_refresh_token = Column(Text, nullable=True)   # Encrypted
oauth_token_expires_at = Column(
    DateTime(timezone=True),
    nullable=True,
)
oauth_scope = Column(String(500), nullable=True)    # Space-separated scopes
oauth_provider_user_id = Column(String(255), nullable=True)  # Provider's user ID
```

### New Migration: `alembic/versions/YYYYMMDD_add_oauth_columns.py`

```sql
ALTER TABLE "AiProviders"
    ADD COLUMN auth_method VARCHAR(20) NOT NULL DEFAULT 'api_key',
    ADD COLUMN oauth_access_token TEXT,
    ADD COLUMN oauth_refresh_token TEXT,
    ADD COLUMN oauth_token_expires_at TIMESTAMPTZ,
    ADD COLUMN oauth_scope VARCHAR(500),
    ADD COLUMN oauth_provider_user_id VARCHAR(255);

-- CHECK constraint
ALTER TABLE "AiProviders"
    ADD CONSTRAINT ck_auth_method CHECK (auth_method IN ('api_key', 'oauth'));

-- Index for lookup
CREATE INDEX ix_aiproviders_auth_method ON "AiProviders" (auth_method);
```

Existing rows keep `auth_method='api_key'` — fully backward compatible. Admin global API keys remain unchanged.

### Acceptance Criteria

- [ ] `auth_method` column defaults to `'api_key'` — no existing data affected
- [ ] CHECK constraint enforces `'api_key'` or `'oauth'` only
- [ ] OAuth token columns are nullable (only populated for OAuth users)
- [ ] Token columns use `Text` type for encrypted ciphertext storage
- [ ] `oauth_token_expires_at` uses `TIMESTAMPTZ` (timezone-aware)
- [ ] Migration is reversible (down migration drops columns)
- [ ] Index on `auth_method` for provider resolution queries

---

## Task 10.2: Backend OAuth Infrastructure

### New File: `fastapi-backend/app/ai/oauth_service.py`

```python
class OAuthService:
    """
    OAuth 2.0 + PKCE service for AI provider subscription connections.

    Supports:
    - OpenAI (Codex / ChatGPT Plus/Pro subscriptions)
    - Anthropic (Claude subscriptions — with third-party blocking caveat)

    Uses PKCE (S256) for security. State tokens stored in Redis with 10-min TTL.
    """

    PROVIDER_CONFIG = {
        "openai": {
            "auth_url": "https://auth.openai.com/oauth/authorize",
            "token_url": "https://auth.openai.com/oauth/token",
            "revoke_url": "https://auth.openai.com/oauth/revoke",
            "scopes": ["openai.chat", "openai.models.read"],
        },
        "anthropic": {
            "auth_url": "https://claude.ai/oauth/authorize",
            "token_url": "https://claude.ai/oauth/token",
            "revoke_url": "https://claude.ai/oauth/revoke",
            "scopes": ["claude.chat", "claude.models.read"],
        },
    }

    def __init__(self, redis: Redis, config: Settings):
        self.redis = redis
        self.config = config

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """
        Generate PKCE code_verifier + code_challenge (S256).

        code_verifier: 43-128 character URL-safe random string
        code_challenge: BASE64URL(SHA256(code_verifier))

        Returns: (code_verifier, code_challenge)
        """

    async def generate_auth_url(
        self,
        provider_type: str,   # "openai" | "anthropic"
        user_id: UUID,
        redirect_uri: str,
    ) -> OAuthInitiateResponse:
        """
        Generate OAuth authorization URL with PKCE.

        1. Generate code_verifier + code_challenge
        2. Generate random state token
        3. Store {state: {user_id, code_verifier, provider_type}} in Redis (10-min TTL)
        4. Construct auth URL with params:
           - client_id, redirect_uri, response_type=code,
           - code_challenge, code_challenge_method=S256,
           - state, scope
        5. Return auth URL + state
        """

    async def exchange_code_for_tokens(
        self,
        provider_type: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> OAuthTokenResponse:
        """
        Exchange authorization code for access + refresh tokens.

        1. Validate state token from Redis (single-use — delete after read)
        2. Extract code_verifier from stored state data
        3. POST to provider token_url with:
           - grant_type=authorization_code, code, redirect_uri,
           - client_id, code_verifier
        4. Parse response: access_token, refresh_token, expires_in, scope
        5. Return tokens (caller handles encryption + storage)
        """

    async def refresh_tokens(
        self,
        provider_type: str,
        refresh_token: str,  # Decrypted
    ) -> OAuthTokenResponse:
        """
        Refresh an expired access token.

        POST to provider token_url with:
        - grant_type=refresh_token, refresh_token, client_id

        Returns new access_token (and possibly new refresh_token).
        """

    async def revoke_tokens(
        self,
        provider_type: str,
        access_token: str,  # Decrypted
    ) -> None:
        """
        Revoke OAuth tokens at the provider.

        POST to provider revoke_url with:
        - token, token_type_hint=access_token, client_id

        Best-effort — don't fail if provider returns error.
        """
```

### Modify: `fastapi-backend/app/config.py`

Add OAuth configuration settings:

```python
# OAuth Client IDs (registered with providers)
openai_oauth_client_id: str = ""
anthropic_oauth_client_id: str = ""

# OAuth State TTL
oauth_state_ttl_seconds: int = 600  # 10 minutes
```

### New File: `fastapi-backend/app/schemas/oauth.py`

```python
class OAuthInitiateRequest(BaseModel):
    provider_type: Literal["openai", "anthropic"]
    redirect_uri: str  # Electron localhost callback URL

class OAuthInitiateResponse(BaseModel):
    auth_url: str          # Full URL to open in browser
    state: str             # State token for CSRF validation
    expires_in: int = 600  # State validity in seconds

class OAuthCallbackRequest(BaseModel):
    provider_type: Literal["openai", "anthropic"]
    code: str              # Authorization code from provider
    state: str             # State token for validation
    redirect_uri: str      # Must match initiate redirect_uri

class OAuthTokenResponse(BaseModel):
    """Internal — never returned to client."""
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    scope: str | None = None

class OAuthConnectionStatus(BaseModel):
    connected: bool
    provider_type: str | None = None
    auth_method: Literal["api_key", "oauth"] | None = None
    provider_user_id: str | None = None
    connected_at: datetime | None = None
    token_expires_at: datetime | None = None
    scopes: list[str] = []

class OAuthDisconnectResponse(BaseModel):
    disconnected: bool
    fallback: str  # "company_default" or "none"
```

### New Endpoints: `fastapi-backend/app/routers/ai_oauth.py`

```python
router = APIRouter(prefix="/api/ai/config/me/oauth", tags=["AI OAuth"])

@router.post("/initiate", response_model=OAuthInitiateResponse)
async def initiate_oauth(
    body: OAuthInitiateRequest,
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    """
    Generate OAuth authorization URL for provider.

    Returns auth URL that Electron opens in a BrowserWindow.
    State token stored in Redis for callback validation.
    """

@router.post("/callback")
async def oauth_callback(
    body: OAuthCallbackRequest,
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange authorization code for tokens and store connection.

    1. Validate state token (CSRF protection)
    2. Exchange code for tokens via provider
    3. Encrypt tokens with Fernet
    4. Create/update AiProvider with auth_method='oauth'
    5. Auto-create chat AiModel (same as API key flow)
    6. Return connection status
    """

@router.delete("/disconnect", response_model=OAuthDisconnectResponse)
async def disconnect_oauth(
    current_user: User = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect OAuth provider and revoke tokens.

    1. Revoke tokens at provider (best-effort)
    2. Clear OAuth columns on AiProvider
    3. Delete user-scoped AiProvider + AiModel
    4. User falls back to company default
    """

@router.get("/status", response_model=OAuthConnectionStatus)
async def oauth_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current OAuth connection status.

    Returns connected state, provider info, and token expiry.
    Never returns actual tokens.
    """
```

### Token Refresh Integration

```python
# In provider_registry.py — modify get_chat_provider()

async def get_chat_provider(self, db: AsyncSession, user_id: UUID | None = None):
    """
    Resolve chat provider. If user has OAuth connection:
    1. Check token expiry
    2. If expired (or within 5-min buffer), refresh automatically
    3. Update encrypted tokens in DB
    4. Return provider with fresh access token
    """
    provider = await self._resolve_provider(db, "chat", user_id)

    if provider and provider.auth_method == "oauth":
        if self._token_needs_refresh(provider):
            await self._refresh_oauth_token(db, provider)

    return self._build_adapter(provider)
```

### Acceptance Criteria

- [ ] PKCE uses S256 (SHA-256), never plain
- [ ] State tokens are single-use (deleted from Redis after validation)
- [ ] State tokens expire after 10 minutes
- [ ] All tokens encrypted with Fernet before DB storage
- [ ] Tokens never returned in API responses
- [ ] Tokens never logged (access_token, refresh_token)
- [ ] Token refresh happens automatically before API calls
- [ ] Revocation is best-effort (no failure on revoke error)
- [ ] `get_current_user` dependency on all endpoints (any authenticated user)
- [ ] Auto-creates chat AiModel on successful connection
- [ ] Disconnect cleans up all OAuth data

---

## Task 10.3: Provider Adapter Updates

### New File: `fastapi-backend/app/ai/codex_provider.py`

OpenAI Codex adapter that uses OAuth access tokens instead of API keys:

```python
class CodexProvider(ChatProviderInterface):
    """
    OpenAI Codex adapter for ChatGPT Plus/Pro subscription OAuth.

    Uses the user's OAuth access token as Bearer auth instead of
    an API key. Same API endpoints as OpenAI, different auth header.
    """

    def __init__(
        self,
        access_token: str,   # Decrypted OAuth access token
        model: str = "gpt-5.2",
    ):
        self.client = AsyncOpenAI(
            api_key=access_token,  # OpenAI SDK accepts OAuth tokens as api_key
            # No base_url override — same API endpoints
        )
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Same as OpenAI provider, but with OAuth token auth.
        Handles 401 (token expired/revoked) gracefully.
        """

    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> AsyncIterator[ChatStreamChunk]:
        """Streaming variant with OAuth auth."""
```

### Modify: `fastapi-backend/app/ai/provider_registry.py`

Update provider resolution to detect `auth_method`:

```python
def _build_adapter(self, provider: AiProvider, model: AiModel) -> ChatProviderInterface:
    """Build the correct adapter based on auth_method."""

    if provider.auth_method == "oauth":
        access_token = self.encryption.decrypt(provider.oauth_access_token)

        if provider.provider_type == "openai":
            return CodexProvider(
                access_token=access_token,
                model=model.model_id,
            )
        elif provider.provider_type == "anthropic":
            return AnthropicProvider(
                api_key=access_token,  # OAuth token used as API key
                model=model.model_id,
            )

    # Existing API key path (unchanged)
    api_key = self.encryption.decrypt(provider.api_key)
    if provider.provider_type == "openai":
        return OpenAiProvider(api_key=api_key, model=model.model_id)
    elif provider.provider_type == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model.model_id)
    elif provider.provider_type == "ollama":
        return OllamaProvider(base_url=provider.base_url, model=model.model_id)
```

### Modify: `fastapi-backend/app/ai/anthropic_provider.py`

Add error handling for subscription token rejection:

```python
async def chat(self, messages, tools=None, **kwargs):
    try:
        response = await self.client.messages.create(...)
        return self._parse_response(response)
    except anthropic.AuthenticationError as e:
        # Anthropic may reject third-party OAuth subscription tokens
        if "subscription" in str(e).lower() or "unauthorized" in str(e).lower():
            raise ProviderAuthError(
                provider="anthropic",
                message=(
                    "Anthropic rejected your subscription token. "
                    "This may be because Anthropic does not allow third-party "
                    "applications to use personal subscription tokens. "
                    "Please use an API key instead, or contact Anthropic support."
                ),
                recoverable=True,
            )
        raise
```

### New File: `fastapi-backend/app/ai/exceptions.py`

```python
class ProviderAuthError(Exception):
    """Raised when a provider rejects authentication."""

    def __init__(self, provider: str, message: str, recoverable: bool = False):
        self.provider = provider
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)
```

### Acceptance Criteria

- [ ] `CodexProvider` uses OAuth token via OpenAI SDK's `api_key` parameter
- [ ] `CodexProvider` handles 401 (expired/revoked) with clear error message
- [ ] Provider registry detects `auth_method` and builds correct adapter
- [ ] Registry auto-refreshes expired tokens before building adapter
- [ ] Anthropic provider catches subscription rejection with user-friendly message
- [ ] `ProviderAuthError` is recoverable (UI can suggest API key fallback)
- [ ] Existing API key flow completely unchanged
- [ ] Ollama unaffected (no OAuth support, always `auth_method='api_key'`)

---

## Task 10.4: Electron OAuth Flow

### New File: `electron-app/src/main/oauth-handler.ts`

```typescript
/**
 * Electron main process OAuth handler.
 *
 * Flow:
 * 1. Renderer requests OAuth initiation via IPC
 * 2. Main process starts temporary localhost HTTP server
 * 3. Opens BrowserWindow with provider auth URL
 * 4. Provider redirects to localhost callback
 * 5. HTTP server captures code + state
 * 6. Forwards to renderer via IPC
 * 7. Cleans up window + server
 *
 * Security:
 * - Random port (0 = OS-assigned)
 * - Session partition (isolated cookies)
 * - 5-minute timeout
 * - Origin validation on callback
 */

import { BrowserWindow, ipcMain } from 'electron'
import { createServer, type Server } from 'http'

interface OAuthResult {
  code: string
  state: string
}

export function registerOAuthHandlers(): void {
  ipcMain.handle(
    'oauth:initiate',
    async (_event, authUrl: string): Promise<OAuthResult> => {
      // 1. Start localhost HTTP server on random port
      const { server, port } = await startCallbackServer()

      // 2. Open BrowserWindow with auth URL
      const authWindow = createOAuthWindow(authUrl)

      // 3. Wait for callback (with 5-min timeout)
      const result = await waitForCallback(server, authWindow)

      // 4. Cleanup
      authWindow.destroy()
      server.close()

      return result
    },
  )
}

function createOAuthWindow(authUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 600,
    height: 700,
    webPreferences: {
      partition: 'oauth-session', // Isolated session
      nodeIntegration: false,
      contextIsolation: true,
    },
    autoHideMenuBar: true,
    title: 'Connect AI Subscription',
  })

  window.loadURL(authUrl)
  return window
}

async function startCallbackServer(): Promise<{
  server: Server
  port: number
}> {
  // Create HTTP server, listen on localhost:0 (random port)
  // Parse /oauth/callback?code=xxx&state=yyy
  // Respond with "You can close this window" HTML
}

async function waitForCallback(
  server: Server,
  window: BrowserWindow,
): Promise<OAuthResult> {
  // Race between:
  // - Callback received (resolve)
  // - Window closed by user (reject)
  // - 5-minute timeout (reject + cleanup)
}
```

### Modify: `electron-app/src/main/preload.ts`

Expose OAuth IPC channel:

```typescript
contextBridge.exposeInMainWorld('electronAPI', {
  // ... existing API ...

  // OAuth
  initiateOAuth: (authUrl: string) =>
    ipcRenderer.invoke('oauth:initiate', authUrl),
})
```

### Modify: `electron-app/src/renderer/types/electron.d.ts`

Add TypeScript declaration:

```typescript
interface ElectronAPI {
  // ... existing ...
  initiateOAuth: (authUrl: string) => Promise<{ code: string; state: string }>
}
```

### Acceptance Criteria

- [ ] BrowserWindow opens with provider auth URL
- [ ] Localhost HTTP server starts on random port
- [ ] Callback captures code + state from redirect
- [ ] Window auto-closes after callback
- [ ] Server destroyed after callback
- [ ] 5-minute timeout cleans up resources
- [ ] User closing window handled gracefully (reject promise)
- [ ] Session partition isolates OAuth cookies from main app
- [ ] IPC channel exposed via preload (no node integration)
- [ ] Origin validation on callback (must be localhost)

---

## Task 10.5: Frontend UI Redesign

### New File: `electron-app/src/renderer/hooks/use-oauth-connect.ts`

```typescript
/**
 * React Query hooks for OAuth subscription connection.
 */

export function useOAuthStatus() {
  /**
   * Query: GET /api/ai/config/me/oauth/status
   * Returns current OAuth connection status.
   * refetchOnWindowFocus: true (token may expire while away)
   */
}

export function useOAuthInitiate() {
  /**
   * Mutation: Initiate OAuth flow.
   * 1. POST /api/ai/config/me/oauth/initiate -> get auth URL
   * 2. Call window.electronAPI.initiateOAuth(authUrl)
   * 3. Electron opens BrowserWindow, waits for callback
   * 4. POST /api/ai/config/me/oauth/callback with code + state
   * 5. Invalidate: oauthStatus query
   */
}

export function useOAuthDisconnect() {
  /**
   * Mutation: DELETE /api/ai/config/me/oauth/disconnect
   * Invalidates: oauthStatus query
   * Confirmation handled by caller
   */
}
```

### Modify: `electron-app/src/renderer/components/ai/user-chat-override.tsx`

Redesign from API key form to OAuth connection cards:

```tsx
/**
 * User Chat AI Settings — OAuth subscription connect.
 *
 * Access: Any authenticated user (sidebar gear icon)
 *
 * ┌──────────────────────────────────────────────────┐
 * │ ⚙ AI Settings                                   │
 * ├──────────────────────────────────────────────────┤
 * │                                                  │
 * │ Connect your AI subscription to power Blair.     │
 * │ Otherwise, the company default will be used.     │
 * │                                                  │
 * │ ┌────────────────────────────────────────────┐   │
 * │ │ 🟢 OpenAI                                  │   │
 * │ │                                            │   │
 * │ │ Connect your ChatGPT Plus or Pro           │   │
 * │ │ subscription to use GPT models.            │   │
 * │ │                                            │   │
 * │ │ [Connect with OpenAI]                      │   │
 * │ └────────────────────────────────────────────┘   │
 * │                                                  │
 * │ ┌────────────────────────────────────────────┐   │
 * │ │ ⚠ Anthropic                      (amber)  │   │
 * │ │                                            │   │
 * │ │ Connect your Claude subscription.          │   │
 * │ │                                            │   │
 * │ │ ⚠ Anthropic may block third-party apps     │   │
 * │ │   from using subscription tokens. If       │   │
 * │ │   connection fails, use an API key instead. │   │
 * │ │                                            │   │
 * │ │ [Connect with Anthropic]                   │   │
 * │ └────────────────────────────────────────────┘   │
 * │                                                  │
 * │ ▸ Advanced: Use API Key Instead                  │
 * │                                                  │
 * │ Currently using: Company default (GPT-5.2)       │
 * └──────────────────────────────────────────────────┘
 *
 * When connected:
 * ┌──────────────────────────────────────────────────┐
 * │ ⚙ AI Settings                                   │
 * ├──────────────────────────────────────────────────┤
 * │                                                  │
 * │ ┌────────────────────────────────────────────┐   │
 * │ │ ✅ Connected to OpenAI                     │   │
 * │ │                                            │   │
 * │ │ Subscription: ChatGPT Plus                 │   │
 * │ │ Connected: Feb 28, 2026                    │   │
 * │ │                                            │   │
 * │ │ Model: [GPT-5.2              ▼]            │   │
 * │ │                                            │   │
 * │ │ [Test Connection] 🟢 Working (201ms)       │   │
 * │ │                                            │   │
 * │ │ [Disconnect]                               │   │
 * │ └────────────────────────────────────────────┘   │
 * │                                                  │
 * │ Currently using: Your OpenAI subscription        │
 * └──────────────────────────────────────────────────┘
 */
```

### Component Structure

```tsx
function UserChatOverride() {
  const { data: status } = useOAuthStatus()
  const { data: userOverride } = useUserChatOverride()

  // Determine current state
  const isOAuthConnected = status?.connected
  const isApiKeyOverride = userOverride?.auth_method === 'api_key'

  if (isOAuthConnected) {
    return <ConnectedCard status={status} />
  }

  return (
    <>
      <ConnectionCards />
      <ApiKeyFallback /> {/* Collapsible "Advanced" section */}
      <StatusLine />
    </>
  )
}
```

### Acceptance Criteria

- [ ] OpenAI card shows "Connect with OpenAI" button
- [ ] Anthropic card shows amber warning banner about third-party blocking
- [ ] Clicking Connect triggers OAuth flow (BrowserWindow opens)
- [ ] Loading state shown while waiting for OAuth callback
- [ ] Connected state shows provider, subscription type, connected date
- [ ] Model selector available after connection
- [ ] Test button verifies OAuth token works
- [ ] Disconnect button with confirmation removes connection
- [ ] "Use API Key" available as collapsible fallback option
- [ ] Status line shows current effective configuration
- [ ] Error states displayed (auth failed, provider rejected, timeout)
- [ ] Responsive layout within sidebar panel

---

## Task 10.6: Tests

### New File: `fastapi-backend/tests/test_oauth_service.py`

```python
"""OAuth service unit tests — PKCE, state, token exchange."""

class TestPKCE:
    def test_code_verifier_length(self):
        """code_verifier is 43-128 characters."""

    def test_code_verifier_url_safe(self):
        """code_verifier contains only [A-Z, a-z, 0-9, -, ., _, ~]."""

    def test_code_challenge_s256(self):
        """code_challenge = BASE64URL(SHA256(code_verifier))."""

    def test_code_challenge_no_padding(self):
        """code_challenge has no = padding (base64url)."""

    def test_pkce_pair_unique(self):
        """Each call generates a unique pair."""

class TestStateToken:
    async def test_generate_state_stores_in_redis(self):
        """State token stored in Redis with user_id and code_verifier."""

    async def test_state_expires_after_ttl(self):
        """State token expires after 10 minutes."""

    async def test_validate_state_single_use(self):
        """State token deleted from Redis after first validation."""

    async def test_validate_expired_state_fails(self):
        """Expired state token returns None."""

    async def test_validate_invalid_state_fails(self):
        """Unknown state token returns None."""

class TestAuthUrl:
    async def test_openai_auth_url_format(self):
        """OpenAI auth URL includes client_id, PKCE, state, scopes."""

    async def test_anthropic_auth_url_format(self):
        """Anthropic auth URL includes correct parameters."""

    async def test_auth_url_includes_redirect_uri(self):
        """redirect_uri parameter matches input."""

class TestTokenExchange:
    async def test_exchange_openai_success(self):
        """Successful code exchange returns tokens (mock HTTP)."""

    async def test_exchange_anthropic_success(self):
        """Successful code exchange returns tokens (mock HTTP)."""

    async def test_exchange_invalid_code_fails(self):
        """Invalid authorization code raises error."""

    async def test_exchange_invalid_state_fails(self):
        """Invalid state token raises 400."""

class TestTokenRefresh:
    async def test_refresh_returns_new_access_token(self):
        """Refresh returns new access token."""

    async def test_refresh_revoked_token_raises(self):
        """Revoked refresh token raises ProviderAuthError."""
```

### New File: `fastapi-backend/tests/test_oauth_flow.py`

```python
"""OAuth endpoint integration tests."""

class TestInitiateEndpoint:
    async def test_initiate_returns_auth_url(self):
        """POST /initiate returns auth_url and state."""

    async def test_initiate_requires_auth(self):
        """Unauthenticated request returns 401."""

    async def test_initiate_invalid_provider(self):
        """Unknown provider_type returns 422."""

class TestCallbackEndpoint:
    async def test_callback_stores_encrypted_tokens(self):
        """Tokens are Fernet-encrypted in AiProvider."""

    async def test_callback_creates_provider_with_oauth_method(self):
        """AiProvider created with auth_method='oauth'."""

    async def test_callback_auto_creates_chat_model(self):
        """Chat AiModel auto-created on connection."""

    async def test_callback_invalid_state_returns_400(self):
        """Invalid state token returns 400."""

    async def test_callback_expired_state_returns_400(self):
        """Expired state returns 400."""

    async def test_callback_updates_existing_provider(self):
        """Re-connecting updates existing OAuth provider."""

class TestDisconnectEndpoint:
    async def test_disconnect_removes_oauth_data(self):
        """OAuth columns cleared on disconnect."""

    async def test_disconnect_deletes_provider(self):
        """User-scoped AiProvider deleted."""

    async def test_disconnect_not_connected_returns_404(self):
        """Disconnect when no connection returns 404."""

class TestStatusEndpoint:
    async def test_status_connected(self):
        """Returns connected=true with provider info."""

    async def test_status_not_connected(self):
        """Returns connected=false when no OAuth provider."""

    async def test_status_never_returns_tokens(self):
        """Response never contains access_token or refresh_token."""
```

### New File: `fastapi-backend/tests/test_codex_provider.py`

```python
"""CodexProvider unit tests."""

class TestCodexProvider:
    async def test_uses_access_token_as_api_key(self):
        """OpenAI client initialized with OAuth access token."""

    async def test_chat_returns_response(self):
        """Successful chat returns ChatResponse (mock OpenAI)."""

    async def test_stream_chat_yields_chunks(self):
        """Streaming chat yields ChatStreamChunks."""

    async def test_handles_401_expired_token(self):
        """401 raises ProviderAuthError with clear message."""

    async def test_handles_403_subscription_issue(self):
        """403 raises ProviderAuthError about subscription."""

class TestRegistryOAuthResolution:
    async def test_resolves_codex_for_openai_oauth(self):
        """Registry returns CodexProvider for OpenAI OAuth users."""

    async def test_resolves_anthropic_with_oauth_token(self):
        """Registry uses OAuth token for Anthropic OAuth users."""

    async def test_auto_refreshes_expired_token(self):
        """Registry refreshes expired token before building adapter."""

    async def test_api_key_path_unchanged(self):
        """API key users still get standard providers."""
```

### Acceptance Criteria

- [ ] PKCE tests verify S256 compliance
- [ ] State token tests verify single-use + expiry
- [ ] Token exchange tests use mocked HTTP (no real provider calls)
- [ ] Endpoint tests verify auth, validation, encryption
- [ ] CodexProvider tests verify OAuth token usage
- [ ] Registry tests verify correct adapter resolution
- [ ] No tokens appear in test assertions (only verify encrypted storage)
- [ ] All tests follow existing conftest.py patterns (session-scoped tables)

---

## Task 10.7: Code Reviews & Sign-Off

### Security Review Focus Areas

| Area | Reviewer | Check |
|------|----------|-------|
| PKCE Implementation | SA | S256 only, no plain fallback, verifier entropy |
| State Parameter | SA | CSRF protection, Redis TTL, single-use enforcement |
| Token Storage | SA | Fernet encryption, no plaintext in DB or logs |
| Token Refresh | SA | Automatic refresh, no token in URL params |
| Electron Window | SA | Session partition, origin validation, cleanup |
| API Surface | SA | All endpoints require auth, no token leakage |

### Verification Checklist — E2E

```
1. OpenAI OAuth Connect:
   → Open sidebar → gear icon → AI Settings
   → Click "Connect with OpenAI"
   → BrowserWindow opens with OpenAI login
   → Log in / authorize
   → Window closes automatically
   → Status shows "✅ Connected to OpenAI"
   → Select model → Test Connection → 🟢 Working
   → Blair chat now uses your subscription

2. Anthropic OAuth Connect:
   → Click "Connect with Anthropic"
   → See amber warning banner about third-party blocking
   → BrowserWindow opens with Anthropic login
   → If authorized → connected successfully
   → If rejected → clear error message suggesting API key

3. OAuth Disconnect:
   → Click [Disconnect] → confirmation dialog
   → Confirm → connection removed
   → Status shows "Using: Company default"
   → Blair uses company default again

4. API Key Fallback:
   → Expand "Advanced: Use API Key Instead"
   → Existing API key form works as before
   → Can switch between OAuth and API key

5. Token Refresh:
   → Connect via OAuth
   → Wait for token expiry (or mock)
   → Next Blair chat → token auto-refreshed
   → No user intervention needed

6. Error Handling:
   → Close BrowserWindow during OAuth → graceful error
   → OAuth timeout (5 min) → clear error message
   → Provider rejects token → suggest API key fallback
   → Network error during exchange → retry-able error
```

### Acceptance Criteria

- [ ] Security review completed — no token leakage vectors
- [ ] PKCE implementation verified as S256-only
- [ ] All endpoints reviewed for auth + RBAC
- [ ] Electron handler reviewed for resource cleanup
- [ ] E2E scenarios verified for both providers
- [ ] Error scenarios verified (timeout, rejection, network)
- [ ] Backward compatibility confirmed (existing API key users unaffected)
- [ ] Phase 10 sign-off by SA + CR1 + CR2

---

## Task 10.8: Login 2FA — Backend (Email Code on Every Login)

**Goal**: After successful password authentication, send a 6-digit email verification code before issuing a JWT token. This applies to **every login**, not just first-time registration.

### Current Login Flow (to change)

1. `POST /auth/login` with email + password
2. Backend verifies credentials → returns JWT immediately

### New Login Flow

1. `POST /auth/login` with email + password
2. Backend verifies credentials → generates 6-digit code → emails it → returns `Login2FAResponse` (no JWT)
3. `POST /auth/verify-login` with email + code
4. Backend validates code → returns JWT token

### Modify: `fastapi-backend/app/schemas/user.py`

Add new schemas:

```python
class Login2FAResponse(BaseModel):
    requires_2fa: bool = True
    email: str
    message: str = "Verification code sent to your email"

class VerifyLoginRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
```

### Modify: `fastapi-backend/app/routers/auth.py`

Change login endpoint behavior:

```python
@router.post("/login", response_model=Login2FAResponse)
async def login(form_data, db):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(401, "Incorrect email or password")

    # Generate 2FA code and email it
    await generate_and_send_login_code(db, user)
    return Login2FAResponse(email=user.email)
```

Add new verify-login endpoint:

```python
@router.post("/verify-login", response_model=Token)
async def verify_login(data: VerifyLoginRequest, db):
    """Verify login 2FA code and return JWT token."""
    user = await verify_login_code(db, data.email, data.code)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    return Token(access_token=access_token)
```

### Modify: `fastapi-backend/app/services/auth_service.py`

- `authenticate_user()` — unchanged (still validates password + `email_verified` flag)
- New `generate_and_send_login_code(db, user)` — generate code, hash with SHA-256, store in `verification_code` / `verification_code_expires_at` columns, reset `verification_attempts`, send email
- New `verify_login_code(db, email, code)` — validate hashed code, check expiry, track failed attempts (clear after 5), clear code columns on success, return user

**Column reuse**: The `verification_code`, `verification_code_expires_at`, and `verification_attempts` columns on the User model are `NULL` after registration email verification completes, so they can be safely reused for login 2FA. No new migration needed.

### Modify: `fastapi-backend/app/services/email_service.py`

Add `send_login_code_email(email, code)`:

- Subject: "Your PM Desktop login code"
- Body: "Your verification code is: XXXXXX. This code expires in 15 minutes."
- **Distinct subject** from registration email ("Verify your PM Desktop email") to avoid confusion

### Acceptance Criteria

- [ ] Login endpoint returns `Login2FAResponse` (not JWT) on valid credentials
- [ ] 6-digit code generated and emailed on every successful login attempt
- [ ] Code hashed with SHA-256 before storage (reuse `_hash_code()`)
- [ ] Code expires after `EMAIL_VERIFICATION_CODE_EXPIRY_MINUTES` (configurable, default 15)
- [ ] 5 failed code attempts clears code (brute-force protection, reuse existing pattern)
- [ ] `POST /auth/verify-login` returns JWT token on valid code
- [ ] Email not verified (registration) still returns 403 **before** 2FA code is sent
- [ ] Invalid credentials still return 401 (no code sent, no email)
- [ ] Login 2FA email has distinct subject from registration verification email
- [ ] Calling login again with valid credentials regenerates and resends a new code
- [ ] No new migration required (reuses existing verification columns)

---

## Task 10.9: Login 2FA — Frontend Changes

### Modify: `electron-app/src/renderer/contexts/auth-context.tsx`

Update `login()` function to handle 2FA response:

```typescript
// Current: response.status === 200 → extract JWT → LOGIN_SUCCESS
// New: response.status === 200 → check requires_2fa → set pendingVerificationEmail

if (response.status === 200) {
  const data = response.data
  if ('requires_2fa' in data && data.requires_2fa) {
    // 2FA required — redirect to verification page
    dispatch({ type: 'SET_PENDING_VERIFICATION', payload: credentials.email })
    dispatch({ type: 'SET_LOADING', payload: false })
    return false
  }
}
```

Add `verifyLogin()` action:

```typescript
const verifyLogin = useCallback(async (email: string, code: string): Promise<boolean> => {
  // POST /auth/verify-login with { email, code }
  // On 200: extract JWT → LOGIN_SUCCESS → fetch user profile
  // On error: parse and display error
}, [])
```

Update `AuthActions` interface and `AuthActionsContext` to include `verifyLogin`.

### Modify: `electron-app/src/renderer/hooks/use-auth.ts`

Expose `verifyLogin` in `UseAuthReturn` interface and hook return.

### Modify: `electron-app/src/renderer/pages/verify-email.tsx`

Add context-aware messaging:

```typescript
interface VerifyEmailPageProps {
  email: string
  context?: 'registration' | 'login'  // NEW — defaults to 'login'
  onNavigateToLogin: () => void
}

// Registration: "Verify your email address"
// Login 2FA:    "Enter your login code"
//
// Registration: "We sent a verification code to verify your email."
// Login 2FA:    "We sent a verification code to complete your login."
//
// Resend button:
//   Registration: calls POST /auth/resend-verification
//   Login 2FA:    calls POST /auth/login again (regenerates code)
```

### Modify: `electron-app/src/renderer/App.tsx`

Pass `context` prop to `VerifyEmailPage`. Track whether the pending verification originated from login (2FA) or registration:

- Login 2FA: `pendingVerificationEmail` set from login 200 response
- Registration: `pendingVerificationEmail` set from register 201 response

Add state to distinguish (e.g., `pendingVerificationContext: 'registration' | 'login'`).

### Acceptance Criteria

- [ ] Login with valid credentials shows verification code page (not dashboard)
- [ ] Verification page shows "Enter your login code" for login 2FA context
- [ ] Verification page shows "Verify your email" for registration context
- [ ] Entering correct code logs user in (JWT received, dashboard shown)
- [ ] Entering wrong code shows error with remaining attempts feedback
- [ ] Resend button for login 2FA calls login again to regenerate code
- [ ] Resend button for registration calls `/auth/resend-verification`
- [ ] 403 (registration email not verified) still works as before
- [ ] Error states (expired code, too many attempts, network error) shown clearly
- [ ] Back to login link clears pending state and returns to login form
