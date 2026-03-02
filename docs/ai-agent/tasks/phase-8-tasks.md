# ~~Phase 8: Query Expansion~~ — REMOVED

**Created**: 2026-02-25
**Last updated**: 2026-02-26
**Status**: REMOVED
**Spec**: ~~[phase-8-query-expansion.md](../phase-8-query-expansion.md)~~

> **STATUS: REMOVED** — Phase 8 was eliminated entirely. The Phase 4 LangGraph agent naturally handles
> query expansion through its reasoning capabilities (rephrasing queries, making multiple tool calls).
> Phase 2's 3-source hybrid search already provides strong recall — semantic embeddings handle synonyms
> implicitly, and pg_trgm handles typos. The marginal benefit of a separate LLM expansion step did not
> justify the added latency, cost, and complexity (~91 tasks).

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

## Task Summary

| Section | Description | Tasks |
|---------|-------------|-------|
| 8.1 | Pydantic Schemas | 8 |
| 8.2 | QueryExpansionService Core | 10 |
| 8.3 | LLM Expansion Prompt + JSON Parsing | 12 |
| ~~8.4~~ | ~~Graph-Aware Expansion~~ | ~~10~~ — REMOVED |
| 8.5 | Redis Caching for LLM Expansions | 8 |
| ~~8.6~~ | ~~KnowledgeGraphService — `get_neighbor_entity_ids()`~~ | ~~10~~ — REMOVED |
| ~~8.7~~ | ~~Enhanced `_entity_search()` with Graph Traversal~~ | ~~10~~ — REMOVED |
| 8.8 | Retrieval Integration — Expanded Semantic Search | 9 |
| 8.9 | Retrieval Integration — Expanded Keyword Search | 7 |
| 8.10 | Retrieval Integration — `retrieve()` Orchestration | 8 |
| 8.11 | Code Reviews | 6 |
| 8.12 | Security Analysis | 5 |
| 8.13 | Unit Tests — Query Expansion Service | 10 |
| ~~8.14~~ | ~~Unit Tests — Enhanced Entity Search~~ | ~~10~~ — REMOVED |
| 8.15 | Verification & Sign-Off | 8 |
| **TOTAL** | | **~91** (was 140; 30 graph tasks + 19 adjusted = ~49 removed) |

---

### 8.1 Pydantic Schemas

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.1.1 | Create file `app/schemas/query_expansion.py` with module docstring | BE | [ ] | |
| 8.1.2 | Define `ExpandedQuery` model with `original` (str, required), `llm_terms` (list[str], default=[]), `all_terms` (list[str], default=[]), `cache_hit` (bool, default=False) | BE | [ ] | `graph_terms` removed (Phase 3→3.1) |
| 8.1.3 | Add Field descriptions to all `ExpandedQuery` fields | BE | [ ] | |
| 8.1.4 | Define `ExpansionConfig` model with `enable_llm_expansion` (bool, default=True) | BE | [ ] | `enable_graph_expansion` removed (Phase 3→3.1) |
| 8.1.5 | Add `max_llm_terms` (int, default=4, ge=1, le=10) to `ExpansionConfig` | BE | [ ] | `max_graph_terms` removed (Phase 3→3.1) |
| 8.1.6 | Add `max_total_terms` (int, default=6, ge=2, le=12), `cache_ttl_seconds` (int, default=86400) to `ExpansionConfig` | BE | [ ] | |
| 8.1.7 | Verify `ExpandedQuery` validates with all-empty optional fields | QE | [ ] | |
| 8.1.8 | Verify `ExpansionConfig` rejects `max_total_terms < 2` | QE | [ ] | |

---

### 8.2 QueryExpansionService Core

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.2.1 | Create file `app/ai/query_expansion_service.py` with module docstring | BE | [ ] | |
| 8.2.2 | Define `QueryExpansionService` class with constructor accepting `provider_registry`, `redis_service` (nullable), `db`, `config` (nullable with default) | BE | [ ] | `kg_service` removed (Phase 3→3.1) |
| 8.2.3 | Implement `expand()` method signature: `async def expand(self, query: str) -> ExpandedQuery` | BE | [ ] | `accessible_app_ids` removed (no graph) |
| 8.2.4 | In `expand()`, call `_llm_expand()` | BE | [ ] | Was parallel with `_graph_expand()`; graph removed |
| 8.2.5 | In `expand()`, handle LLM expansion failure gracefully (log + continue with original only) | BE | [ ] | |
| 8.2.6 | In `expand()`, call `_deduplicate_terms()` to build `all_terms` | BE | [ ] | |
| 8.2.7 | Implement `_cache_key()` static method: `qe:{sha256(query.lower().strip())}` | BE | [ ] | |
| 8.2.8 | Implement `_deduplicate_terms()` static method: case-insensitive dedup, original first, capped at `max_total` | BE | [ ] | |
| 8.2.9 | Verify `expand()` returns `ExpandedQuery` with `original` always in `all_terms[0]` | QE | [ ] | |
| 8.2.10 | Verify empty query returns `ExpandedQuery` with only original term | QE | [ ] | |

