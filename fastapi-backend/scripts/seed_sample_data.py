"""
Seed script: populate the database with rich 2-week realistic sample data.

Creates:
  - 10 users (mix of developers and regular users)
  - 3 applications with role-based memberships (owner / editor / viewer)
  - 8 projects across the 3 applications
  - 64 tasks (8 per project) — Done, In Progress, In Review, Issue, Todo,
    several overdue (due_date < today, status != Done)
  - ~50 comments spread across 25 tasks
  - 15 checklists with ~85 items (some fully done, some partial)
  - 23 knowledge folders + 30 documents (app-scope, project-scope, personal)

Usage:
    cd fastapi-backend
    python -m scripts.seed_sample_data

All UUIDs are deterministic so the script is safe to re-run (upsert-style:
it will error on duplicate key if data already exists — run against a fresh DB
or truncate tables first).
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text, update

from app.database import async_session_maker, engine
from app.models import (
    Application,
    ApplicationMember,
    Checklist,
    ChecklistItem,
    Comment,
    Document,
    DocumentFolder,
    Project,
    ProjectMember,
    ProjectTaskStatusAgg,
    Task,
    TaskStatus,
    User,
)
from app.utils.security import get_password_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid(n: int) -> uuid.UUID:
    """Deterministic UUID from a small integer — keeps re-runs idempotent."""
    return uuid.UUID(f"00000000-0000-4000-a000-{n:012d}")


# Anchor date: "two weeks ago" relative to 2026-03-05
TODAY = date(2026, 3, 5)
BASE_TS = datetime(2026, 2, 19, 9, 0, 0, tzinfo=timezone.utc)


def _ts(day: int, hour: int = 9, minute: int = 0) -> datetime:
    """Timestamp: BASE_TS + <day> days.  day=0 → 2026-02-19, day=14 → 2026-03-05."""
    return BASE_TS + timedelta(days=day, hours=hour - 9, minutes=minute)


def _due(offset: int) -> date:
    """Due date relative to TODAY.  offset<0 → overdue, offset>0 → future."""
    return TODAY + timedelta(days=offset)


def _tiptap_json(text: str) -> str:
    """Minimal serialised TipTap doc used for body_json / content_json (Text cols)."""
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }
    return json.dumps(doc)


PASSWORD = "Demo1234!"  # shared password for every demo account

# ---------------------------------------------------------------------------
# Static data tables
# ---------------------------------------------------------------------------

# ── Users (indices 0-9) ────────────────────────────────────────────────────
USERS = [
    # 0
    {"id": _uuid(1),  "email": "alice@demo.com",  "display_name": "Alice Chen",    "is_developer": True},
    # 1
    {"id": _uuid(2),  "email": "bob@demo.com",    "display_name": "Bob Martinez",  "is_developer": False},
    # 2
    {"id": _uuid(3),  "email": "carol@demo.com",  "display_name": "Carol Johnson", "is_developer": True},
    # 3
    {"id": _uuid(4),  "email": "dave@demo.com",   "display_name": "Dave Kim",      "is_developer": False},
    # 4
    {"id": _uuid(5),  "email": "eve@demo.com",    "display_name": "Eve Williams",  "is_developer": True},
    # 5
    {"id": _uuid(6),  "email": "frank@demo.com",  "display_name": "Frank Liu",     "is_developer": False},
    # 6
    {"id": _uuid(7),  "email": "grace@demo.com",  "display_name": "Grace Park",    "is_developer": True},
    # 7
    {"id": _uuid(8),  "email": "henry@demo.com",  "display_name": "Henry Brown",   "is_developer": False},
    # 8
    {"id": _uuid(9),  "email": "iris@demo.com",   "display_name": "Iris Tan",      "is_developer": True},
    # 9
    {"id": _uuid(10), "email": "jack@demo.com",   "display_name": "Jack Wilson",   "is_developer": False},
]

# ── Applications (indices 0-2) ─────────────────────────────────────────────
APPS = [
    # 0 – Alice owns
    {
        "id": _uuid(11), "name": "Acme Platform",
        "description": "Enterprise resource-planning and project-management platform",
        "owner_idx": 0, "day": 0,
    },
    # 1 – Carol owns
    {
        "id": _uuid(12), "name": "Startup Hub",
        "description": "SaaS product for startup accelerators and portfolio companies",
        "owner_idx": 2, "day": 1,
    },
    # 2 – Eve owns
    {
        "id": _uuid(13), "name": "DevOps Suite",
        "description": "Internal tooling for CI/CD, monitoring, and cloud infrastructure",
        "owner_idx": 4, "day": 2,
    },
]

# ── Application memberships  (app_idx, user_idx, role) ────────────────────
APP_MEMBERS = [
    # Acme Platform
    (0, 0, "owner"), (0, 1, "editor"), (0, 2, "editor"),
    (0, 3, "viewer"), (0, 5, "editor"), (0, 6, "editor"),
    (0, 7, "viewer"), (0, 8, "viewer"),
    # Startup Hub
    (1, 2, "owner"), (1, 0, "editor"), (1, 4, "editor"),
    (1, 5, "editor"), (1, 6, "editor"), (1, 7, "viewer"),
    (1, 1, "viewer"), (1, 9, "viewer"),
    # DevOps Suite
    (2, 4, "owner"), (2, 0, "editor"), (2, 1, "editor"),
    (2, 8, "editor"), (2, 9, "editor"), (2, 3, "viewer"),
    (2, 7, "viewer"),
]

# ── Projects (indices 0-7) ─────────────────────────────────────────────────
# Fields: id, app_idx, name, key, type, owner_idx, creator_idx, due_offset, day
PROJECTS = [
    # Acme Platform
    {"id": _uuid(21), "app_idx": 0, "name": "Backend API",      "key": "API",   "type": "kanban", "owner_idx": 0, "creator_idx": 0, "due": _due(30),  "day": 0},
    {"id": _uuid(22), "app_idx": 0, "name": "Mobile App",       "key": "MOB",   "type": "kanban", "owner_idx": 1, "creator_idx": 0, "due": _due(45),  "day": 1},
    {"id": _uuid(23), "app_idx": 0, "name": "Data Platform",    "key": "DATA",  "type": "kanban", "owner_idx": 8, "creator_idx": 0, "due": _due(60),  "day": 2},
    # Startup Hub
    {"id": _uuid(24), "app_idx": 1, "name": "Dashboard UI",     "key": "DASH",  "type": "kanban", "owner_idx": 2, "creator_idx": 2, "due": _due(25),  "day": 1},
    {"id": _uuid(25), "app_idx": 1, "name": "Analytics Engine", "key": "ANA",   "type": "kanban", "owner_idx": 4, "creator_idx": 2, "due": _due(40),  "day": 3},
    # DevOps Suite
    {"id": _uuid(26), "app_idx": 2, "name": "CI/CD Pipeline",   "key": "CICD",  "type": "kanban", "owner_idx": 4, "creator_idx": 4, "due": _due(20),  "day": 2},
    {"id": _uuid(27), "app_idx": 2, "name": "Monitoring Stack",  "key": "MON",   "type": "kanban", "owner_idx": 8, "creator_idx": 4, "due": _due(35),  "day": 3},
    {"id": _uuid(28), "app_idx": 2, "name": "Infrastructure",   "key": "INFRA", "type": "kanban", "owner_idx": 9, "creator_idx": 4, "due": _due(50),  "day": 4},
]

# ── Project memberships  (proj_idx, user_idx, role, added_by_idx) ──────────
PROJ_MEMBERS = [
    (0, 0, "admin", 0), (0, 2, "member", 0), (0, 5, "member", 0), (0, 3, "member", 0),
    (1, 1, "admin", 0), (1, 0, "member", 0), (1, 3, "member", 1), (1, 6, "member", 1),
    (2, 8, "admin", 0), (2, 5, "member", 0), (2, 0, "member", 0),
    (3, 2, "admin", 2), (3, 4, "member", 2), (3, 6, "member", 2),
    (4, 4, "admin", 2), (4, 2, "member", 2), (4, 6, "member", 2),
    (5, 4, "admin", 4), (5, 8, "member", 4), (5, 0, "member", 4),
    (6, 8, "admin", 4), (6, 4, "member", 4), (6, 9, "member", 4),
    (7, 9, "admin", 4), (7, 4, "member", 4), (7, 8, "member", 4),
]

# ── Tasks (8 per project, 64 total) ───────────────────────────────────────
# Tuple: (proj_idx, uuid, title, task_type, priority, status,
#         assignee_idx, reporter_idx, story_points, due_offset, created_day)
# due_offset is relative to TODAY (negative = overdue)
# created_day is offset from BASE_TS (2026-02-19)
TASKS = [
    # ── Backend API ──────────────────────────────────────────────────────
    (0, _uuid(101), "Set up FastAPI project structure",      "story",  "high",    "Done",        0,    0, 3,  -14, 0),
    (0, _uuid(102), "Implement JWT authentication",          "story",  "highest", "Done",        0,    1, 8,  -10, 1),
    (0, _uuid(103), "Create CRUD endpoints for projects",    "story",  "high",    "In Review",   2,    0, 5,   -3, 3),
    (0, _uuid(104), "Fix N+1 query on task listing",         "bug",    "medium",  "In Progress", 0,    3, 3,   -2, 5),
    (0, _uuid(105), "Add rate limiting middleware",          "story",  "low",     "Todo",        None, 0, 2,    5, 7),
    (0, _uuid(106), "Implement WebSocket manager",           "story",  "high",    "In Progress", 2,    0, 5,   -1, 4),
    (0, _uuid(107), "Add file upload to MinIO",              "story",  "medium",  "Todo",        5,    0, 3,    7, 8),
    (0, _uuid(108), "Write integration tests for auth",      "task",   "medium",  "Issue",       0,    0, 2,   -5, 6),

    # ── Mobile App ───────────────────────────────────────────────────────
    (1, _uuid(111), "Design onboarding flow screens",        "story",  "highest", "Done",        1,    0, 5,  -12, 1),
    (1, _uuid(112), "Implement push notifications",          "story",  "high",    "In Progress", 3,    1, 8,    2, 3),
    (1, _uuid(113), "Login screen crashes on Android 14",    "bug",    "highest", "Issue",       1,    3, 3,   -7, 2),
    (1, _uuid(114), "Offline mode data sync",                "epic",   "medium",  "Todo",        None, 1, 13,  14, 4),
    (1, _uuid(115), "Add biometric authentication",          "story",  "medium",  "Todo",        3,    0, 5,   10, 6),
    (1, _uuid(116), "Profile screen dark mode bug",          "bug",    "high",    "In Progress", 1,    3, 3,   -1, 5),
    (1, _uuid(117), "App performance audit",                 "task",   "high",    "In Review",   6,    1, 5,    2, 7),
    (1, _uuid(118), "Localization: German and French",       "story",  "low",     "Todo",        None, 1, 8,   20, 9),

    # ── Data Platform ────────────────────────────────────────────────────
    (2, _uuid(121), "Design data schema for events",         "story",  "highest", "Done",        8,    0, 5,  -13, 2),
    (2, _uuid(122), "Set up Kafka cluster",                  "epic",   "highest", "Done",        8,    0, 13,  -8, 3),
    (2, _uuid(123), "Build ETL pipeline for raw events",     "story",  "high",    "In Progress", 5,    8, 8,    3, 4),
    (2, _uuid(124), "Data retention policy jobs",            "story",  "medium",  "Todo",        None, 8, 5,    7, 7),
    (2, _uuid(125), "Dashboard aggregation queries",         "story",  "high",    "In Review",   8,    5, 5,    1, 5),
    (2, _uuid(126), "Memory leak in stream processor",       "bug",    "high",    "Issue",       5,    8, 5,   -4, 4),
    (2, _uuid(127), "Add Prometheus metrics",                "story",  "low",     "Todo",        5,    8, 3,   10, 8),
    (2, _uuid(128), "Write data dictionary",                 "task",   "low",     "Todo",        None, 8, 2,   14, 9),

    # ── Dashboard UI ─────────────────────────────────────────────────────
    (3, _uuid(131), "Build sidebar navigation component",    "story",  "high",    "Done",        2,    2, 5,  -11, 1),
    (3, _uuid(132), "Implement drag-and-drop widgets",       "story",  "high",    "In Progress", 4,    2, 8,    3, 3),
    (3, _uuid(133), "Dark mode theme support",               "story",  "medium",  "In Review",   2,    4, 5,    2, 4),
    (3, _uuid(134), "Chart tooltip misaligned in Safari",    "bug",    "low",     "Todo",        None, 4, 2,    7, 6),
    (3, _uuid(135), "Responsive layout for tablets",         "story",  "medium",  "Todo",        4,    2, 5,    8, 7),
    (3, _uuid(136), "Export to PDF feature",                 "story",  "medium",  "Todo",        None, 2, 5,   15, 8),
    (3, _uuid(137), "Keyboard shortcuts help modal",         "story",  "low",     "Done",        2,    4, 3,   -6, 2),
    (3, _uuid(138), "Performance: lazy-load chart bundles",  "story",  "high",    "In Progress", 6,    2, 5,   -1, 5),

    # ── Analytics Engine ─────────────────────────────────────────────────
    (4, _uuid(141), "Design event ingestion pipeline",       "epic",   "highest", "Done",        4,    2, 13, -14, 3),
    (4, _uuid(142), "Implement real-time aggregation",       "story",  "high",    "In Progress", 4,    2, 8,    2, 4),
    (4, _uuid(143), "Create data retention policy jobs",     "story",  "medium",  "Todo",        None, 4, 5,   10, 6),
    (4, _uuid(144), "Memory leak in stream processor",       "bug",    "high",    "Issue",       4,    2, 5,   -3, 5),
    (4, _uuid(145), "Add Prometheus metrics exporter",       "story",  "low",     "Todo",        None, 4, 3,   12, 8),
    (4, _uuid(146), "Funnel analysis feature",               "story",  "medium",  "Todo",        6,    2, 5,   18, 9),
    (4, _uuid(147), "A/B test result calculation engine",    "story",  "high",    "In Review",   4,    6, 8,    1, 6),
    (4, _uuid(148), "Cohort analysis module",                "story",  "high",    "In Progress", 6,    2, 8,   -5, 4),

    # ── CI/CD Pipeline ───────────────────────────────────────────────────
    (5, _uuid(151), "Set up GitHub Actions workflows",       "story",  "highest", "Done",        4,    4, 5,  -13, 2),
    (5, _uuid(152), "Add Docker build layer caching",        "story",  "high",    "Done",        8,    4, 3,   -9, 3),
    (5, _uuid(153), "Implement staging environment",         "story",  "high",    "In Progress", 8,    4, 8,    4, 4),
    (5, _uuid(154), "Fix flaky integration tests",           "bug",    "highest", "Issue",       8,    0, 3,   -5, 3),
    (5, _uuid(155), "Add security scanning with Snyk",       "story",  "medium",  "Todo",        None, 4, 3,    8, 7),
    (5, _uuid(156), "Blue-green deployment strategy",        "epic",   "high",    "Todo",        None, 4, 13,  20, 9),
    (5, _uuid(157), "Parallel test execution sharding",      "story",  "medium",  "In Review",   8,    0, 5,    2, 6),
    (5, _uuid(158), "Rollback procedure documentation",      "task",   "low",     "Todo",        None, 4, 2,   12, 10),

    # ── Monitoring Stack ─────────────────────────────────────────────────
    (6, _uuid(161), "Set up Grafana dashboards",             "story",  "high",    "Done",        4,    4, 5,  -10, 3),
    (6, _uuid(162), "Configure Prometheus alerting rules",   "story",  "high",    "Done",        8,    4, 5,   -7, 4),
    (6, _uuid(163), "Error rate SLO alerting",               "story",  "high",    "In Progress", 8,    4, 5,    2, 5),
    (6, _uuid(164), "SLO/SLA Grafana dashboard",             "story",  "medium",  "Todo",        None, 8, 5,   14, 8),
    (6, _uuid(165), "On-call rotation setup in PagerDuty",   "story",  "medium",  "In Review",   8,    4, 3,    3, 6),
    (6, _uuid(166), "Log aggregation with Loki",             "story",  "medium",  "Todo",        None, 4, 5,   10, 9),
    (6, _uuid(167), "Alertmanager config drift detected",    "bug",    "high",    "Issue",       8,    9, 3,   -2, 7),
    (6, _uuid(168), "Runbook for common alerts",             "task",   "low",     "Todo",        None, 8, 2,    8, 10),

    # ── Infrastructure ───────────────────────────────────────────────────
    (7, _uuid(171), "Terraform modules for VPC and subnets", "story",  "highest", "Done",        4,    4, 8,  -12, 2),
    (7, _uuid(172), "Kubernetes cluster setup (EKS)",        "epic",   "highest", "Done",        9,    4, 13,  -8, 3),
    (7, _uuid(173), "Implement HPA autoscaling",             "story",  "high",    "In Progress", 9,    4, 5,    3, 5),
    (7, _uuid(174), "Redis cluster failover configuration",  "bug",    "highest", "Issue",       9,    4, 5,   -3, 4),
    (7, _uuid(175), "Set up automated backup procedures",    "story",  "medium",  "Todo",        None, 9, 5,    7, 7),
    (7, _uuid(176), "Cloud cost optimisation audit",         "story",  "medium",  "Todo",        None, 4, 5,   15, 9),
    (7, _uuid(177), "mTLS between microservices",            "story",  "high",    "In Review",   9,    4, 8,    5, 6),
    (7, _uuid(178), "Disaster recovery runbook",             "task",   "high",    "Todo",        None, 9, 5,   18, 10),
]

# ── Comments ───────────────────────────────────────────────────────────────
# Tuple: (comment_uuid, task_uuid, author_idx, body_text, day_offset)
# day_offset → days from BASE_TS when comment was written
COMMENTS = [
    # API-3: Create CRUD endpoints (In Review)
    (_uuid(1001), _uuid(103), 0,  "Started reviewing the PR. Endpoint design looks solid — just need to verify cursor pagination handles empty results and last-page edge cases.", 5),
    (_uuid(1002), _uuid(103), 2,  "Added tests for empty cursor and last-page behaviour. Ready for another round.", 4),
    (_uuid(1003), _uuid(103), 0,  "LGTM on pagination tests. One last ask: add 422 validation error examples to the OpenAPI docs before merging.", 3),

    # API-4: Fix N+1 query (In Progress, overdue)
    (_uuid(1004), _uuid(104), 3,  "This is causing significant slowdown in staging load tests — 300ms on task list vs expected 50ms. Needs urgent attention.", 7),
    (_uuid(1005), _uuid(104), 0,  "Confirmed. Fix is to add selectinload(Task.assignee) and selectinload(Task.task_status) in the list query. Working on it now.", 6),

    # API-6: WebSocket manager (In Progress, overdue)
    (_uuid(1006), _uuid(106), 0,  "Initial impl is in feature/ws-manager. Uses Redis pub/sub channels per project. Handles reconnect with exponential backoff.", 4),
    (_uuid(1007), _uuid(106), 2,  "Looks good overall. One concern: what happens when Redis goes down mid-session? Do clients get a notification?", 3),
    (_uuid(1008), _uuid(106), 0,  "Good catch! Added graceful degradation — clients receive a connection_lost event and can fall back to polling.", 2),

    # API-8: Integration tests (Issue)
    (_uuid(1009), _uuid(108), 0,  "Tests pass locally but fail on CI. Suspect missing env var for the test database URL.", 8),
    (_uuid(1010), _uuid(108), 0,  "Found it — TEST_DATABASE_URL wasn't exported in the CI env template. Tests now pass, but teardown still leaves orphaned rows.", 7),

    # MOB-3: Android 14 crash (Issue, overdue)
    (_uuid(1011), _uuid(113), 3,  "Reproducible 100% on Pixel 7 running Android 14 QPR2. Stack trace points to BiometricPrompt callback null dereference.", 10),
    (_uuid(1012), _uuid(113), 1,  "Taking ownership. Android 14 changed the BiometricPrompt API — the old callback signature is now deprecated and throws on QPR2.", 9),
    (_uuid(1013), _uuid(113), 3,  "Any ETA? This is blocking the 2.1.0 release that was meant to ship last week.", 7),
    (_uuid(1014), _uuid(113), 1,  "Fix is ready and tested on Pixel 7 emulator. PR up for review. Will need QA sign-off on a physical device before merge.", 6),

    # MOB-6: Profile dark mode bug (In Progress, overdue)
    (_uuid(1015), _uuid(116), 3,  "Avatar background stays white in dark mode. CSS variable --avatar-bg is not connected to the theme token.", 5),
    (_uuid(1016), _uuid(116), 1,  "On it. Missing data-theme attribute propagation in the Profile component root. Simple one-liner fix.", 4),

    # MOB-7: Performance audit (In Review)
    (_uuid(1017), _uuid(117), 1,  "Initial audit: FlatList re-renders on every store update because keyExtractor returns index not id. Easy fix, big impact.", 6),
    (_uuid(1018), _uuid(117), 6,  "Also spotted a memory leak — useEffect subscription to analytics events is not cleaned up on unmount.", 5),
    (_uuid(1019), _uuid(117), 1,  "Both issues fixed in my branch. PR is up. Also added React.memo to the task card component to halve re-render count.", 4),

    # DATA-3: ETL pipeline (In Progress)
    (_uuid(1020), _uuid(123), 8,  "Using Kafka consumers with manual offset commit. Failures mid-batch can replay from last committed offset without data loss.", 5),
    (_uuid(1021), _uuid(123), 5,  "Good pattern. Cap dead-letter queue retries at 3 to avoid infinite loops. Also consider alerting on DLQ depth.", 4),

    # DATA-5: Aggregation queries (In Review)
    (_uuid(1022), _uuid(125), 8,  "Aggregation query runs in ~450ms on 10M rows. We need it under 200ms to hit the dashboard SLO.", 6),
    (_uuid(1023), _uuid(125), 5,  "Added a partial index on created_at for the last 30 days. Down to 180ms on the same dataset. PR ready.", 5),
    (_uuid(1024), _uuid(125), 8,  "Excellent. Approving the PR. Let's monitor query time in production after deploy.", 4),

    # DATA-6: Memory leak (Issue, overdue)
    (_uuid(1025), _uuid(126), 8,  "Memory grows ~2MB/min under load. Stream processor accumulates state in a HashMap for deduplication but never evicts.", 6),
    (_uuid(1026), _uuid(126), 5,  "Confirmed root cause. Implementing LRU eviction policy with 10k entry limit. Will deploy to staging tomorrow for validation.", 5),

    # DASH-2: Drag-and-drop widgets (In Progress)
    (_uuid(1027), _uuid(132), 4,  "Using @dnd-kit SortableContext. Main challenge is persisting widget order to backend efficiently on drop end.", 5),
    (_uuid(1028), _uuid(132), 2,  "Debounce the persist call — we don't want an API request on every intermediate drag position, only on drop.", 4),

    # DASH-3: Dark mode (In Review)
    (_uuid(1029), _uuid(133), 2,  "Almost done. Chart colours are the last blocker — Recharts doesn't auto-inherit CSS vars, need explicit prop passing.", 4),
    (_uuid(1030), _uuid(133), 4,  "Pass colours as props derived from a useTheme() hook. That keeps the chart decoupled from CSS specifics.", 3),

    # DASH-8: Lazy loading (In Progress, overdue)
    (_uuid(1031), _uuid(138), 6,  "Main bundle includes all Recharts components even for screens without charts. Lazy loading will cut initial load ~40%.", 6),
    (_uuid(1032), _uuid(138), 2,  "Use React.lazy + Suspense with a skeleton fallback. Make sure to test the Suspense boundary on throttled 3G.", 5),

    # ANA-4: Memory leak (Issue, overdue)
    (_uuid(1033), _uuid(144), 4,  "Profiling shows aggregation service holds event references in a HashMap for dedup — they accumulate indefinitely in long-running workers.", 5),
    (_uuid(1034), _uuid(144), 2,  "Suggest a TTL-based Bloom filter instead of HashMap. Same false-positive rate for dedup, fraction of the memory footprint.", 4),
    (_uuid(1035), _uuid(144), 4,  "Implemented TTL Bloom filter (1h TTL, 0.1% FPR). Memory growth dropped to near-zero in 4-hour load test. PR up.", 3),

    # ANA-8: Cohort analysis (In Progress, overdue)
    (_uuid(1036), _uuid(148), 2,  "Cohort query schema is designed. Building the SQL generation layer — supporting up to 5 sequential steps per cohort.", 6),
    (_uuid(1037), _uuid(148), 6,  "What is the expected response time for a cohort with 500k users and a 6-month window?", 5),
    (_uuid(1038), _uuid(148), 2,  "~2-3s cold, <500ms with incremental caching (computing daily deltas and storing them). Implementing that now.", 4),

    # CICD-4: Flaky tests (Issue, overdue)
    (_uuid(1039), _uuid(154), 8,  "Tests that hit the DB are race-conditioning when running in parallel — multiple workers share the same DB schema.", 7),
    (_uuid(1040), _uuid(154), 0,  "Using pytest-xdist with dist=each and a worker-scoped DB fixture. Each worker gets its own schema prefix. Should eliminate races.", 6),

    # CICD-7: Parallel test execution (In Review)
    (_uuid(1041), _uuid(157), 8,  "Split suite into 4 shards by file size. CI time dropped from 18 min to under 5 min. Shard config in .github/workflows/ci.yml.", 5),
    (_uuid(1042), _uuid(157), 0,  "Nice work! Confirm coverage reports from each shard are being merged — otherwise we'll report inflated coverage gaps.", 4),

    # MON-7: Alertmanager config drift (Issue, overdue)
    (_uuid(1043), _uuid(167), 9,  "Alertmanager config on staging drifted from prod — routing trees differ. Someone edited the config file manually without committing.", 8),
    (_uuid(1044), _uuid(167), 8,  "Identified the change: an inhibition rule was added for the Redis alerts but never pushed to git. Adding alertmanager config to GitOps repo and making the file read-only on all envs.", 7),

    # INFRA-4: Redis failover (Issue, overdue)
    (_uuid(1045), _uuid(174), 9,  "Redis Sentinel failover is taking 45 seconds, causing cascading connection timeouts across all services. Acceptable is under 10 seconds.", 5),
    (_uuid(1046), _uuid(174), 4,  "Increased sentinel heartbeat frequency (down-after-milliseconds from 30000 to 5000) and reduced failover-timeout. Deploying to staging.", 4),
    (_uuid(1047), _uuid(174), 9,  "Staging still showing 25s failover. Sentinel quorum requires 2/3 but one sentinel is on a high-latency node. Investigating topology.", 3),

    # INFRA-7: mTLS (In Review)
    (_uuid(1048), _uuid(177), 9,  "Using cert-manager for automatic certificate rotation (24h TTL). All service identities provisioned via SPIFFE/SPIRE.", 6),
    (_uuid(1049), _uuid(177), 4,  "Solid setup. Make sure certificate rotation doesn't cause connection drops — test with a forced rotation in staging first.", 5),
]

# ── Checklists ─────────────────────────────────────────────────────────────
# Tuple: (checklist_uuid, task_uuid, title, creator_idx, created_day, items)
# items: list of (item_uuid, content, is_done, completer_idx_or_None)
CHECKLISTS = [
    # API-2: JWT auth (Done) — fully complete
    (_uuid(401), _uuid(102), "Authentication Checklist", 0, 2, [
        (_uuid(2001), "Implement bcrypt password hashing (cost=12)",      True,  0),
        (_uuid(2002), "Create JWT access token (15min expiry)",           True,  0),
        (_uuid(2003), "Create JWT refresh token (7d expiry)",             True,  0),
        (_uuid(2004), "Add token validation middleware",                  True,  0),
        (_uuid(2005), "Write unit tests for auth service",               True,  0),
    ]),

    # API-3: CRUD endpoints (In Review) — partially done
    (_uuid(402), _uuid(103), "Endpoint Implementation", 0, 4, [
        (_uuid(2011), "Design request/response Pydantic schemas",         True,  0),
        (_uuid(2012), "Implement GET list with cursor pagination",        True,  2),
        (_uuid(2013), "Implement GET single resource",                    True,  2),
        (_uuid(2014), "Implement POST create",                            True,  2),
        (_uuid(2015), "Implement PUT update with row_version check",      False, None),
        (_uuid(2016), "Implement DELETE soft-delete",                     False, None),
        (_uuid(2017), "Add OpenAPI examples and 422 docs",                False, None),
    ]),

    # API-8: Integration tests (Issue) — barely started
    (_uuid(403), _uuid(108), "Test Coverage", 0, 7, [
        (_uuid(2021), "Write auth endpoint integration tests",            True,  0),
        (_uuid(2022), "Write project CRUD integration tests",             False, None),
        (_uuid(2023), "Write task CRUD integration tests",                False, None),
        (_uuid(2024), "Fix CI environment test database config",          False, None),
    ]),

    # MOB-3: Android 14 crash (Issue) — investigation in progress
    (_uuid(404), _uuid(113), "Bug Investigation Steps", 1, 3, [
        (_uuid(2031), "Reproduce crash on Pixel 7 emulator",              True,  1),
        (_uuid(2032), "Capture and analyse crash stack trace",            True,  3),
        (_uuid(2033), "Identify root cause in BiometricPrompt API",       True,  1),
        (_uuid(2034), "Implement fix with updated BiometricPrompt usage", False, None),
        (_uuid(2035), "Test on Android 14 QPR1, QPR2, QPR3",             False, None),
    ]),

    # MOB-7: App performance audit (In Review) — nearly done
    (_uuid(405), _uuid(117), "Performance Audit Checklist", 6, 7, [
        (_uuid(2041), "Audit FlatList keyExtractor and renderItem",       True,  6),
        (_uuid(2042), "Profile memory usage over 1-hour session",        True,  6),
        (_uuid(2043), "Fix useEffect subscription memory leak",          True,  6),
        (_uuid(2044), "Apply React.memo to task card component",         True,  1),
        (_uuid(2045), "Run Flipper profiler and document findings",       False, None),
    ]),

    # DATA-3: ETL pipeline (In Progress) — half done
    (_uuid(406), _uuid(123), "ETL Pipeline Tasks", 5, 5, [
        (_uuid(2051), "Design Kafka consumer group topology",             True,  5),
        (_uuid(2052), "Implement event schema validation layer",          True,  5),
        (_uuid(2053), "Build transformation and enrichment layer",       False, None),
        (_uuid(2054), "Set up dead-letter queue with retry cap",         False, None),
        (_uuid(2055), "Write unit tests for transformer functions",      False, None),
        (_uuid(2056), "Load test at 50k events/sec for 10 minutes",      False, None),
    ]),

    # DATA-5: Aggregation queries (In Review) — fully done
    (_uuid(407), _uuid(125), "Query Optimisation Review", 8, 6, [
        (_uuid(2061), "Identify slow queries with EXPLAIN ANALYSE",      True,  8),
        (_uuid(2062), "Add partial index on created_at (last 30 days)",  True,  5),
        (_uuid(2063), "Add composite index for common filter patterns",  True,  5),
        (_uuid(2064), "Verify query plans in staging with production data", True, 8),
    ]),

    # DASH-2: Drag-and-drop widgets (In Progress) — halfway
    (_uuid(408), _uuid(132), "Drag-Drop Implementation", 4, 4, [
        (_uuid(2071), "Research @dnd-kit SortableContext API",            True,  4),
        (_uuid(2072), "Implement draggable widget wrapper component",     True,  4),
        (_uuid(2073), "Add drop zone with visual feedback (border glow)", True,  4),
        (_uuid(2074), "Persist widget order to backend on drag-end",      False, None),
        (_uuid(2075), "Handle undo/redo for widget reorders",             False, None),
        (_uuid(2076), "Write Playwright E2E tests for drag interactions", False, None),
    ]),

    # DASH-3: Dark mode (In Review) — almost done
    (_uuid(409), _uuid(133), "Dark Mode Checklist", 2, 5, [
        (_uuid(2081), "Update CSS variables for dark colour palette",     True,  2),
        (_uuid(2082), "Apply Tailwind dark: variants across components",  True,  2),
        (_uuid(2083), "Fix Recharts colours for dark mode via useTheme",  True,  2),
        (_uuid(2084), "Test all 12 page types in dark mode",              True,  4),
        (_uuid(2085), "Validate dark mode rendering in Safari",           True,  4),
        (_uuid(2086), "Update Storybook stories with dark theme knob",    False, None),
    ]),

    # ANA-2: Real-time aggregation (In Progress) — early stage
    (_uuid(410), _uuid(142), "Aggregation Features", 4, 5, [
        (_uuid(2091), "Design windowed aggregation state model",          True,  4),
        (_uuid(2092), "Implement 1-minute sliding window aggregation",   True,  4),
        (_uuid(2093), "Implement hourly rollup job",                      False, None),
        (_uuid(2094), "Implement daily rollup job",                       False, None),
        (_uuid(2095), "Add backfill capability for historical windows",   False, None),
        (_uuid(2096), "Performance test at 1M events/hour",              False, None),
        (_uuid(2097), "Document aggregation schema and retention policy", False, None),
    ]),

    # CICD-3: Staging environment (In Progress) — good progress
    (_uuid(411), _uuid(153), "Staging Setup", 8, 5, [
        (_uuid(2101), "Provision staging Kubernetes namespace",           True,  8),
        (_uuid(2102), "Deploy all microservices to staging",              True,  8),
        (_uuid(2103), "Configure staging databases and seed test data",   True,  4),
        (_uuid(2104), "Set up staging deploy pipeline in GitHub Actions", True,  8),
        (_uuid(2105), "Smoke-test staging with production data subset",   False, None),
        (_uuid(2106), "Document staging access, URLs, and credentials",   False, None),
    ]),

    # CICD-4: Flaky tests (Issue) — just started
    (_uuid(412), _uuid(154), "Flaky Test Debug Steps", 0, 4, [
        (_uuid(2111), "Identify all flaky test cases (>1 failure in 10 runs)", True, 0),
        (_uuid(2112), "Isolate test DB schema per xdist worker",          False, None),
        (_uuid(2113), "Add retry decorator for flaky network tests",      False, None),
        (_uuid(2114), "Remove shared mutable state between test cases",   False, None),
    ]),

    # MON-5: On-call rotation (In Review) — nearly done
    (_uuid(413), _uuid(165), "On-Call Setup Checklist", 8, 7, [
        (_uuid(2121), "Create PagerDuty service for each team (3 teams)", True,  8),
        (_uuid(2122), "Configure escalation policies (5m → 15m → manager)", True, 8),
        (_uuid(2123), "Set up override and vacation schedules",            True,  8),
        (_uuid(2124), "End-to-end test: trigger alert and verify routing", True,  4),
        (_uuid(2125), "Run incident response training for all on-call members", False, None),
    ]),

    # INFRA-3: HPA autoscaling (In Progress)
    (_uuid(414), _uuid(173), "HPA Configuration", 9, 6, [
        (_uuid(2131), "Define CPU/memory resource requests and limits for all pods", True, 9),
        (_uuid(2132), "Configure HPA with CPU and custom metrics",        True,  9),
        (_uuid(2133), "Load test to validate scale-up and scale-down",    False, None),
        (_uuid(2134), "Document scaling thresholds and cooldown periods", False, None),
    ]),

    # INFRA-7: mTLS (In Review) — mostly done
    (_uuid(415), _uuid(177), "mTLS Implementation", 9, 7, [
        (_uuid(2141), "Install cert-manager in cluster",                  True,  9),
        (_uuid(2142), "Configure SPIFFE/SPIRE identity provider",         True,  9),
        (_uuid(2143), "Issue certificates for all microservices",         True,  9),
        (_uuid(2144), "Configure Istio PeerAuthentication STRICT policies", True, 9),
        (_uuid(2145), "Test inter-service mTLS connectivity end-to-end",  True,  4),
        (_uuid(2146), "Validate cert rotation causes zero connection drops", False, None),
        (_uuid(2147), "Write runbook for certificate rotation incidents",  False, None),
    ]),
]

# ── Knowledge Folders ──────────────────────────────────────────────────────
# Tuple: (uuid, name, scope_type, scope_idx, parent_uuid_or_None, creator_idx, day)
FOLDERS = [
    # Acme Platform – application scope
    (_uuid(301), "Engineering Docs",    "application", 0, None,       0, 1),
    (_uuid(302), "Team Onboarding",     "application", 0, None,       0, 2),
    (_uuid(303), "Architecture",        "application", 0, _uuid(301), 0, 2),  # child

    # Startup Hub – application scope
    (_uuid(304), "Product Strategy",    "application", 1, None,       2, 1),
    (_uuid(305), "Design System",       "application", 1, None,       2, 3),

    # DevOps Suite – application scope
    (_uuid(306), "Infrastructure Docs", "application", 2, None,       4, 2),
    (_uuid(307), "Incident Runbooks",   "application", 2, None,       4, 3),

    # Project-level folders
    (_uuid(310), "API Design",          "project",     0, None,       0, 2),  # Backend API
    (_uuid(311), "Sprint Notes",        "project",     1, None,       1, 2),  # Mobile App
    (_uuid(312), "Data Dictionary",     "project",     2, None,       8, 3),  # Data Platform
    (_uuid(313), "Component Specs",     "project",     3, None,       2, 2),  # Dashboard UI
    (_uuid(314), "Analytics Specs",     "project",     4, None,       4, 3),  # Analytics Engine
    (_uuid(315), "Pipeline Docs",       "project",     5, None,       4, 3),  # CI/CD
    (_uuid(316), "Alert Runbooks",      "project",     6, None,       8, 3),  # Monitoring
    (_uuid(317), "Terraform Modules",   "project",     7, None,       9, 3),  # Infrastructure

    # Personal folders
    (_uuid(320), "My Notes",            "user",        0, None,       0, 1),  # Alice
    (_uuid(321), "Meeting Notes",       "user",        2, None,       2, 1),  # Carol
    (_uuid(322), "DevOps Research",     "user",        4, None,       4, 2),  # Eve
    (_uuid(323), "Monitoring Notes",    "user",        8, None,       8, 3),  # Iris
]

# ── Documents ──────────────────────────────────────────────────────────────
# Tuple: (uuid, title, scope_type, scope_idx, folder_uuid_or_None, creator_idx, day, content)
DOCUMENTS = [
    # ── Acme Platform – application scope ──────────────────────────────
    (_uuid(501), "System Architecture Overview",
     "application", 0, _uuid(303), 0, 2,
     "The Acme Platform uses a microservices architecture. FastAPI handles the API gateway, "
     "PostgreSQL (with pgvector) for persistence and semantic search, Redis 7 for caching and "
     "real-time pub/sub, Meilisearch for full-text search, and MinIO for object storage. "
     "Services communicate via REST and WebSockets. All containers orchestrated on Kubernetes."),

    (_uuid(502), "Developer Onboarding Guide",
     "application", 0, _uuid(302), 0, 1,
     "Welcome to Acme Platform! This guide covers: environment setup (Docker Compose), "
     "coding conventions (Ruff for Python, ESLint for TypeScript), Git workflow (feature branches, "
     "PR review required), and how to run tests locally (pytest + npm test). "
     "Read CLAUDE.md before writing any code."),

    (_uuid(503), "Security Policy",
     "application", 0, _uuid(301), 0, 3,
     "All API endpoints require JWT authentication. Passwords hashed with bcrypt (cost=12). "
     "Rate limiting enforced at 100 req/min per user via Redis sliding window. "
     "SQL injection prevented via SQLAlchemy parameterised queries. "
     "Secrets managed in environment variables — no secrets in source code, ever."),

    (_uuid(504), "Engineering Team Charter",
     "application", 0, _uuid(301), 0, 4,
     "Values: code quality over speed (but not perfection over shipping), psychological safety, "
     "blameless postmortems, continuous improvement. "
     "Sprint ceremonies: Monday planning, Wednesday sync, Friday retro. "
     "PR review SLA: 24 hours. On-call rotation: weekly, one primary + one secondary."),

    # ── Startup Hub – application scope ────────────────────────────────
    (_uuid(511), "Q2 2026 Product Roadmap",
     "application", 1, _uuid(304), 2, 2,
     "Startup Hub Q2 goals: launch analytics dashboards v2, improve onboarding NPS from 35 to 50, "
     "reduce monthly churn from 8% to 5%. Key initiatives: real-time analytics, self-serve dashboard "
     "builder, cohort analysis, A/B testing framework. Target: 10k MAU by end of Q2."),

    (_uuid(512), "Design System Guide",
     "application", 1, _uuid(305), 6, 3,
     "Component library built on Radix UI primitives with TailwindCSS utility classes. "
     "Colour tokens, spacing scale, and typography defined in tailwind.config.ts. "
     "All components must meet WCAG 2.1 AA contrast ratios. "
     "Use Storybook for documentation — every new component needs a story."),

    (_uuid(513), "Feature Request Process",
     "application", 1, _uuid(304), 2, 5,
     "To request a feature: create a task in the relevant project with type 'story', "
     "add the tag 'feature-request', and link it to the relevant milestone in the description. "
     "Product team reviews the backlog every Monday. Prioritisation uses RICE scoring."),

    # ── DevOps Suite – application scope ───────────────────────────────
    (_uuid(521), "Infrastructure Overview",
     "application", 2, _uuid(306), 4, 2,
     "Infrastructure runs on AWS (us-east-1 primary, eu-west-1 DR). "
     "Kubernetes (EKS) for container orchestration, RDS PostgreSQL for databases, "
     "ElastiCache Redis for caching, S3 for object storage. "
     "All infrastructure managed as code via Terraform. No manual console changes in production."),

    (_uuid(522), "Incident Response Playbook",
     "application", 2, _uuid(307), 4, 3,
     "Severity: P1 (service down, all hands), P2 (degraded, on-call team), P3 (minor, next business day). "
     "For P1: page on-call, open war room in Slack #incident, update status page within 5 minutes, "
     "resolve or escalate within 30 minutes. All incidents require a blameless postmortem within 48 hours."),

    (_uuid(523), "On-Call Rotation Guidelines",
     "application", 2, _uuid(307), 8, 4,
     "On-call shifts: one week, starting Monday 09:00 UTC. Primary and secondary per rotation. "
     "Response SLA: P1 within 5 min, P2 within 30 min, P3 within next business day. "
     "Use the runbook index (see project docs) to find resolution steps for common alerts. "
     "Swap requests must be agreed 48h in advance and logged in PagerDuty."),

    # ── Backend API – project scope ─────────────────────────────────────
    (_uuid(531), "REST API Design Guidelines",
     "project", 0, _uuid(310), 0, 2,
     "All endpoints: plural resource names, HTTP verbs for actions, JSON bodies. "
     "Pagination: cursor-based using 'after' (UUID) parameter — no offset pagination. "
     "Errors: RFC 7807 Problem Details format. All timestamps in ISO 8601 UTC. "
     "Versioning: URL-based (/api/v1/). Breaking changes require a new version."),

    (_uuid(532), "Authentication Flow Sequence",
     "project", 0, _uuid(310), 0, 3,
     "Register: POST /auth/register → send email verification code (10min TTL). "
     "Login: POST /auth/login → validate password → send 2FA OTP → POST /auth/verify-login → JWT pair. "
     "Tokens: 15min access + 7d refresh. Refresh rotates the refresh token on each use. "
     "Password reset: OTP via email, 10min TTL, 3 attempt limit."),

    # ── Mobile App – project scope ──────────────────────────────────────
    (_uuid(541), "Sprint 5 Retrospective",
     "project", 1, _uuid(311), 1, 9,
     "What went well: delivered push notifications ahead of schedule, team collaboration improved. "
     "What needs improvement: Android 14 testing coverage was insufficient, PR review cycle too long (avg 3d). "
     "Action items: add Android 14 emulator to CI pipeline, establish 24h PR review SLA, "
     "run pair testing sessions weekly."),

    (_uuid(542), "Mobile Release Checklist",
     "project", 1, None, 1, 5,
     "Pre-release: full E2E test suite, verify deep links on iOS and Android, test push notifications, "
     "validate analytics events firing, review crash-free rate (target >99.5%). "
     "Post-release: monitor Sentry for 24h, check app store ratings, validate A/B test assignments. "
     "Rollback: pull release from stores within 30 min if crash-free drops below 98%."),

    # ── Data Platform – project scope ───────────────────────────────────
    (_uuid(551), "Event Schema Reference",
     "project", 2, _uuid(312), 8, 4,
     "All events are JSON with mandatory fields: event_name (string), user_id (UUID), "
     "timestamp (ISO8601 UTC), session_id (UUID). Optional: properties (dict), context.device, context.os. "
     "Max event payload: 64KB. Larger events are dropped with HTTP 413. "
     "Reserved event names: _page_view, _session_start, _session_end."),

    (_uuid(552), "Pipeline Architecture",
     "project", 2, _uuid(312), 8, 3,
     "Events flow: Client SDK → API Gateway → Redis Streams (MAXLEN ~500k) → "
     "Aggregation Workers (4x) → PostgreSQL (raw events + hourly aggregates). "
     "Target throughput: 50k events/sec sustained. Retention: raw 90 days, aggregates indefinitely. "
     "Backpressure: Redis MAXLEN trimming with approximate mode for performance."),

    # ── Dashboard UI – project scope ────────────────────────────────────
    (_uuid(561), "Component Library Index",
     "project", 3, _uuid(313), 2, 3,
     "Core components: Button (8 variants), Input, Select, Checkbox, Radio, Toggle, Modal, Drawer, "
     "Toast, DataTable (sort/filter/pagination), Chart (Line/Bar/Pie via Recharts), "
     "KanbanBoard, DragHandle. All components have Storybook stories and WCAG 2.1 AA compliance tests."),

    (_uuid(562), "UX Writing Guidelines",
     "project", 3, _uuid(313), 6, 5,
     "Use sentence case for all UI text. Action buttons: verb-first ('Save changes', not 'Changes saved'). "
     "Error messages: specific and actionable — 'Title must be at least 3 characters' not 'Invalid input'. "
     "Empty states: explain why it's empty and offer a clear next action. "
     "Loading states: show skeleton screens, not spinners, for content >200ms load time."),

    # ── Analytics Engine – project scope ────────────────────────────────
    (_uuid(571), "Metrics Glossary",
     "project", 4, _uuid(314), 4, 4,
     "DAU: distinct user_ids with any tracked event in a UTC calendar day. "
     "MAU: distinct user_ids active in a rolling 30-day window. "
     "D7 Retention: % of new users (day 0) who have any event on day 7 +/- 1 day. "
     "Conversion: % of users completing all steps of a defined funnel in order. "
     "All metrics exclude internal team user IDs (flagged in the users table)."),

    (_uuid(572), "A/B Test Framework Spec",
     "project", 4, _uuid(314), 6, 6,
     "Experiment definition: name, hypothesis, variants (control + 1-3 treatments), "
     "targeting (% split or segment filter), primary metric, guardrail metrics (must not regress). "
     "Assignment: deterministic bucketing by user_id hash — same user always in same variant. "
     "Analysis: daily Welch's t-test. Min detectable effect: 5% relative. Min sample: 1000/variant."),

    # ── CI/CD Pipeline – project scope ──────────────────────────────────
    (_uuid(581), "Pipeline Overview",
     "project", 5, _uuid(315), 4, 3,
     "GitHub Actions workflows: PR checks (lint, typecheck, unit test, build) on every PR. "
     "Main branch: auto-deploy to staging after green CI. Manual approval gate for production. "
     "Target CI time: <8 minutes. Current: 18 minutes (being fixed with 4-shard parallelism). "
     "Secrets: stored in GitHub Actions encrypted secrets, never in workflow files."),

    (_uuid(582), "Testing Strategy",
     "project", 5, _uuid(315), 8, 4,
     "Unit tests: pytest (backend, 80% coverage target), Jest (frontend, 70% target). "
     "Integration tests: pytest with testcontainers for DB and Redis. "
     "E2E tests: Playwright for frontend flows, httpx for API contracts. "
     "Parallelism: 4 shards via pytest-xdist. Flaky policy: quarantine after 3 consecutive failures."),

    # ── Monitoring Stack – project scope ────────────────────────────────
    (_uuid(591), "Alert Runbook Index",
     "project", 6, _uuid(316), 8, 5,
     "HighCPU: check pg_stat_activity for runaway queries, scale HPA if legitimate load. "
     "HighErrorRate: check Sentry for new exceptions, review recent deploys, rollback if needed. "
     "DBConnectionExhaustion: check for connection leaks, restart app pods, scale pgBouncer pool. "
     "RedisMemoryHigh: inspect large keys with SCAN + OBJECT ENCODING, review TTL policies."),

    (_uuid(592), "SLO Definitions",
     "project", 6, _uuid(316), 4, 4,
     "API availability: 99.9% over 30-day rolling window (43.8 min error budget). "
     "API p99 latency: <500ms read, <1000ms write. Error rate: <0.1% of requests → 5xx. "
     "Error budget policy: if budget <20% remaining, freeze all non-critical deploys until replenished."),

    # ── Infrastructure – project scope ──────────────────────────────────
    (_uuid(601), "Terraform Module Guide",
     "project", 7, _uuid(317), 9, 4,
     "All infrastructure in /infra/modules: vpc, eks, rds, redis, s3. "
     "Naming: {env}-{service}-{resource} (e.g. prod-api-rds). "
     "Apply flow: terraform plan → peer review in PR → apply to staging → smoke test → apply to prod. "
     "Never use terraform apply -auto-approve in production."),

    (_uuid(602), "Kubernetes Operations Runbook",
     "project", 7, _uuid(317), 4, 5,
     "Rolling restart: kubectl rollout restart deployment/{name}. "
     "Scale: kubectl scale deployment/{name} --replicas=N. "
     "Logs: kubectl logs -f deployment/{name} --tail=100. "
     "Never kubectl delete a production pod without confirming the replacement is healthy first."),

    # ── Personal notes ───────────────────────────────────────────────────
    (_uuid(611), "API Debugging Tips",
     "user", 0, _uuid(320), 0, 3,
     "httpie for quick API testing: http :8001/api/health. "
     "pgcli for interactive PostgreSQL with syntax highlighting. "
     "redis-cli MONITOR for real-time pub/sub inspection. "
     "Remember selectinload for N+1 prevention. Use EXPLAIN ANALYSE to find slow queries."),

    (_uuid(612), "Architecture Decision Notes",
     "user", 0, _uuid(320), 0, 6,
     "Decision: cursor-based pagination over offset. "
     "Reason: OFFSET N forces DB to scan and discard N rows — degrades at scale. "
     "Cursor uses an indexed column (created_at or id) for O(1) seek regardless of dataset size. "
     "Downside: cannot jump to arbitrary page — acceptable for our infinite-scroll UX."),

    (_uuid(621), "Weekly Standup Template",
     "user", 2, _uuid(321), 2, 1,
     "Yesterday: [list completed tasks with keys]. Today: [planned work]. "
     "Blockers: [anything preventing progress — tag the relevant person]. "
     "Keep updates under 2 minutes. Use task keys for reference (e.g. DASH-133)."),

    (_uuid(622), "1-on-1 Notes — Alice",
     "user", 2, _uuid(321), 2, 7,
     "Topics discussed: API team capacity, dark mode timeline, Q2 roadmap priority alignment. "
     "Action items: Alice to share updated architecture diagram by Friday. "
     "Carol to review sprint 6 goals and send feedback before Monday planning."),

    (_uuid(631), "eBPF Observability Research",
     "user", 4, _uuid(322), 4, 5,
     "eBPF captures syscall-level traces without code instrumentation. "
     "Tools to evaluate: Cilium Hubble (network flow), Pixie (full-stack profiling), BCC (custom programs). "
     "Zero overhead in production compared to traditional APM agents. "
     "POC planned for Q3 — will trial Pixie on staging cluster."),

    (_uuid(641), "Prometheus Alerting Best Practices",
     "user", 8, _uuid(323), 8, 4,
     "Always set 'for: 5m' on alerts to avoid flapping on transient spikes. "
     "AlertManager inhibition rules: P1 alerts suppress lower-severity alerts for same service. "
     "Silence durations: max 4h in business hours, 8h overnight. "
     "Label consistency: every alert must have 'severity', 'team', and 'service' labels."),
]


# ---------------------------------------------------------------------------
# Clean logic
# ---------------------------------------------------------------------------

async def clean_db() -> None:
    """Truncate all tables touched by the seed script (CASCADE handles FK order)."""
    async with async_session_maker() as session:
        # TRUNCATE Users and Applications with CASCADE wipes every child table
        # (Tasks, Projects, Comments, Checklists, Documents, Folders, Members…)
        # while leaving AI config tables (AiProvider, AiModel, etc.) intact.
        await session.execute(text('TRUNCATE "Users", "Applications" CASCADE'))
        await session.commit()
    print("  ✓ Seed tables truncated\n")


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

async def seed() -> None:
    pw_hash = get_password_hash(PASSWORD)

    async with async_session_maker() as session:

        # ── 1. Users ───────────────────────────────────────────────────
        users: list[User] = []
        for u in USERS:
            obj = User(
                id=u["id"],
                email=u["email"],
                password_hash=pw_hash,
                display_name=u["display_name"],
                email_verified=True,
                is_developer=u["is_developer"],
                created_at=_ts(0),
                updated_at=_ts(0),
            )
            session.add(obj)
            users.append(obj)
        await session.flush()
        print(f"  ✓ {len(users)} users")

        # ── 2. Applications ────────────────────────────────────────────
        apps: list[Application] = []
        for a in APPS:
            obj = Application(
                id=a["id"],
                name=a["name"],
                description=a["description"],
                owner_id=USERS[a["owner_idx"]]["id"],
                created_at=_ts(a["day"]),
                updated_at=_ts(a["day"]),
            )
            session.add(obj)
            apps.append(obj)
        await session.flush()
        print(f"  ✓ {len(apps)} applications")

        # ── 3. Application memberships ─────────────────────────────────
        for app_idx, user_idx, role in APP_MEMBERS:
            session.add(ApplicationMember(
                id=uuid.uuid4(),
                application_id=APPS[app_idx]["id"],
                user_id=USERS[user_idx]["id"],
                role=role,
                created_at=_ts(APPS[app_idx]["day"] + 1),
                updated_at=_ts(APPS[app_idx]["day"] + 1),
            ))
        await session.flush()
        print(f"  ✓ {len(APP_MEMBERS)} application memberships")

        # ── 4. Projects + default task statuses + aggregation rows ─────
        projects: list[Project] = []
        all_statuses: dict[uuid.UUID, list[TaskStatus]] = {}

        for p in PROJECTS:
            proj = Project(
                id=p["id"],
                application_id=APPS[p["app_idx"]]["id"],
                name=p["name"],
                key=p["key"],
                project_type=p["type"],
                due_date=p["due"],
                project_owner_user_id=USERS[p["owner_idx"]]["id"],
                created_by=USERS[p["creator_idx"]]["id"],
                next_task_number=1,
                row_version=1,
                created_at=_ts(p["day"]),
                updated_at=_ts(p["day"]),
            )
            session.add(proj)
            projects.append(proj)

            statuses = TaskStatus.create_default_statuses(p["id"])
            for s in statuses:
                session.add(s)
            all_statuses[p["id"]] = statuses

            session.add(ProjectTaskStatusAgg(
                project_id=p["id"],
                total_tasks=0, todo_tasks=0, active_tasks=0,
                review_tasks=0, issue_tasks=0, done_tasks=0,
                updated_at=_ts(p["day"]),
            ))

        await session.flush()
        print(f"  ✓ {len(projects)} projects (with default statuses)")

        # ── 5. Project memberships ─────────────────────────────────────
        for proj_idx, user_idx, role, added_by_idx in PROJ_MEMBERS:
            session.add(ProjectMember(
                id=uuid.uuid4(),
                project_id=PROJECTS[proj_idx]["id"],
                user_id=USERS[user_idx]["id"],
                role=role,
                added_by_user_id=USERS[added_by_idx]["id"],
                created_at=_ts(PROJECTS[proj_idx]["day"] + 1),
                updated_at=_ts(PROJECTS[proj_idx]["day"] + 1),
            ))
        await session.flush()
        print(f"  ✓ {len(PROJ_MEMBERS)} project memberships")

        # ── 6. Tasks ──────────────────────────────────────────────────
        status_lookup: dict[uuid.UUID, dict[str, uuid.UUID]] = {
            pid: {s.name: s.id for s in sts}
            for pid, sts in all_statuses.items()
        }

        task_numbers: dict[int, int] = {i: 1 for i in range(len(PROJECTS))}
        agg_counts: dict[uuid.UUID, dict[str, int]] = {
            p["id"]: {"total": 0, "todo": 0, "active": 0, "review": 0, "issue": 0, "done": 0}
            for p in PROJECTS
        }
        STATUS_AGG = {
            "Todo": "todo", "In Progress": "active", "In Review": "review",
            "Issue": "issue", "Done": "done",
        }

        for (proj_idx, t_id, title, task_type, priority, status,
             assignee_idx, reporter_idx, points, due_off, created_day) in TASKS:

            proj = PROJECTS[proj_idx]
            pid = proj["id"]
            num = task_numbers[proj_idx]
            task_numbers[proj_idx] = num + 1

            session.add(Task(
                id=t_id,
                project_id=pid,
                task_status_id=status_lookup[pid][status],
                task_key=f"{proj['key']}-{num}",
                title=title,
                task_type=task_type,
                priority=priority,
                assignee_id=USERS[assignee_idx]["id"] if assignee_idx is not None else None,
                reporter_id=USERS[reporter_idx]["id"],
                story_points=points,
                due_date=_due(due_off),
                task_rank=f"{num:05d}",
                row_version=1,
                checklist_total=0,
                checklist_done=0,
                completed_at=_ts(created_day + 2) if status == "Done" else None,
                created_at=_ts(created_day),
                updated_at=_ts(created_day),
            ))

            c = agg_counts[pid]
            c["total"] += 1
            c[STATUS_AGG[status]] += 1

        await session.flush()

        # Update aggregation rows and next_task_number
        for i, p in enumerate(PROJECTS):
            pid = p["id"]
            c = agg_counts[pid]
            await session.execute(
                update(ProjectTaskStatusAgg)
                .where(ProjectTaskStatusAgg.project_id == pid)
                .values(
                    total_tasks=c["total"], todo_tasks=c["todo"],
                    active_tasks=c["active"], review_tasks=c["review"],
                    issue_tasks=c["issue"], done_tasks=c["done"],
                    updated_at=_ts(14),
                )
            )
            await session.execute(
                update(Project).where(Project.id == pid)
                .values(next_task_number=task_numbers[i])
            )
        await session.flush()
        print(f"  ✓ {len(TASKS)} tasks")

        # ── 7. Comments ───────────────────────────────────────────────
        for c_id, task_id, author_idx, body, day in COMMENTS:
            session.add(Comment(
                id=c_id,
                task_id=task_id,
                author_id=USERS[author_idx]["id"],
                body_json=_tiptap_json(body),
                body_text=body,
                is_deleted=False,
                created_at=_ts(day),
                updated_at=_ts(day),
            ))
        await session.flush()
        print(f"  ✓ {len(COMMENTS)} comments")

        # ── 8. Checklists + items ─────────────────────────────────────
        # Track checklist totals per task for denormalised counter update
        task_cl_totals: dict[uuid.UUID, tuple[int, int]] = {}  # task_id → (total, done)

        cl_count = 0
        item_count = 0
        for (cl_id, task_id, title, creator_idx, created_day, items) in CHECKLISTS:
            total = len(items)
            done = sum(1 for _, _, is_done, _ in items if is_done)

            session.add(Checklist(
                id=cl_id,
                task_id=task_id,
                title=title,
                rank=f"{cl_count:05d}",
                total_items=total,
                completed_items=done,
                created_at=_ts(created_day),
            ))
            cl_count += 1

            for rank_i, (item_id, content, is_done, completer_idx) in enumerate(items):
                session.add(ChecklistItem(
                    id=item_id,
                    checklist_id=cl_id,
                    content=content,
                    is_done=is_done,
                    completed_by=USERS[completer_idx]["id"] if completer_idx is not None else None,
                    completed_at=_ts(created_day + 1) if is_done else None,
                    rank=f"{rank_i:05d}",
                    created_at=_ts(created_day),
                    updated_at=_ts(created_day + 1) if is_done else None,
                ))
                item_count += 1

            # Accumulate per-task checklist counters
            prev_t, prev_d = task_cl_totals.get(task_id, (0, 0))
            task_cl_totals[task_id] = (prev_t + total, prev_d + done)

        await session.flush()

        # Update Task.checklist_total / checklist_done denormalised counters
        for task_id, (total, done) in task_cl_totals.items():
            await session.execute(
                update(Task).where(Task.id == task_id)
                .values(checklist_total=total, checklist_done=done)
            )
        await session.flush()
        print(f"  ✓ {cl_count} checklists, {item_count} checklist items")

        # ── 9. Knowledge folders ───────────────────────────────────────
        for (f_id, name, scope_type, scope_idx, parent_id, creator_idx, day) in FOLDERS:
            scope_kw: dict = {}
            if scope_type == "application":
                scope_kw["application_id"] = APPS[scope_idx]["id"]
            elif scope_type == "project":
                scope_kw["project_id"] = PROJECTS[scope_idx]["id"]
            else:
                scope_kw["user_id"] = USERS[scope_idx]["id"]

            depth = 0 if parent_id is None else 1
            mat_path = (
                f"/{f_id}/" if parent_id is None
                else f"/{parent_id}/{f_id}/"
            )

            session.add(DocumentFolder(
                id=f_id,
                name=name,
                parent_id=parent_id,
                materialized_path=mat_path,
                depth=depth,
                sort_order=0,
                created_by=USERS[creator_idx]["id"],
                created_at=_ts(day),
                updated_at=_ts(day),
                **scope_kw,
            ))

        await session.flush()
        print(f"  ✓ {len(FOLDERS)} knowledge folders")

        # ── 10. Documents ─────────────────────────────────────────────
        for (d_id, title, scope_type, scope_idx, folder_id, creator_idx, day, content) in DOCUMENTS:
            scope_kw = {}
            if scope_type == "application":
                scope_kw["application_id"] = APPS[scope_idx]["id"]
            elif scope_type == "project":
                scope_kw["project_id"] = PROJECTS[scope_idx]["id"]
            else:
                scope_kw["user_id"] = USERS[scope_idx]["id"]

            session.add(Document(
                id=d_id,
                title=title,
                folder_id=folder_id,
                content_json=_tiptap_json(content),
                content_plain=content,
                content_markdown=content,
                sort_order=0,
                row_version=1,
                schema_version=1,
                embedding_status="none",
                created_by=USERS[creator_idx]["id"],
                created_at=_ts(day),
                updated_at=_ts(day),
                **scope_kw,
            ))

        await session.flush()
        print(f"  ✓ {len(DOCUMENTS)} documents")

        # ── Commit ─────────────────────────────────────────────────────
        await session.commit()
        print("\n  All changes committed.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sample data into the PM database.")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Truncate existing seed data before inserting (safe re-run).",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Truncate seed data then exit without re-seeding.",
    )
    args = parser.parse_args()

    try:
        if args.clean or args.clean_only:
            print("Cleaning existing data…")
            await clean_db()

        if args.clean_only:
            print("Done (clean only — no data inserted).")
            return

        print("Seeding sample data…\n")
        await seed()
    finally:
        await engine.dispose()

    overdue = sum(
        1 for (_, _, _, _, _, status, _, _, _, due_off, _) in TASKS
        if status != "Done" and due_off < 0
    )

    print("\n─── Summary ───────────────────────────────────────────")
    print(f"  Users             {len(USERS):>4}  (password: {PASSWORD})")
    print(f"  Applications      {len(APPS):>4}")
    print(f"  App memberships   {len(APP_MEMBERS):>4}")
    print(f"  Projects          {len(PROJECTS):>4}")
    print(f"  Project members   {len(PROJ_MEMBERS):>4}")
    print(f"  Tasks             {len(TASKS):>4}  ({overdue} overdue)")
    print(f"  Comments          {len(COMMENTS):>4}")
    print(f"  Checklists        {len(CHECKLISTS):>4}")
    print(f"  Folders           {len(FOLDERS):>4}")
    print(f"  Documents         {len(DOCUMENTS):>4}")
    print("────────────────────────────────────────────────────────")
    print()
    print("Demo accounts:")
    for u in USERS:
        print(f"  {u['email']:<22} {u['display_name']}")


if __name__ == "__main__":
    asyncio.run(main())
