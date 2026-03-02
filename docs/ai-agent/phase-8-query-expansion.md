# ~~Phase 8: Query Expansion~~ — REMOVED

> **STATUS: REMOVED** — Phase 8 was eliminated entirely. The Phase 4 LangGraph agent naturally handles
> query expansion through its reasoning capabilities (rephrasing queries, making multiple tool calls).
> Phase 2's 3-source hybrid search (pgvector semantic + Meilisearch keyword + pg_trgm fuzzy) already
> provides strong recall — semantic embeddings handle synonyms implicitly, and pg_trgm handles typos.
> The marginal benefit of a separate LLM expansion step did not justify the added latency, cost, and
> complexity (~91 tasks). Previously depended on Phase 2; previously blocked Phase 4 (soft dependency).

~~**Goal**: Pre-retrieval query expansion that broadens search using LLM world knowledge (synonyms, related terms, alternate phrasings), with Redis caching for performance.~~

~~**Depends on**: Phase 2 (hybrid retrieval infrastructure)~~
~~**Blocks**: Phase 4 (agent tools benefit from expanded retrieval, but not strictly required)~~
~~**No new dependencies**: Uses existing `openai`/`anthropic` (LLM), `redis` (caching)~~

---

## Design Decision: Standalone QueryExpansionService

Three options were considered for where to place expansion logic:

| Option | Description | Verdict |
|--------|-------------|---------|
| A. Inline in `retrieve()` | Add expansion logic directly into `HybridRetrievalService.retrieve()` | Rejected — bloats retrieve, hard to test, couples expansion to retrieval |
| B. Middleware / decorator | Wrap `retrieve()` with expansion preprocessing | Rejected — awkward for async, can't easily inspect intermediate state |
| **C. Standalone service** | `QueryExpansionService` called by `retrieve()` before search | **Chosen** — reusable by agent tools, independently testable, optional (graceful degradation) |

### Why Query Expansion?

The retrieval pipeline currently searches with the **exact user query**. If a user asks about "hashbrown", the system won't find documents about "potato" unless they literally contain "hashbrown". Query expansion solves this through LLM world knowledge:

1. **LLM expansion** (world knowledge): Ask the LLM to generate synonyms, related terms, and alternate phrasings — `"hashbrown" → ["potato", "hash brown", "breakfast food"]`

> **Note**: Graph expansion (project knowledge via entity aliases and 1-hop neighbors) was removed when
> Phase 3 was replaced by Phase 3.1. The Phase 4 agent can perform structural lookups via SQL queries.

### Expansion Sources

| Source | Knowledge Type | Cached? | Reason |
|--------|---------------|---------|--------|
| Original query | User intent | N/A | Always included, never modified |
| LLM expansion | World knowledge (synonyms, abbreviations, related concepts) | Yes — Redis 24h TTL | Same query → same expansion (deterministic-ish); saves LLM cost |

### How Expanded Terms Are Used

| Search Source | Expansion Strategy | Rationale |
|---------------|-------------------|-----------|
| **Semantic search** | Embed each expanded term separately, union results (cap at 4 terms total) | Different embeddings capture different semantic neighborhoods |
| **Keyword search** | Combine all terms into single Meilisearch query (OR semantics) | Meilisearch handles OR natively; single query is more efficient |
| **Fuzzy search** | Original query only (unchanged) | Fuzzy already handles typos/abbreviations; expanding would add noise |

### Graceful Degradation

The expansion service is fully optional. If any component is unavailable:

| Scenario | Behavior |
|----------|----------|
| No LLM configured | Skip LLM expansion, use original query only |
| Redis unavailable | LLM expansion still works (just uncached) |
| LLM expansion fails | Fall through to original query only (existing behavior) |

---

## Data Flow

```
User query: "hashbrown"
        │
        v
┌──────────────────────────────┐
│   QueryExpansionService      │
│                              │
│  1. Normalize query          │
│  2. Check Redis cache ──────────── HIT → return cached LLM terms
│  3. LLM expansion ──────────────── "potato", "hash brown", "breakfast"
│  4. Cache in Redis (24h TTL) │
│  5. Merge & deduplicate      │
│  6. Cap at max_terms (6)     │
└──────────────────────────────┘
        │
        v
ExpandedQuery {
    original: "hashbrown",
    llm_terms: ["potato", "hash brown", "breakfast"],
    all_terms: ["hashbrown", "potato", "hash brown", "breakfast"]
}
        │
        v
┌──────────────────────────────┐
│   HybridRetrievalService     │
│                              │
│  Semantic: embed top 4 terms │
│    separately → union        │
│  Keyword: all terms as       │
│    single Meilisearch query  │
│  Fuzzy: original only        │
│                              │
│  → RRF merge (k=60)         │
│  → Deduplicate by doc_id    │
│  → Return top N             │
└──────────────────────────────┘
```