---

### 8.3 LLM Expansion Prompt + JSON Parsing

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.3.1 | Define `EXPANSION_PROMPT` template constant with `{query}` and `{max_terms}` placeholders | BE | [ ] | |
| 8.3.2 | Prompt instructs LLM to return JSON array of 1-4 word terms, excluding original query | BE | [ ] | |
| 8.3.3 | Prompt requests synonyms, alternate phrasings, abbreviations, and closely related concepts | BE | [ ] | |
| 8.3.4 | Implement `_llm_expand()`: check Redis cache first | BE | [ ] | |
| 8.3.5 | Implement `_llm_expand()`: on cache miss, call `provider_registry.get_chat_provider()` + `provider.chat()` | BE | [ ] | |
| 8.3.6 | Use `temperature=0.3`, `max_tokens=200` for near-deterministic output | BE | [ ] | |
| 8.3.7 | Implement `_llm_expand()`: parse response with `_parse_expansion_json()` | BE | [ ] | |
| 8.3.8 | Implement `_llm_expand()`: cache parsed terms in Redis with TTL | BE | [ ] | |
| 8.3.9 | Define `_parse_expansion_json()` module-level function (follows `_parse_llm_json` pattern from sql_generator.py) | BE | [ ] | Pattern: strip code fences, find array, remove trailing commas, json.loads |
| 8.3.10 | `_parse_expansion_json()` handles: clean JSON, code fences, trailing commas, extra text, garbage | BE | [ ] | |
| 8.3.11 | `_llm_expand()` returns `[]` if `config.enable_llm_expansion is False` | BE | [ ] | |
| 8.3.12 | `_llm_expand()` returns `[]` on any exception (LLM failure, parse failure) | BE | [ ] | |

---

### ~~8.4 Graph-Aware Expansion~~ — REMOVED (Phase 3 → 3.1)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.4.1 | ~~Implement `_graph_expand()` method~~ | BE | [-] | REMOVED — Knowledge graph replaced by Phase 3.1 |
| 8.4.2 | ~~Early return if graph disabled~~ | BE | [-] | REMOVED |
| 8.4.3 | ~~Search entities via kg_service~~ | BE | [-] | REMOVED |
| 8.4.4 | ~~Collect entity aliases~~ | BE | [-] | REMOVED |
| 8.4.5 | ~~Get 1-hop neighbor entity IDs~~ | BE | [-] | REMOVED |
| 8.4.6 | ~~Load neighbor entity names~~ | BE | [-] | REMOVED |
| 8.4.7 | ~~Exclude already-matched entities~~ | BE | [-] | REMOVED |
| 8.4.8 | ~~Combine aliases + neighbor names~~ | BE | [-] | REMOVED |
| 8.4.9 | ~~Entity search failure handling~~ | BE | [-] | REMOVED |
| 8.4.10 | ~~Neighbor lookup failure handling~~ | BE | [-] | REMOVED |

---

### 8.5 Redis Caching for LLM Expansions

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.5.1 | Cache key format: `qe:{sha256(query.lower().strip())}` | BE | [ ] | |
| 8.5.2 | Cache value format: JSON `{"terms": ["term1", "term2", ...]}` | BE | [ ] | |
| 8.5.3 | Cache TTL: `config.cache_ttl_seconds` (default 86400 = 24h) | BE | [ ] | |
| 8.5.4 | On cache hit: return cached terms without calling LLM, set `cache_hit=True` on `ExpandedQuery` | BE | [ ] | |
| 8.5.5 | On cache miss: call LLM, store result in Redis | BE | [ ] | |
| 8.5.6 | Redis read failure → log debug, proceed to LLM call | BE | [ ] | |
| 8.5.7 | Redis write failure → log debug, return terms anyway | BE | [ ] | |
| 8.5.8 | Redis service is None → skip all cache operations, always call LLM | BE | [ ] | |

---

