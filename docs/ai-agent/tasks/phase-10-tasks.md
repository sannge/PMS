# Phase 10: OAuth Subscription Connect + Login 2FA — Task Breakdown

**Created**: 2026-02-28
**Last updated**: 2026-02-28
**Status**: NOT STARTED
**Spec**: [phase-10-oauth-subscription-connect.md](../phase-10-oauth-subscription-connect.md)

> **Depends on**: Phase 7 (user chat override UI, provider registry, AiProviders table)
> **Downstream**: None (final user-facing AI feature)

---

## Task Summary

| Section | Description | Task Count |
|---------|-------------|------------|
| 10.0 | Documentation | 5 |
| 10.1 | Database Schema — OAuth Columns | 10 |
| 10.2 | Backend OAuth — Service Implementation | 14 |
| 10.3 | Backend OAuth — Schemas | 8 |
| 10.4 | Backend OAuth — Endpoints | 12 |
| 10.5 | Provider Adapter Updates | 12 |
| 10.6 | Electron OAuth Flow | 14 |
| 10.7 | Frontend — OAuth Hook | 8 |
| 10.8 | Frontend — UI Redesign | 22 |
| 10.9 | Tests | 34 |
| 10.10 | Code Reviews & Sign-Off | 12 |
| 10.0a | Bug Fix — Wire AiToggleButton + AiSidebar into Dashboard | 7 |
| 10.0b | Bug Fix — Add Missing /ai/config/system-prompt Endpoint | 9 |
| 10.11 | Login 2FA — Backend | 12 |
| 10.12 | Login 2FA — Frontend | 10 |
| 10.13 | Login 2FA — Tests | 12 |
| **Phase 10 Total** | | **201** |

---

## Team

| Role | Abbreviation |
|------|-------------|
| Frontend Engineer | **FE** |
| Backend Engineer | **BE** |
| Database Engineer | **DBE** |
| Code Reviewer 1 | **CR1** |
| Code Reviewer 2 | **CR2** |
| Security Analyst | **SA** |
| Quality Engineer | **QE** |
| Test Engineer | **TE** |
| Devil's Advocate | **DA** |

## Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked
- `[-]` Skipped / N/A

---

## 10.0a Bug Fix — Wire AiToggleButton + AiSidebar into Dashboard

> **Blocker for**: 10.8 (Frontend UI Redesign) — OAuth settings accessed via sidebar gear icon, which requires the sidebar to be openable.

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.0a.1 | Import `AiToggleButton` from `@/components/ai` in `dashboard.tsx` | FE | [ ] | Component already exists from Phase 5 |
| 10.0a.2 | Import `AiSidebar` from `@/components/ai` in `dashboard.tsx` | FE | [ ] | Component already exists from Phase 5 |
| 10.0a.3 | Pass `extraControls={<AiToggleButton />}` to `<WindowTitleBar>` in `dashboard.tsx` — renders Blair sparkles icon between theme toggle and user menu | FE | [ ] | Line ~945 in current dashboard.tsx |
| 10.0a.4 | Render `<AiSidebar />` inside the main layout flex container in `dashboard.tsx` — adjacent to `<main>`, after the main content area | FE | [ ] | Sidebar slides in from right |
| 10.0a.5 | Verify sidebar opens/closes via toggle button, persists state in localStorage via `useAiSidebar` store | FE | [ ] | Store already implemented (use-ai-sidebar.ts) |
| 10.0a.6 | Verify gear icon inside sidebar is accessible and opens AI Settings panel (`user-chat-override.tsx`) | FE | [ ] | Prerequisite for 10.8 OAuth UI |
| 10.0a.7 | **CR1 Review**: Layout — no content shift regressions? Sidebar works alongside existing Sidebar component? No z-index conflicts with notification panel? | CR1 | [ ] | |

---

## 10.0b Bug Fix — Add Missing /ai/config/system-prompt Endpoint

> **Blocker for**: 10.8 (Frontend UI Redesign) — PersonalityTab in AI Settings throws 404 without this endpoint.

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.0b.1 | Create Alembic migration `20260228_add_ai_system_prompt.py` — `ai_system_prompts` table with `id` UUID PK, `prompt` Text NOT NULL, `updated_at` TimestampTZ | DBE | [ ] | Single-row config table, no FK |
| 10.0b.2 | Create `app/models/ai_system_prompt.py` — `AiSystemPrompt` model (id, prompt, updated_at) using `Base` from `database.py` | BE | [ ] | Same pattern as `AiProvider` |
| 10.0b.3 | Add `AiSystemPrompt` import and `__all__` entry in `app/models/__init__.py` | BE | [ ] | |
| 10.0b.4 | Add `SystemPromptResponse` and `SystemPromptUpdate` schemas to `app/schemas/ai_config.py` — `SystemPromptUpdate.prompt` has `max_length=2000` | BE | [ ] | |
| 10.0b.5 | Add `GET /system-prompt` endpoint in `app/routers/ai_config.py` — require_developer, return stored prompt or `{ "prompt": "" }` | BE | [ ] | |
| 10.0b.6 | Add `PUT /system-prompt` endpoint in `app/routers/ai_config.py` — require_developer, upsert prompt (empty string deletes row) | BE | [ ] | |
| 10.0b.7 | Modify `app/ai/agent/graph.py` `agent_node` — query `AiSystemPrompt` in existing DB session block, cache and use as override for hardcoded `SYSTEM_PROMPT` | BE | [ ] | Fallback to `SYSTEM_PROMPT` when no row |
| 10.0b.8 | Create `tests/test_system_prompt.py` — 6 tests: GET empty, PUT create, GET after PUT, PUT empty resets, >2000 chars 422, non-developer 403 | TE | [ ] | |
| 10.0b.9 | **CR1 Review**: Single-row upsert pattern correct? Cache invalidation on prompt change? Agent uses updated prompt on next invocation? | CR1 | [ ] | |