---

## Task 8.1: Pydantic Schemas

### New File: `fastapi-backend/app/schemas/query_expansion.py`

```python
"""Schemas for query expansion results."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExpandedQuery(BaseModel):
    """Result of query expansion — original query plus expanded terms."""

    original: str = Field(..., description="Original user query (always included)")
    llm_terms: list[str] = Field(
        default_factory=list,
        description="Terms from LLM world knowledge expansion",
    )
    all_terms: list[str] = Field(
        default_factory=list,
        description="Deduplicated union of original + llm_terms",
    )
    cache_hit: bool = Field(
        default=False,
        description="Whether the LLM expansion came from Redis cache",
    )


class ExpansionConfig(BaseModel):
    """Configuration for query expansion behavior."""

    enable_llm_expansion: bool = Field(default=True, description="Use LLM for synonym/related term expansion")
    max_llm_terms: int = Field(default=4, ge=1, le=10, description="Max terms from LLM expansion")
    max_total_terms: int = Field(default=6, ge=2, le=12, description="Max total expanded terms (including original)")
    cache_ttl_seconds: int = Field(default=86400, description="Redis cache TTL for LLM expansions (default 24h)")
```

### Acceptance Criteria
- [ ] `ExpandedQuery` schema validates correctly with all fields
- [ ] `ExpansionConfig` has sensible defaults that work without configuration
- [ ] `all_terms` always contains the original query as the first element
- [ ] `max_total_terms` lower bound is 2 (original + at least 1 expansion)

---

## Task 8.2: QueryExpansionService Core

### New File: `fastapi-backend/app/ai/query_expansion_service.py`

```python
"""Query expansion service for broadening search queries.

Expands user queries using LLM world knowledge (synonyms, related terms,
alternate phrasings). Results are cached in Redis for performance.
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.query_expansion import ExpandedQuery, ExpansionConfig
from ..services.redis_service import RedisService
from .provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class QueryExpansionService:
    """Expands search queries using LLM world knowledge.

    Args:
        provider_registry: For LLM chat calls.
        redis_service: For caching LLM expansions.
        db: Async database session.
        config: Optional expansion configuration overrides.
    """

    def __init__(
        self,
        provider_registry: ProviderRegistry,
        redis_service: RedisService | None,
        db: AsyncSession,
        config: ExpansionConfig | None = None,
    ) -> None:
        self.provider_registry = provider_registry
        self.redis_service = redis_service
        self.db = db
        self.config = config or ExpansionConfig()

    async def expand(
        self,
        query: str,
    ) -> ExpandedQuery:
        """Expand a query using LLM world knowledge.

        Args:
            query: Original user query string.

        Returns:
            ExpandedQuery with original, llm_terms, and all_terms.
        """
        ...

    async def _llm_expand(self, query: str) -> list[str]:
        """Get expanded terms from LLM (with Redis cache)."""
        ...

    @staticmethod
    def _cache_key(query: str) -> str:
        """Generate Redis cache key from normalized query.

        Key format: `qe:{sha256_of_lowered_stripped_query}`
        """
        normalized = query.lower().strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"qe:{digest}"

    @staticmethod
    def _deduplicate_terms(
        original: str,
        llm_terms: list[str],
        max_total: int,
    ) -> list[str]:
        """Merge and deduplicate terms, original always first.

        Deduplication is case-insensitive. Order: original → LLM.
        """
        ...
```

### Acceptance Criteria
- [ ] Constructor accepts all dependencies with reasonable defaults
- [ ] `expand()` returns `ExpandedQuery` with original always present
- [ ] `_cache_key()` is deterministic for same normalized query
- [ ] `_deduplicate_terms()` preserves order: original → LLM
- [ ] Deduplication is case-insensitive
- [ ] Total terms capped at `config.max_total_terms`

---

## Task 8.3: LLM Expansion Prompt + JSON Parsing

### Method: `QueryExpansionService._llm_expand()`