### ~~8.6 KnowledgeGraphService — `get_neighbor_entity_ids()`~~ — REMOVED (Phase 3 → 3.1)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.6.1 | ~~Add `get_neighbor_entity_ids()` to KnowledgeGraphService~~ | BE | [-] | REMOVED — KG service deleted |
| 8.6.2 | ~~Method signature~~ | BE | [-] | REMOVED |
| 8.6.3 | ~~Empty input handling~~ | BE | [-] | REMOVED |
| 8.6.4 | ~~Depth cap~~ | BE | [-] | REMOVED |
| 8.6.5 | ~~Recursive CTE~~ | BE | [-] | REMOVED |
| 8.6.6 | ~~Bidirectional relationships~~ | BE | [-] | REMOVED |
| 8.6.7 | ~~Cycle prevention~~ | BE | [-] | REMOVED |
| 8.6.8 | ~~RBAC at every hop~~ | BE | [-] | REMOVED |
| 8.6.9 | ~~Exclude starting entities~~ | BE | [-] | REMOVED |
| 8.6.10 | ~~Limit 50 results~~ | BE | [-] | REMOVED |

---

### ~~8.7 Enhanced `_entity_search()` with Graph Traversal~~ — REMOVED (Phase 3 → 3.1)

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.7.1 | ~~Call get_neighbor_entity_ids() after entity search~~ | BE | [-] | REMOVED — `_entity_search()` removed from retrieval |
| 8.7.2 | ~~Reduced score for neighbors~~ | BE | [-] | REMOVED |
| 8.7.3 | ~~Combine entity IDs~~ | BE | [-] | REMOVED |
| 8.7.4 | ~~Batch EntityMentions query~~ | BE | [-] | REMOVED |
| 8.7.5 | ~~RBAC scope filter~~ | BE | [-] | REMOVED |
| 8.7.6 | ~~Dedup by document_id~~ | BE | [-] | REMOVED |
| 8.7.7 | ~~Neighbor failure handling~~ | BE | [-] | REMOVED |
| 8.7.8 | ~~No-neighbors fallback~~ | BE | [-] | REMOVED |
| 8.7.9 | ~~Verify limit~~ | QE | [-] | REMOVED |
| 8.7.10 | ~~Verify source="entity"~~ | QE | [-] | REMOVED |

---

### 8.8 Retrieval Integration — Expanded Semantic Search

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.8.1 | Add `_expanded_semantic_search()` method to `HybridRetrievalService` | BE | [ ] | |
| 8.8.2 | Method signature: `async def _expanded_semantic_search(self, terms: list[str], scope_ids: dict, limit: int = 20) -> list[_RankedResult]` | BE | [ ] | |
| 8.8.3 | For each term, generate embedding via `provider_registry.get_embedding_provider()` + `normalizer.normalize()` | BE | [ ] | |
| 8.8.4 | Run pgvector searches in parallel via `asyncio.gather()` | BE | [ ] | |
| 8.8.5 | Union results across all terms | BE | [ ] | |
| 8.8.6 | Dedup by `(document_id, chunk_index)` — keep highest `raw_score` | BE | [ ] | |
| 8.8.7 | Re-rank deduped results by raw_score, assign sequential ranks | BE | [ ] | |
| 8.8.8 | Cap total results at `limit` | BE | [ ] | |
| 8.8.9 | If all embeddings fail → return `[]` (graceful degradation) | BE | [ ] | |

---

### 8.9 Retrieval Integration — Expanded Keyword Search

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.9.1 | Add `_expanded_keyword_search()` method to `HybridRetrievalService` | BE | [ ] | |
| 8.9.2 | Method signature: `async def _expanded_keyword_search(self, terms: list[str], scope_ids: dict, limit: int = 20) -> list[_RankedResult]` | BE | [ ] | |
| 8.9.3 | Combine all terms into single query string: `" ".join(terms)` (Meilisearch treats spaces as OR) | BE | [ ] | |
| 8.9.4 | Call existing Meilisearch search with combined query | BE | [ ] | |
| 8.9.5 | Apply RBAC scope filter (same as existing `_keyword_search()`) | BE | [ ] | |
| 8.9.6 | Return `_RankedResult` list with `source="keyword"` | BE | [ ] | |
| 8.9.7 | Empty terms list → fall back to original `_keyword_search()` behavior | BE | [ ] | |

---