---

## 10.0 Documentation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.0.1 | Create `docs/ai-agent/phase-10-oauth-subscription-connect.md` — Phase 10 spec matching format of phase-7-admin-polish.md | BE | [ ] | |
| 10.0.2 | Create `docs/ai-agent/tasks/phase-10-tasks.md` — Granular task breakdown matching format of phase-7-tasks.md | BE | [ ] | |
| 10.0.3 | Update `docs/ai-agent/README.md` — Add Phase 10 to Table of Contents + Decisions Summary table | BE | [ ] | |
| 10.0.4 | Update `docs/ai-agent/tasks/index.md` — Add Phase 10 to Phase Summary table + Dependency Graph | BE | [ ] | |
| 10.0.5 | Update `docs/ai-agent/file-manifest.md` — Add Phase 10 new/modified files to all tables | BE | [ ] | |

---

## 10.1 Database Schema — OAuth Columns

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.1.1 | Add `auth_method` column to `AiProvider` model in `app/models/ai_provider.py` — `Column(String(20), nullable=False, default="api_key", server_default="api_key")` | BE | [ ] | Discriminator: `'api_key'` or `'oauth'` |
| 10.1.2 | Add `oauth_access_token` column — `Column(Text, nullable=True)`, Fernet-encrypted ciphertext | BE | [ ] | Reuse existing `encryption.py` |
| 10.1.3 | Add `oauth_refresh_token` column — `Column(Text, nullable=True)`, Fernet-encrypted ciphertext | BE | [ ] | |
| 10.1.4 | Add `oauth_token_expires_at` column — `Column(DateTime(timezone=True), nullable=True)` | BE | [ ] | TIMESTAMPTZ for timezone awareness |
| 10.1.5 | Add `oauth_scope` column — `Column(String(500), nullable=True)`, space-separated OAuth scopes | BE | [ ] | |
| 10.1.6 | Add `oauth_provider_user_id` column — `Column(String(255), nullable=True)`, provider's user identifier | BE | [ ] | For display only, not for auth |
| 10.1.7 | Create Alembic migration `YYYYMMDD_add_oauth_columns.py` — ADD all 6 columns + CHECK constraint on `auth_method IN ('api_key', 'oauth')` + index on `auth_method` | DBE | [ ] | Reversible: down drops all columns |
| 10.1.8 | Update `AiProviderResponse` schema to include `auth_method` field in API responses (never include tokens) | BE | [ ] | |
| 10.1.9 | **CR1 Review**: Migration safety — default `'api_key'` preserves existing rows? CHECK constraint correct? No data loss on down migration? | CR1 | [ ] | |
| 10.1.10 | **DA Challenge**: Should we support multiple simultaneous OAuth connections per user (e.g., both OpenAI and Anthropic)? Current design allows one user-scoped provider. | DA | [ ] | |

---