```python
EXPANSION_PROMPT = """Given the search query below, generate a list of related \
search terms that would help find relevant documents. Include:
- Synonyms and alternate phrasings
- Common abbreviations or expanded forms
- Closely related concepts (not tangential)

IMPORTANT:
- Do NOT include the original query in your list
- Return ONLY a JSON array of strings, nothing else
- Return at most {max_terms} terms
- Each term should be 1-4 words

Query: "{query}"

JSON array:"""

async def _llm_expand(self, query: str) -> list[str]:
    """Get expanded terms from LLM, with Redis caching.

    1. Check Redis cache for existing expansion
    2. If miss, call LLM with structured prompt
    3. Parse JSON array from response
    4. Cache result in Redis with TTL
    5. Return list of expanded terms

    Returns:
        List of expanded term strings (max config.max_llm_terms).
    """
    if not self.config.enable_llm_expansion:
        return []

    cache_key = self._cache_key(query)

    # Step 1: Check cache
    if self.redis_service is not None:
        try:
            cached = await self.redis_service.get_json(cache_key)
            if cached is not None and isinstance(cached.get("terms"), list):
                return cached["terms"][:self.config.max_llm_terms]
        except Exception:
            logger.debug("Redis cache read failed for query expansion")

    # Step 2: LLM call
    try:
        provider, model_id = await self.provider_registry.get_chat_provider(self.db)
        prompt = EXPANSION_PROMPT.format(
            query=query,
            max_terms=self.config.max_llm_terms,
        )
        response = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            model_id=model_id,
            max_tokens=200,
            temperature=0.3,
        )
    except Exception as e:
        logger.warning("LLM expansion failed: %s", type(e).__name__)
        return []

    # Step 3: Parse JSON
    terms = _parse_expansion_json(response)
    terms = terms[:self.config.max_llm_terms]

    # Step 4: Cache
    if self.redis_service is not None and terms:
        try:
            await self.redis_service.set(
                cache_key,
                json.dumps({"terms": terms}),
                ttl=self.config.cache_ttl_seconds,
            )
        except Exception:
            logger.debug("Redis cache write failed for query expansion")

    return terms


def _parse_expansion_json(raw: str) -> list[str]:
    """Parse LLM response into list of expansion terms.

    Handles common LLM quirks: markdown code fences, trailing commas,
    extra explanation text around the JSON.

    Args:
        raw: Raw LLM response string.

    Returns:
        List of term strings, or empty list on parse failure.
    """
    import re
    text = raw.strip()
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    # Find JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    text = match.group(0)
    # Remove trailing commas before ] or }
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if isinstance(t, str) and t.strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return []
```

### Acceptance Criteria
- [ ] LLM prompt generates relevant terms without the original query
- [ ] JSON parsing handles code fences, trailing commas, and extra text
- [ ] Redis cache hit skips LLM call entirely
- [ ] Redis cache miss stores result for future calls
- [ ] LLM failure returns empty list (graceful degradation)
- [ ] Redis failure doesn't prevent LLM call
- [ ] Temperature 0.3 for mostly-deterministic output

### Edge Cases
- Query is a single character → LLM may return empty; that's OK
- LLM returns non-JSON → `_parse_expansion_json` returns `[]`
- LLM returns terms identical to original → deduplicated later in `_deduplicate_terms`
- Redis TTL expires → next call re-generates (expected behavior)

---

## ~~Task 8.4: Graph-Aware Expansion~~ — REMOVED

> **REMOVED**: Graph expansion was removed when Phase 3 (Knowledge Graph) was replaced by Phase 3.1 (Agent SQL Access).
> The Phase 4 agent can perform structural lookups via SQL queries against scoped views instead.

---

## Task 8.5: Redis Caching for LLM Expansions

### Cache Design

| Aspect | Value |
|--------|-------|
| Key format | `qe:{sha256(normalized_query)}` |
| Normalization | `query.lower().strip()` |
| Value format | JSON: `{"terms": ["term1", "term2", ...]}` |
| TTL | 24 hours (86400 seconds), configurable via `ExpansionConfig.cache_ttl_seconds` |
| Eviction | Redis native TTL expiry |

### Why Cache LLM Expansions?

- Same query → same expansion (temperature 0.3 is near-deterministic). Saves ~500ms and LLM cost per cache hit.

### Acceptance Criteria
- [ ] Cache key is SHA256 of normalized (lowered, stripped) query
- [ ] Cache stores JSON with `{"terms": [...]}` format
- [ ] TTL is configurable, defaults to 24h
- [ ] Cache miss triggers LLM call and stores result
- [ ] Cache hit returns stored terms without LLM call
- [ ] Redis unavailable → LLM still works (uncached)
- [ ] No cache key collisions for different queries

---

## ~~Task 8.6: New `get_neighbor_entity_ids()` on KnowledgeGraphService~~ — REMOVED