### 8.10 Retrieval Integration — `retrieve()` Orchestration

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.10.1 | Add `expansion_service` (nullable) to `HybridRetrievalService.__init__()` | BE | [ ] | |
| 8.10.2 | In `retrieve()`, call `expansion_service.expand()` after RBAC resolution, before search | BE | [ ] | |
| 8.10.3 | ~~Pass `accessible_app_ids` to `expand()` for graph expansion RBAC~~ | BE | [-] | REMOVED — no graph expansion, no RBAC needed for LLM expansion |
| 8.10.4 | Expansion failure → log warning, proceed with `expanded = None` | BE | [ ] | |
| 8.10.5 | Build `semantic_terms` from `expanded.all_terms[:4]` (or `[query]` if no expansion) | BE | [ ] | |
| 8.10.6 | Build `keyword_terms` from `expanded.all_terms` (or `[query]` if no expansion) | BE | [ ] | |
| 8.10.7 | Replace `_semantic_search(query, ...)` call with `_expanded_semantic_search(semantic_terms, ...)` | BE | [ ] | |
| 8.10.8 | Replace `_keyword_search(query, ...)` call with `_expanded_keyword_search(keyword_terms, ...)` | BE | [ ] | |

---

### 8.11 Code Reviews

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.11.1 | CR1: Review `app/schemas/query_expansion.py` — Pydantic field types, validators, defaults | CR1 | [ ] | |
| 8.11.2 | ~~CR1: Review `get_neighbor_entity_ids()` — SQL correctness, CTE structure~~ | CR1 | [-] | REMOVED — KG service deleted |
| 8.11.3 | CR2: Review `query_expansion_service.py` — async patterns, error handling, DI | CR2 | [ ] | |
| 8.11.4 | CR2: Review `_expanded_semantic_search()` — asyncio.gather usage, dedup logic | CR2 | [ ] | |
| 8.11.5 | CR2: Review `_expanded_keyword_search()` — Meilisearch query construction | CR2 | [ ] | |
| 8.11.6 | ~~CR2: Review `_entity_search()` enhancements~~ | CR2 | [-] | REMOVED — `_entity_search()` deleted |
| 8.11.7 | DA: Challenge expansion term count limits — are 4 LLM + 4 graph + 6 total appropriate? | DA | [ ] | |
| 8.11.8 | DA: Challenge Redis caching strategy — 24h TTL appropriate? Should graph be cached with user-scoped keys? | DA | [ ] | |

---

### 8.12 Security Analysis

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.12.1 | SA: Verify LLM prompt does not leak internal system information in expansion request | SA | [ ] | |
| 8.12.2 | SA: Verify expanded terms are sanitized before use in SQL queries (parameterized, not interpolated) | SA | [ ] | |
| 8.12.3 | SA: Verify expanded terms are sanitized before use in Meilisearch query | SA | [ ] | |
| 8.12.4 | ~~SA: Verify RBAC enforcement in `get_neighbor_entity_ids()`~~ | SA | [-] | REMOVED — KG service deleted |
| 8.12.5 | ~~SA: Verify RBAC enforcement in `_graph_expand()`~~ | SA | [-] | REMOVED — graph expansion deleted |
| 8.12.6 | SA: Verify Redis cache key cannot be exploited for cross-user data leakage (LLM cache is query-scoped, not user-scoped — confirm this is acceptable since LLM world knowledge is user-independent) | SA | [ ] | |
| 8.12.7 | SA: Verify `_parse_expansion_json()` cannot execute arbitrary code (no `eval`, no `exec`) | SA | [ ] | |
| 8.12.8 | ~~SA: Verify graph expansion RBAC~~ | SA | [-] | REMOVED — graph expansion deleted |

---

### 8.13 Unit Tests — Query Expansion Service

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.13.1 | Create file `tests/test_query_expansion.py` with imports and test fixtures | TE | [ ] | |
| 8.13.2 | `TestExpandedQuerySchema`: test defaults, config defaults, config validation (3 tests) | TE | [ ] | |
| 8.13.3 | `TestCacheKey`: test deterministic, case-insensitive, strips whitespace (3 tests) | TE | [ ] | |
| 8.13.4 | `TestParseExpansionJson`: test clean JSON, code fences, trailing comma, extra text, garbage (5 tests) | TE | [ ] | |
| 8.13.5 | `TestDeduplicateTerms`: test original first, case-insensitive dedup, max total, empty expansions (4 tests) | TE | [ ] | |
| 8.13.6 | `TestLlmExpansion`: test returns terms, cache hit, cache miss stores, failure, disabled (5 tests) | TE | [ ] | |
| 8.13.7 | ~~`TestGraphExpansion`: test graph aliases+neighbors~~ | TE | [-] | REMOVED — graph expansion deleted |
| 8.13.8 | `TestExpandIntegration`: test LLM terms, LLM fails, LLM disabled (3 tests) | TE | [ ] | Was 4 tests; graph scenarios removed |
| 8.13.9 | All tests use `AsyncMock` for `ProviderRegistry`, `RedisService`, `AsyncSession` | TE | [ ] | `KnowledgeGraphService` mock removed |
| 8.13.10 | All async tests decorated with `@pytest.mark.asyncio` | TE | [ ] | |
| 8.13.11 | Verify all 23 tests pass with `pytest tests/test_query_expansion.py -v` | QE | [ ] | Was 28; 5 graph tests removed |
| 8.13.12 | Verify no real LLM, Redis, or database calls in unit tests | QE | [ ] | |