## 10.2 Backend OAuth — Service Implementation

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.2.1 | Add `openai_oauth_client_id: str = ""` to `Settings` in `app/config.py` | BE | [ ] | Env var: `OPENAI_OAUTH_CLIENT_ID` |
| 10.2.2 | Add `anthropic_oauth_client_id: str = ""` to `Settings` in `app/config.py` | BE | [ ] | Env var: `ANTHROPIC_OAUTH_CLIENT_ID` |
| 10.2.3 | Add `oauth_state_ttl_seconds: int = 600` to `Settings` in `app/config.py` | BE | [ ] | 10-minute state token lifetime |
| 10.2.4 | Create `app/ai/oauth_service.py` — define `OAuthService` class with `PROVIDER_CONFIG` dict (auth_url, token_url, revoke_url, scopes for OpenAI + Anthropic) | BE | [ ] | |
| 10.2.5 | Implement `generate_pkce_pair()` static method — generate `code_verifier` (43-128 chars, `[A-Za-z0-9\-._~]`) + `code_challenge` (`BASE64URL(SHA256(code_verifier))`) | BE | [ ] | Use `secrets.token_urlsafe` + `hashlib.sha256` |
| 10.2.6 | Implement `_store_state()` — generate random state token, store `{user_id, code_verifier, provider_type}` as JSON in Redis with TTL from config | BE | [ ] | Key: `oauth_state:{state}` |
| 10.2.7 | Implement `_validate_state()` — Redis GET + DELETE (atomic single-use), deserialize JSON, verify `user_id` matches caller, return `code_verifier` + `provider_type` | BE | [ ] | Return `None` if expired/invalid |
| 10.2.8 | Implement `generate_auth_url()` — construct full URL with `client_id`, `redirect_uri`, `response_type=code`, `code_challenge`, `code_challenge_method=S256`, `state`, `scope` | BE | [ ] | Use `urllib.parse.urlencode` |
| 10.2.9 | Implement `exchange_code_for_tokens()` — HTTP POST to `token_url` with `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `code_verifier`; parse JSON response | BE | [ ] | Use `httpx.AsyncClient` with 30s timeout |
| 10.2.10 | Implement `refresh_tokens()` — HTTP POST to `token_url` with `grant_type=refresh_token`, `refresh_token`, `client_id`; return new tokens | BE | [ ] | May return new refresh_token too |
| 10.2.11 | Implement `revoke_tokens()` — HTTP POST to `revoke_url` with `token`, `token_type_hint=access_token`, `client_id`; best-effort (log warning on failure, don't raise) | BE | [ ] | |
| 10.2.12 | Add `get_oauth_service()` FastAPI dependency — resolve `Redis` and `Settings` from app state, construct and return `OAuthService` | BE | [ ] | |
| 10.2.13 | **CR2 Review**: HTTP error handling — timeouts on token exchange? Retry logic? Redis key namespace collision safety? Race conditions on concurrent OAuth flows? | CR2 | [ ] | |
| 10.2.14 | **SA Review**: PKCE implementation — S256 only (no `plain` fallback)? State token entropy sufficient? Code verifier never logged? | SA | [ ] | |

---

## 10.3 Backend OAuth — Schemas

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.3.1 | Create `app/schemas/oauth.py` | BE | [ ] | |
| 10.3.2 | Define `OAuthInitiateRequest` — `provider_type: Literal["openai", "anthropic"]`, `redirect_uri: str` | BE | [ ] | Validates provider_type at schema level |
| 10.3.3 | Define `OAuthInitiateResponse` — `auth_url: str`, `state: str`, `expires_in: int = 600` | BE | [ ] | |
| 10.3.4 | Define `OAuthCallbackRequest` — `provider_type: Literal["openai", "anthropic"]`, `code: str`, `state: str`, `redirect_uri: str` | BE | [ ] | `redirect_uri` must match initiate |
| 10.3.5 | Define `OAuthTokenResponse` (internal, never returned to client) — `access_token: str`, `refresh_token: str | None`, `expires_in: int`, `scope: str | None` | BE | [ ] | Mark with docstring: "Internal only" |
| 10.3.6 | Define `OAuthConnectionStatus` — `connected: bool`, `provider_type`, `auth_method`, `provider_user_id`, `connected_at`, `token_expires_at`, `scopes: list[str]` | BE | [ ] | Never include token fields |
| 10.3.7 | Define `OAuthDisconnectResponse` — `disconnected: bool`, `fallback: str` (e.g., `"company_default"`) | BE | [ ] | |
| 10.3.8 | **CR1 Review**: Schema completeness — all fields validated? `OAuthTokenResponse` truly never serialized to API? `Literal` types match `PROVIDER_CONFIG` keys? | CR1 | [ ] | |

---

## 10.4 Backend OAuth — Endpoints

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.4.1 | Create `app/routers/ai_oauth.py` with `APIRouter(prefix="/api/ai/config/me/oauth", tags=["AI OAuth"])` | BE | [ ] | |
| 10.4.2 | Implement `POST /initiate` — call `oauth_service.generate_auth_url()`, return `OAuthInitiateResponse` with auth URL + state | BE | [ ] | Depends: `get_current_user` |
| 10.4.3 | Implement `POST /callback` — validate state via `oauth_service`, exchange code for tokens, encrypt with Fernet, store in `AiProvider` | BE | [ ] | Single DB transaction |
| 10.4.4 | Callback: create `AiProvider(auth_method='oauth', scope='user')` or update existing user-scoped provider | BE | [ ] | Upsert pattern |
| 10.4.5 | Callback: auto-create chat `AiModel` under user's OAuth provider (reuse same pattern from API key flow in Task 7.0.9) | BE | [ ] | |
| 10.4.6 | Implement `DELETE /disconnect` — call `oauth_service.revoke_tokens()` (best-effort), delete user-scoped `AiProvider` + associated `AiModel` | BE | [ ] | |
| 10.4.7 | Implement `GET /status` — query user's `AiProvider`, return `OAuthConnectionStatus` (never include token values) | BE | [ ] | |
| 10.4.8 | Mount `ai_oauth` router in `app/main.py` | BE | [ ] | |
| 10.4.9 | Register `ai_oauth_router` in `app/routers/__init__.py` | BE | [ ] | |
| 10.4.10 | Add rate limiting to `POST /initiate` — 5 requests/min per user to prevent OAuth initiation abuse | BE | [ ] | Reuse `AIRateLimiter` from Phase 7 |
| 10.4.11 | **CR2 Review**: Endpoint error handling — transaction rollback on callback failure? Race condition if user initiates two OAuth flows simultaneously? | CR2 | [ ] | |
| 10.4.12 | **SA Review**: Token never in response body? `redirect_uri` validated against allowlist? Rate limiting prevents abuse? | SA | [ ] | |

---

## 10.5 Provider Adapter Updates

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.5.1 | Create `app/ai/codex_provider.py` — `CodexProvider(ChatProviderInterface)` class | BE | [ ] | |
| 10.5.2 | Implement `CodexProvider.__init__()` — accept `access_token` and `model`; initialize `AsyncOpenAI(api_key=access_token)` | BE | [ ] | OpenAI SDK accepts OAuth tokens via `api_key` param |
| 10.5.3 | Implement `CodexProvider.chat()` — same as `OpenAiProvider.chat()`, catch `openai.AuthenticationError` and raise `ProviderAuthError` | BE | [ ] | Handle 401 (token expired/revoked) |
| 10.5.4 | Implement `CodexProvider.stream_chat()` — streaming variant with same error handling | BE | [ ] | |
| 10.5.5 | Create `app/ai/exceptions.py` — define `ProviderAuthError(provider, message, recoverable)` exception | BE | [ ] | `recoverable=True` → UI suggests API key fallback |
| 10.5.6 | Modify `provider_registry.py` `_build_adapter()` — check `provider.auth_method`; if `'oauth'` + `openai`, return `CodexProvider` with decrypted `oauth_access_token` | BE | [ ] | |
| 10.5.7 | Registry: if `auth_method='oauth'` + `anthropic`, return `AnthropicProvider` with decrypted `oauth_access_token` as `api_key` | BE | [ ] | Anthropic SDK accepts tokens as API key |
| 10.5.8 | Implement `_token_needs_refresh()` — check `oauth_token_expires_at` vs `now + 5min` buffer; return `True` if expired or near-expiry | BE | [ ] | 5-min buffer prevents mid-request expiry |
| 10.5.9 | Implement `_refresh_oauth_token()` — call `oauth_service.refresh_tokens()`, encrypt new tokens, update `AiProvider` in DB | BE | [ ] | |
| 10.5.10 | Modify `anthropic_provider.py` — catch `anthropic.AuthenticationError`, detect subscription rejection, raise `ProviderAuthError` with user-friendly message | BE | [ ] | See spec Task 10.3 for error message |
| 10.5.11 | **CR1 Review**: Adapter resolution correctness — all auth_method/provider_type combos covered? Token refresh race conditions (two concurrent requests)? | CR1 | [ ] | |
| 10.5.12 | **DA Challenge**: What if Anthropic blocks ALL third-party OAuth in the future? Should we add a feature flag to hide Anthropic OAuth option? | DA | [ ] | |

---

## 10.6 Electron OAuth Flow

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.6.1 | Create `electron-app/src/main/oauth-handler.ts` | FE | [ ] | |
| 10.6.2 | Implement `registerOAuthHandlers()` — register `ipcMain.handle('oauth:initiate')` handler | FE | [ ] | Called from main process entry point |
| 10.6.3 | Implement `createOAuthWindow()` — `BrowserWindow` with `partition: 'oauth-session'`, 600x700, `contextIsolation: true`, `nodeIntegration: false` | FE | [ ] | Isolated session prevents cookie leaks |
| 10.6.4 | Implement `startCallbackServer()` — `http.createServer()` on `localhost:0` (OS-assigned random port), parse `/oauth/callback?code=xxx&state=yyy` | FE | [ ] | |
| 10.6.5 | Callback server: extract `code` and `state` from URL query params, validate they exist | FE | [ ] | Return 400 if params missing |
| 10.6.6 | Callback server: respond with HTML page "Authorization complete. You can close this window." then resolve promise | FE | [ ] | |
| 10.6.7 | Implement `waitForCallback()` — `Promise.race([callbackReceived, windowClosed, timeout])` | FE | [ ] | |
| 10.6.8 | Timeout handler: 5-minute timeout destroys `BrowserWindow` + closes HTTP server, rejects promise with `OAuthTimeoutError` | FE | [ ] | |
| 10.6.9 | Window close handler: if user closes window before callback, reject promise with `OAuthCancelledError`, cleanup server | FE | [ ] | |
| 10.6.10 | Add `initiateOAuth(authUrl: string)` to preload `contextBridge.exposeInMainWorld('electronAPI', ...)` | FE | [ ] | |
| 10.6.11 | Add TypeScript declaration `initiateOAuth: (authUrl: string) => Promise<{ code: string; state: string }>` to `electron.d.ts` | FE | [ ] | |
| 10.6.12 | Call `registerOAuthHandlers()` from main process entry point (e.g., `main.ts` `app.whenReady()`) | FE | [ ] | |
| 10.6.13 | Security: validate callback request origin is `localhost` — reject requests from other origins | FE | [ ] | Prevent redirect hijacking |
| 10.6.14 | **CR2 Review**: Resource cleanup — all code paths destroy window + server? Timeout edge cases? IPC security (no arbitrary URL loading)? | CR2 | [ ] | |

---

## 10.7 Frontend — OAuth Hook

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.7.1 | Create `electron-app/src/renderer/hooks/use-oauth-connect.ts` | FE | [ ] | |
| 10.7.2 | Implement `useOAuthStatus()` — `useQuery` for `GET /api/ai/config/me/oauth/status`, `refetchOnWindowFocus: true` (token may expire while away) | FE | [ ] | |
| 10.7.3 | Implement `useOAuthInitiate()` — `useMutation` that: (1) `POST /initiate` to get auth URL, (2) call `window.electronAPI.initiateOAuth(authUrl)`, (3) `POST /callback` with returned code + state | FE | [ ] | Three-step orchestrated mutation |
| 10.7.4 | Implement `useOAuthDisconnect()` — `useMutation` for `DELETE /disconnect`, invalidates `oauthStatus` query | FE | [ ] | Confirmation handled by caller component |
| 10.7.5 | Handle `initiateOAuth` response — auto-POST callback to backend with code + state extracted from Electron IPC result | FE | [ ] | |
| 10.7.6 | Error handling — catch `OAuthTimeoutError` (window timeout), `OAuthCancelledError` (user closed), provider rejection, network errors | FE | [ ] | Map to user-friendly messages |
| 10.7.7 | Loading state management — expose `isConnecting: boolean` flag for UI spinner during OAuth flow | FE | [ ] | |
| 10.7.8 | Add OAuth query keys to `lib/query-client.ts` — `oauthStatus` key | FE | [ ] | Follow existing query key patterns |

---

## 10.8 Frontend — UI Redesign

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.8.1 | Redesign `user-chat-override.tsx` — replace API key form with OAuth connection cards layout | FE | [ ] | Keep backward-compat API key as fallback |
| 10.8.2 | Create `ProviderCard` sub-component — card with provider logo, name, description, action button | FE | [ ] | Reusable for OpenAI + Anthropic |
| 10.8.3 | OpenAI card — green accent, "Connect your ChatGPT Plus or Pro subscription to use GPT models", [Connect with OpenAI] button | FE | [ ] | |
| 10.8.4 | Anthropic card — amber accent, "Connect your Claude subscription", [Connect with Anthropic] button | FE | [ ] | |
| 10.8.5 | Anthropic amber warning banner — "Anthropic may block third-party apps from using subscription tokens. If connection fails, use an API key instead." | FE | [ ] | Amber/yellow background, warning icon |
| 10.8.6 | `ConnectedCard` component — show provider name, subscription type, connected date, model selector, test button, disconnect button | FE | [ ] | Displayed when OAuth connected |
| 10.8.7 | Model selector in connected state — dropdown populated from `AiModels` table filtered by connected `provider_type` + `capability='chat'` | FE | [ ] | Reuse existing model dropdown pattern |
| 10.8.8 | Test Connection button — calls `POST /api/ai/config/me/providers/{type}/test`, shows latency + success/failure | FE | [ ] | Reuse test pattern from Task 7.1b |
| 10.8.9 | Disconnect button with `AlertDialog` confirmation — "Disconnect from {provider}? You'll fall back to the company default." | FE | [ ] | Use Radix AlertDialog |
| 10.8.10 | Loading state — spinner + "Connecting to {provider}..." during OAuth flow (waiting for BrowserWindow callback) | FE | [ ] | |
| 10.8.11 | Error state — red banner with error message + retry button and/or "Use API key instead" link | FE | [ ] | |
| 10.8.12 | Collapsible "Advanced: Use API Key Instead" section — Radix Collapsible with existing API key form | FE | [ ] | Preserves backward compatibility |
| 10.8.13 | API key form (existing) inside collapsible section — same as current `user-chat-override.tsx` with radio buttons + key input | FE | [ ] | No changes to existing form logic |
| 10.8.14 | Status line at bottom — "Currently using: Your OpenAI subscription (GPT-5.2)" / "Your API key" / "Company default" | FE | [ ] | |
| 10.8.15 | Transition between disconnected → connecting → connected states — smooth state machine with no flash of wrong state | FE | [ ] | |
| 10.8.16 | Handle OAuth window closed by user — show "Connection cancelled. Try again or use an API key." info message | FE | [ ] | Not an error, informational |
| 10.8.17 | Handle OAuth timeout — show "Connection timed out. Please try again." error message | FE | [ ] | |
| 10.8.18 | Handle Anthropic rejection — show "Anthropic blocked your subscription token. Please use an API key instead." with API key section auto-expanded | FE | [ ] | Auto-expand collapsible fallback |
| 10.8.19 | Handle `ProviderAuthError` from chat — if `recoverable=true`, show toast "Your OAuth token was rejected. Reconnect or switch to API key." | FE | [ ] | Shown during Blair chat, not settings |
| 10.8.20 | Responsive layout — cards stack vertically in narrow sidebar, expand horizontally in wider panels | FE | [ ] | |
| 10.8.21 | Keyboard accessibility — all buttons, cards, and collapsible sections are focusable and operable via keyboard | FE | [ ] | WCAG 2.1 AA |
| 10.8.22 | **CR2 Review**: Component structure — state management clean? Error UX comprehensive? Transitions smooth? Radix components used correctly? | CR2 | [ ] | |

---

## 10.9 Tests

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.9.1 | `test_oauth_service.py`: `test_code_verifier_length` — verify 43-128 characters | TE | [ ] | |
| 10.9.2 | `test_oauth_service.py`: `test_code_verifier_url_safe` — verify `[A-Za-z0-9\-._~]` only | TE | [ ] | |
| 10.9.3 | `test_oauth_service.py`: `test_code_challenge_s256` — verify `BASE64URL(SHA256(code_verifier))` | TE | [ ] | |
| 10.9.4 | `test_oauth_service.py`: `test_code_challenge_no_padding` — verify no `=` padding in base64url | TE | [ ] | |
| 10.9.5 | `test_oauth_service.py`: `test_pkce_pair_unique` — verify each call generates different pair | TE | [ ] | |
| 10.9.6 | `test_oauth_service.py`: `test_state_stored_in_redis` — verify Redis SET with correct TTL | TE | [ ] | |
| 10.9.7 | `test_oauth_service.py`: `test_state_expires_after_ttl` — verify state gone after 10 min | TE | [ ] | Use fakeredis or mock time |
| 10.9.8 | `test_oauth_service.py`: `test_state_single_use` — verify GET + DELETE atomic, second read fails | TE | [ ] | |
| 10.9.9 | `test_oauth_service.py`: `test_invalid_state_fails` — verify unknown token returns `None` | TE | [ ] | |
| 10.9.10 | `test_oauth_service.py`: `test_openai_auth_url` — verify URL includes `client_id`, `code_challenge`, `S256`, `state`, scopes | TE | [ ] | |
| 10.9.11 | `test_oauth_service.py`: `test_anthropic_auth_url` — verify Anthropic URL with correct params | TE | [ ] | |
| 10.9.12 | `test_oauth_service.py`: `test_exchange_openai_success` — mock HTTP POST, verify tokens returned | TE | [ ] | Use `respx` or `httpx` mock |
| 10.9.13 | `test_oauth_service.py`: `test_exchange_anthropic_success` — mock HTTP POST, verify tokens returned | TE | [ ] | |
| 10.9.14 | `test_oauth_service.py`: `test_exchange_invalid_code` — mock 400 response, verify error raised | TE | [ ] | |
| 10.9.15 | `test_oauth_service.py`: `test_refresh_success` — mock refresh POST, verify new access token | TE | [ ] | |
| 10.9.16 | `test_oauth_service.py`: `test_refresh_revoked` — mock 401 response, verify `ProviderAuthError` | TE | [ ] | |
| 10.9.17 | `test_oauth_flow.py`: `test_initiate_returns_auth_url` — verify 200 + `auth_url` + `state` | TE | [ ] | |
| 10.9.18 | `test_oauth_flow.py`: `test_initiate_requires_auth` — verify 401 without token | TE | [ ] | |
| 10.9.19 | `test_oauth_flow.py`: `test_initiate_invalid_provider` — verify 422 for unknown `provider_type` | TE | [ ] | |
| 10.9.20 | `test_oauth_flow.py`: `test_callback_stores_encrypted_tokens` — verify Fernet ciphertext in DB, not plaintext | TE | [ ] | |
| 10.9.21 | `test_oauth_flow.py`: `test_callback_creates_oauth_provider` — verify `auth_method='oauth'` on created `AiProvider` | TE | [ ] | |
| 10.9.22 | `test_oauth_flow.py`: `test_callback_auto_creates_model` — verify `AiModel(capability='chat')` created | TE | [ ] | |
| 10.9.23 | `test_oauth_flow.py`: `test_callback_invalid_state` — verify 400 for bad state token | TE | [ ] | |
| 10.9.24 | `test_oauth_flow.py`: `test_callback_expired_state` — verify 400 for expired state | TE | [ ] | |
| 10.9.25 | `test_oauth_flow.py`: `test_callback_updates_existing` — re-connecting updates, no duplicate providers | TE | [ ] | |
| 10.9.26 | `test_oauth_flow.py`: `test_disconnect_removes_data` — verify OAuth columns cleared, provider deleted | TE | [ ] | |
| 10.9.27 | `test_oauth_flow.py`: `test_status_connected` — verify `connected=true` with provider info | TE | [ ] | |
| 10.9.28 | `test_oauth_flow.py`: `test_status_not_connected` — verify `connected=false` when no OAuth | TE | [ ] | |
| 10.9.29 | `test_oauth_flow.py`: `test_status_no_tokens_returned` — verify response never contains `access_token` or `refresh_token` | TE | [ ] | |
| 10.9.30 | `test_codex_provider.py`: `test_uses_access_token` — verify `AsyncOpenAI(api_key=access_token)` | TE | [ ] | |
| 10.9.31 | `test_codex_provider.py`: `test_chat_success` — mock OpenAI, verify `ChatResponse` | TE | [ ] | |
| 10.9.32 | `test_codex_provider.py`: `test_401_expired_token` — verify `ProviderAuthError` raised | TE | [ ] | |
| 10.9.33 | `test_codex_provider.py`: `test_registry_resolves_codex` — verify `CodexProvider` for OpenAI OAuth | TE | [ ] | |
| 10.9.34 | `test_codex_provider.py`: `test_registry_auto_refresh` — verify expired token triggers refresh before adapter build | TE | [ ] | |

---

## 10.10 Code Reviews & Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.10.1 | **SA**: PKCE implementation review — verify S256 only, no `plain` downgrade, code_verifier entropy (128 bits minimum) | SA | [ ] | |
| 10.10.2 | **SA**: Token storage review — all tokens Fernet-encrypted in DB, no plaintext anywhere (DB, logs, responses, error messages) | SA | [ ] | |
| 10.10.3 | **SA**: State parameter review — CSRF protection via Redis, TTL enforced, single-use enforced, sufficient entropy | SA | [ ] | |
| 10.10.4 | **SA**: Electron OAuth window security — session partition isolates cookies, origin validation on callback, no `nodeIntegration` | SA | [ ] | |
| 10.10.5 | **SA**: No token logging review — grep codebase for `oauth_access_token`, `oauth_refresh_token`, verify they never appear in log statements | SA | [ ] | |
| 10.10.6 | **CR1**: Database schema review — migration reversible, column defaults safe, CHECK constraint correct, no data loss | CR1 | [ ] | |
| 10.10.7 | **CR2**: OAuth service code review — error handling for all HTTP failure modes, timeout handling, Redis race conditions | CR2 | [ ] | |
| 10.10.8 | **CR2**: Electron handler code review — all code paths clean up resources (window + server), no dangling listeners | CR2 | [ ] | |
| 10.10.9 | **QE**: Manual E2E — OpenAI OAuth connect → select model → test → chat with Blair → disconnect → verify fallback | QE | [ ] | |
| 10.10.10 | **QE**: Manual E2E — Anthropic OAuth connect → verify warning banner → attempt connection → verify error/success handling | QE | [ ] | |
| 10.10.11 | **QE**: Manual E2E — API key fallback → expand advanced section → enter API key → save → verify works alongside OAuth option | QE | [ ] | |
| 10.10.12 | Phase 10 sign-off — SA + CR1 + CR2 + QE confirm all acceptance criteria met, backward compatibility verified | SA | [ ] | |
| 10.10.13 | **SA**: Login 2FA review — code hashing, brute-force lockout, no code in logs, email enumeration prevention | SA | [ ] | |
| 10.10.14 | **CR1**: Login 2FA code review — column reuse safety, response model change backward-compat, login+verify-login atomicity | CR1 | [ ] | |
| 10.10.15 | **QE**: Manual E2E — login → receive email → enter code → dashboard. Wrong code → error. Expired code → error. Resend → new code. | QE | [ ] | |

---

## 10.11 Login 2FA — Backend

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.11.1 | Add `Login2FAResponse` schema to `app/schemas/user.py` — `requires_2fa: bool = True`, `email: str`, `message: str` | BE | [ ] | Response model for login endpoint |
| 10.11.2 | Add `VerifyLoginRequest` schema to `app/schemas/user.py` — `email: EmailStr`, `code: str` (min/max length 6) | BE | [ ] | Request body for verify-login |
| 10.11.3 | Create `send_login_code_email(email, code)` in `app/services/email_service.py` — subject "Your PM Desktop login code", body with code + expiry notice | BE | [ ] | Distinct subject from registration email |
| 10.11.4 | Create `generate_and_send_login_code(db, user)` in `app/services/auth_service.py` — generate 6-digit code, hash with SHA-256, store in `verification_code` + `verification_code_expires_at`, reset `verification_attempts`, call `send_login_code_email()` | BE | [ ] | Reuses existing User columns (NULL after registration verification) |
| 10.11.5 | Create `verify_login_code(db, email, code)` in `app/services/auth_service.py` — look up user, validate hashed code, check expiry, track failed attempts (clear code after 5 failures), clear code on success, return user | BE | [ ] | Same pattern as `verify_email_code()` |
| 10.11.6 | Modify `POST /auth/login` endpoint in `app/routers/auth.py` — change `response_model` to `Login2FAResponse`, after `authenticate_user()` succeeds call `generate_and_send_login_code()`, return `Login2FAResponse` instead of `Token` | BE | [ ] | Breaking change: login no longer returns JWT directly |
| 10.11.7 | Add `POST /auth/verify-login` endpoint in `app/routers/auth.py` — accept `VerifyLoginRequest`, call `verify_login_code()`, create JWT via `create_access_token()`, return `Token` | BE | [ ] | This is now the only endpoint that returns JWT for login |
| 10.11.8 | Import `Login2FAResponse`, `VerifyLoginRequest`, `verify_login_code`, `generate_and_send_login_code` in `auth.py` router | BE | [ ] | |
| 10.11.9 | Verify `authenticate_user()` still raises 403 for `email_verified=False` **before** 2FA code generation — unverified registration users must not receive login codes | BE | [ ] | Existing check at auth_service.py:235 |
| 10.11.10 | Verify calling `POST /auth/login` again with valid credentials overwrites previous code (regenerate + resend) — acts as "resend code" mechanism | BE | [ ] | No separate resend endpoint needed |
| 10.11.11 | **CR1 Review**: Column reuse safety — `verification_code` columns guaranteed NULL after email verification? Race condition if user registers + tries login 2FA simultaneously? Response model change impact on existing clients? | CR1 | [ ] | |
| 10.11.12 | **SA Review**: Code never logged? SHA-256 hashing applied before storage? Brute-force lockout after 5 attempts? Email enumeration prevented (invalid credentials → 401, no timing leak)? | SA | [ ] | |

---

## 10.12 Login 2FA — Frontend

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.12.1 | Modify `login()` in `auth-context.tsx` — on `response.status === 200`, check for `requires_2fa` in response data; if true, dispatch `SET_PENDING_VERIFICATION` with email and a new `SET_PENDING_CONTEXT` with `'login'`, return false | FE | [ ] | Currently expects `Token` response |
| 10.12.2 | Add `pendingVerificationContext: 'registration' \| 'login' \| null` to `AuthState` interface and reducer in `auth-context.tsx` | FE | [ ] | Distinguishes login 2FA from registration verification |
| 10.12.3 | Add `SET_PENDING_CONTEXT` action to `authReducer` — stores `'registration'` or `'login'` | FE | [ ] | Cleared on `LOGOUT` and `LOGIN_SUCCESS` |
| 10.12.4 | Add `verifyLogin(email, code)` function in `auth-context.tsx` — `POST /auth/verify-login` with `{ email, code }`, on 200 extract JWT → `LOGIN_SUCCESS` dispatch → fetch user profile | FE | [ ] | Same pattern as existing `verifyEmail()` but different endpoint |
| 10.12.5 | Add `verifyLogin` to `AuthActions` interface, `AuthActionsContext`, and `useMemo` actions object in `auth-context.tsx` | FE | [ ] | |
| 10.12.6 | Expose `verifyLogin` and `pendingVerificationContext` in `use-auth.ts` `UseAuthReturn` interface and hook return | FE | [ ] | |
| 10.12.7 | Modify `verify-email.tsx` — add `context?: 'registration' \| 'login'` prop; update heading ("Enter your login code" vs "Verify your email"), description text, and resend handler (login 2FA: re-call login; registration: call resend-verification) | FE | [ ] | Resend for login = POST /auth/login again |
| 10.12.8 | Modify `verify-email.tsx` — when `context='login'`, call `verifyLogin()` instead of `verifyEmail()` on form submit | FE | [ ] | Different backend endpoint |
| 10.12.9 | Modify `App.tsx` `AuthPages` — pass `context={pendingVerificationContext ?? 'login'}` to `VerifyEmailPage`, store login credentials temporarily for resend | FE | [ ] | Need email+password to re-call login for resend |
| 10.12.10 | **CR2 Review**: State management — `pendingVerificationContext` cleared on all exit paths? Login credentials for resend stored securely (in-memory only, cleared after use)? Verify vs VerifyLogin calls routed correctly? | CR2 | [ ] | |

---

## 10.13 Login 2FA — Tests

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 10.13.1 | `test_login_2fa.py`: `test_login_returns_2fa_required` — valid credentials → 200 with `requires_2fa=True` + `email` (no JWT in response) | TE | [ ] | |
| 10.13.2 | `test_login_2fa.py`: `test_login_sends_email` — verify `send_login_code_email()` called with correct email and 6-digit code | TE | [ ] | Mock email service |
| 10.13.3 | `test_login_2fa.py`: `test_login_stores_hashed_code` — verify `verification_code` column contains SHA-256 hash (not plaintext) | TE | [ ] | |
| 10.13.4 | `test_login_2fa.py`: `test_login_invalid_credentials_no_code` — wrong password → 401, no code generated, no email sent | TE | [ ] | |
| 10.13.5 | `test_login_2fa.py`: `test_login_unverified_email_403` — `email_verified=False` → 403 before any 2FA code is sent | TE | [ ] | Registration verification still gated |
| 10.13.6 | `test_login_2fa.py`: `test_verify_login_correct_code` — `POST /auth/verify-login` with valid code → 200 with JWT `access_token` | TE | [ ] | |
| 10.13.7 | `test_login_2fa.py`: `test_verify_login_wrong_code` — invalid code → 400 "Invalid verification code" | TE | [ ] | |
| 10.13.8 | `test_login_2fa.py`: `test_verify_login_expired_code` — expired code → 400 "Verification code has expired" | TE | [ ] | |
| 10.13.9 | `test_login_2fa.py`: `test_verify_login_brute_force` — 5 wrong attempts → code cleared, "Too many failed attempts" | TE | [ ] | Same lockout pattern as registration |
| 10.13.10 | `test_login_2fa.py`: `test_verify_login_code_single_use` — code cleared after successful verification, second use fails | TE | [ ] | |
| 10.13.11 | `test_login_2fa.py`: `test_login_regenerates_code` — calling login again overwrites previous code with new one + sends new email | TE | [ ] | Acts as "resend" |
| 10.13.12 | `test_login_2fa.py`: `test_login_2fa_email_distinct_subject` — verify login email subject differs from registration email subject | TE | [ ] | Prevent user confusion |