> **REMOVED**: Knowledge graph service was removed when Phase 3 was replaced by Phase 3.1 (Agent SQL Access).

---

## ~~Task 8.7: Enhanced `_entity_search()` with Graph Traversal~~ — REMOVED

> **REMOVED**: Entity search (`_entity_search()`) was removed from `HybridRetrievalService` when Phase 3 was replaced
> by Phase 3.1. Retrieval uses 3 sources: semantic + keyword + fuzzy. The Phase 4 agent performs structural lookups
> via SQL queries against scoped views.

---

## Task 8.8: Integration into `HybridRetrievalService.retrieve()`

### Modified File: `fastapi-backend/app/ai/retrieval_service.py`

The `retrieve()` method gains a query expansion step before the parallel search phase.

```python
class HybridRetrievalService:
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        normalizer: EmbeddingNormalizer,
        db: AsyncSession,
        expansion_service: QueryExpansionService | None = None,  # NEW
    ) -> None:
        self.provider_registry = provider_registry
        self.normalizer = normalizer
        self.db = db
        self.expansion_service = expansion_service  # NEW

    async def retrieve(
        self,
        query: str,
        user_id: UUID,
        limit: int = 10,
        application_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> list[RetrievalResult]:
        """Main retrieval with query expansion.

        1. Resolve RBAC scope
        2. Expand query (NEW — LLM world knowledge)
        3. Run searches in parallel:
           - Semantic: embed top N expanded terms separately, union
           - Keyword: all expanded terms as single query
           - Fuzzy: original query only
        4. RRF merge
        5. Dedup and sort
        """
        # ... (existing RBAC resolution) ...

        # Step 2: Query expansion (NEW)
        expanded = None
        if self.expansion_service is not None:
            try:
                expanded = await self.expansion_service.expand(
                    query=query,
                )
            except Exception as e:
                logger.warning("Query expansion failed: %s", type(e).__name__)

        # Step 3: Run searches with expanded terms
        semantic_terms = (
            expanded.all_terms[:4] if expanded and len(expanded.all_terms) > 1
            else [query]
        )
        keyword_terms = (
            expanded.all_terms if expanded and len(expanded.all_terms) > 1
            else [query]
        )

        semantic_task = self._expanded_semantic_search(semantic_terms, scope_ids, limit=20)
        keyword_task = self._expanded_keyword_search(keyword_terms, scope_ids, limit=20)
        fuzzy_task = self._fuzzy_title_search(query, scope_ids, limit=10)  # original only
        # ... (rest follows existing pattern) ...
```

### New Methods

```python
async def _expanded_semantic_search(
    self,
    terms: list[str],
    scope_ids: dict,
    limit: int = 20,
) -> list[_RankedResult]:
    """Semantic search with multiple expanded terms.

    Embeds each term separately, runs pgvector search for each,
    and unions the results. Deduplicates by (document_id, chunk_index),
    keeping the highest raw_score.

    Args:
        terms: List of search terms (original + expanded).
        scope_ids: RBAC scope.
        limit: Maximum results per term (total may exceed, deduped after).

    Returns:
        List of _RankedResult with source="semantic".
    """
    ...


async def _expanded_keyword_search(
    self,
    terms: list[str],
    scope_ids: dict,
    limit: int = 20,
) -> list[_RankedResult]:
    """Keyword search with expanded terms.

    Combines all terms into a single Meilisearch query string
    (space-separated, Meilisearch treats as OR).

    Args:
        terms: List of search terms.
        scope_ids: RBAC scope.
        limit: Maximum results.

    Returns:
        List of _RankedResult with source="keyword".
    """
    ...
```

### Acceptance Criteria
- [ ] `expansion_service` is optional in constructor (None = no expansion)
- [ ] Expansion failure doesn't break retrieval (falls back to original query)
- [ ] Semantic search embeds up to 4 terms separately, unions results
- [ ] Keyword search combines all terms into single query
- [ ] Fuzzy search uses original query only (unchanged)
- [ ] Existing `_semantic_search` and `_keyword_search` still work for backward compatibility
- [ ] No performance regression when expansion_service is None

### Performance Notes
- Semantic search with 4 terms = 4 embedding API calls + 4 pgvector queries. Runs in parallel via `asyncio.gather`.
- Keyword search: single Meilisearch call (no additional cost).
- Total added latency when expansion enabled: ~500ms (LLM call) on cache miss, ~0ms on cache hit.

---

## Task 8.9: Tests

### New File: `fastapi-backend/tests/test_query_expansion.py`