---

### ~~8.14 Unit Tests — Enhanced Entity Search~~ — REMOVED (Phase 3 → 3.1)

> Entity search (`_entity_search()`) was removed from `HybridRetrievalService`. Tests 8.14.8-8.14.10
> (expanded semantic/keyword search and retrieve integration) are covered in 8.13 and 8.15 instead.

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.14.1 | ~~Create test_enhanced_entity_search.py~~ | TE | [-] | REMOVED — no entity search |
| 8.14.2 | ~~TestGetNeighborEntityIds~~ | TE | [-] | REMOVED |
| 8.14.3 | ~~TestEnhancedEntitySearch~~ | TE | [-] | REMOVED |
| 8.14.4 | ~~Dedup test~~ | TE | [-] | REMOVED |
| 8.14.5 | ~~KG service mocks~~ | TE | [-] | REMOVED |
| 8.14.6 | ~~Async decorators~~ | TE | [-] | REMOVED |
| 8.14.7 | ~~Verify tests pass~~ | QE | [-] | REMOVED |
| 8.14.8 | ~~Test expanded semantic search~~ | TE | [-] | Moved to 8.13/8.15 |
| 8.14.9 | ~~Test expanded keyword search~~ | TE | [-] | Moved to 8.13/8.15 |
| 8.14.10 | ~~Test retrieve integration~~ | TE | [-] | Moved to 8.15 |

---

### 8.15 Verification & Sign-Off

| # | Task | Owner | Status | Notes |
|---|------|-------|--------|-------|
| 8.15.1 | Verify `QueryExpansionService` class exists with all documented methods | QE | [ ] | |
| 8.15.2 | Verify `ExpandedQuery` and `ExpansionConfig` schemas validate correctly | QE | [ ] | |
| 8.15.3 | ~~Verify `get_neighbor_entity_ids()` CTE~~ | QE | [-] | REMOVED — KG service deleted |
| 8.15.4 | ~~Verify enhanced `_entity_search()` includes neighbor mentions~~ | QE | [-] | REMOVED — entity search deleted |
| 8.15.5 | Verify `retrieve()` uses expanded terms for semantic and keyword search | QE | [ ] | |
| 8.15.6 | Verify graceful degradation: no LLM → works, no Redis → works | QE | [ ] | KG check removed |
| 8.15.7 | Run `ruff check app/ai/query_expansion_service.py app/schemas/query_expansion.py` — zero warnings | QE | [ ] | |
| 8.15.8 | Run full test suite `pytest tests/ -v` — no regressions | QE | [ ] | |
| 8.15.9 | Verify no new dependencies added to `requirements.txt` | QE | [ ] | |
| 8.15.10 | Final sign-off: all 17 verification checklist items in spec are checked | QE | [ ] | Was 25; 8 graph items removed |

---

## Cross-Phase Dependencies

| Dependency | Phase | Item | Status | Notes |
|------------|-------|------|--------|-------|
| `ProviderRegistry.get_chat_provider()` | Phase 1 | LLM chat provider | Required | LLM expansion calls this |
| `ProviderRegistry.get_embedding_provider()` | Phase 1 | Embedding provider | Required | Expanded semantic search calls this |
| `RedisService.get_json()` / `set()` | Existing | Redis caching | Optional | LLM expansion cache (graceful if absent) |
| `EmbeddingNormalizer` | Phase 2 | Dimension normalization | Required | Expanded semantic search normalizes embeddings |
| `HybridRetrievalService` | Phase 2 | Retrieval service (3 sources) | Modified | Phase 8 adds expansion before search |

> **Removed dependencies** (Phase 3 → 3.1): `KnowledgeGraphService`, `EntityMention` model, `_entity_search()`, `traverse_graph()` CTE pattern

---

## Task Count Summary

| Role | Active | Removed | Original |
|------|--------|---------|----------|
| BE   | ~55    | ~33     | 88       |
| TE   | ~12    | ~8      | 20       |
| QE   | ~10    | ~6      | 16       |
| CR1  | 1      | 1       | 2        |
| CR2  | 3      | 1       | 4        |
| SA   | 5      | 3       | 8        |
| DA   | 2      | —       | 2        |
| **Total** | **~88** | **~52** | **140** |

> ~52 tasks removed when graph expansion (sections 8.4, 8.6, 8.7, 8.14) was stripped.