28 test cases organized by class:

#### `TestExpandedQuerySchema` (3 tests)
| # | Test | Asserts |
|---|------|---------|
| 1 | `test_expanded_query_defaults` | Default `ExpandedQuery` has empty lists and `cache_hit=False` |
| 2 | `test_expansion_config_defaults` | Default `ExpansionConfig` has sensible values (4, 4, 6, 86400) |
| 3 | `test_expansion_config_validation` | `max_total_terms` rejects value < 2 |

#### `TestCacheKey` (3 tests)
| # | Test | Asserts |
|---|------|---------|
| 4 | `test_cache_key_deterministic` | Same query → same key |
| 5 | `test_cache_key_case_insensitive` | "Hello" and "hello" → same key |
| 6 | `test_cache_key_strips_whitespace` | "  hello  " and "hello" → same key |

#### `TestParseExpansionJson` (5 tests)
| # | Test | Asserts |
|---|------|---------|
| 7 | `test_parse_clean_json` | `'["a","b"]'` → `["a", "b"]` |
| 8 | `test_parse_with_code_fences` | `` ```json\n["a"]\n``` `` → `["a"]` |
| 9 | `test_parse_with_trailing_comma` | `'["a","b",]'` → `["a", "b"]` |
| 10 | `test_parse_with_extra_text` | `'Here are terms: ["a"]'` → `["a"]` |
| 11 | `test_parse_garbage` | `'not json at all'` → `[]` |

#### `TestDeduplicateTerms` (4 tests)
| # | Test | Asserts |
|---|------|---------|
| 12 | `test_original_always_first` | Original query is always `all_terms[0]` |
| 13 | `test_case_insensitive_dedup` | "Potato" from LLM + "potato" from graph → kept once |
| 14 | `test_max_total_respected` | With max_total=3, only 3 terms returned |
| 15 | `test_empty_expansions` | No LLM terms + no graph terms → `[original]` only |

#### `TestLlmExpansion` (5 tests)
| # | Test | Asserts |
|---|------|---------|
| 16 | `test_llm_returns_terms` | Mocked LLM returns valid JSON → terms populated |
| 17 | `test_llm_cache_hit` | Redis returns cached result → no LLM call made |
| 18 | `test_llm_cache_miss_stores` | Redis miss → LLM called → result stored in Redis |
| 19 | `test_llm_failure_returns_empty` | LLM raises → returns `[]` |
| 20 | `test_llm_disabled` | `enable_llm_expansion=False` → returns `[]`, no LLM call |

#### `TestExpandIntegration` (3 tests)
| # | Test | Asserts |
|---|------|---------|
| 21 | `test_expand_with_llm_terms` | LLM → merged into `all_terms` |
| 22 | `test_expand_llm_fails` | LLM fails → `all_terms = [original]` |
| 23 | `test_expand_llm_disabled` | LLM disabled → `all_terms = [original]` |

### Acceptance Criteria
- [ ] All 23 query expansion tests pass
- [ ] Tests use `AsyncMock` for all external dependencies
- [ ] Tests are class-organized with `@pytest.mark.asyncio`
- [ ] No real LLM/Redis calls in unit tests
- [ ] Edge cases covered: empty query, LLM failure, Redis failure

---

## Verification Checklist

| # | Check | Status |
|---|-------|--------|
| 1 | `QueryExpansionService` class exists with `expand()` method | [ ] |
| 2 | `ExpandedQuery` schema validates correctly | [ ] |
| 3 | `ExpansionConfig` has documented defaults | [ ] |
| 4 | LLM prompt generates relevant terms (manual test) | [ ] |
| 5 | `_parse_expansion_json()` handles all documented quirks | [ ] |
| 6 | Redis cache key is SHA256 of normalized query | [ ] |
| 7 | Redis cache stores `{"terms": [...]}` with 24h TTL | [ ] |
| 8 | Cache hit skips LLM call (verified with mock) | [ ] |
| 9 | `retrieve()` calls expansion before search | [ ] |
| 10 | Semantic search embeds up to 4 terms separately | [ ] |
| 11 | Keyword search combines all terms into single query | [ ] |
| 12 | Fuzzy search uses original query only | [ ] |
| 13 | Expansion failure → retrieval works with original query | [ ] |
| 14 | No LLM configured → expansion works without LLM terms | [ ] |
| 15 | No Redis → LLM expansion works (uncached) | [ ] |
| 16 | All 23 unit tests pass | [ ] |
| 17 | No new dependencies added to `requirements.txt` | [ ] |
