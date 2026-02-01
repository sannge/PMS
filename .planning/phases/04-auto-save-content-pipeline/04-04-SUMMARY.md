---
phase: 04-auto-save-content-pipeline
plan: 04
subsystem: content-pipeline
tags: [tiptap, markdown, plain-text, converter, tdd]
depends_on:
  requires: [01-03]
  provides: [content_converter.py, tiptap_json_to_markdown, tiptap_json_to_plain_text]
  affects: [09-search]
tech-stack:
  added: []
  patterns: [recursive-tree-walker, mark-wrapper-dict, graceful-degradation]
key-files:
  created:
    - fastapi-backend/app/services/content_converter.py
    - fastapi-backend/tests/test_content_converter.py
  modified:
    - fastapi-backend/app/services/document_service.py
decisions:
  - textStyle and highlight marks are presentation-only -- skipped in Markdown output
  - codeBlock with 'plaintext' or empty/null language renders bare ``` fences
  - underline renders as <u>text</u> in Markdown (HTML is valid Markdown)
  - indent and textAlign attrs are presentation-only -- skipped in all output
  - Unknown node types render children recursively (graceful degradation)
metrics:
  duration: ~4 min
  completed: 2026-02-01
  tests: 49
---

# Phase 04 Plan 04: TipTap JSON Content Converter Summary

Custom Python TipTap JSON-to-Markdown and JSON-to-plain-text converter built via TDD, wired into save_document_content pipeline so all three formats stored on every save.

## What Was Done

### Task 1: RED -- Failing Test Suite (49 test cases)
- Created `test_content_converter.py` with comprehensive helper functions for building TipTap JSON fixtures
- 49 test cases covering all node types from `editor-extensions.ts`
- Tests organized into 14 test classes by feature area
- All tests failed initially (content_converter.py did not exist)
- Commit: `5dd9bdf`

### Task 2: GREEN -- Implement Converter
- Created `content_converter.py` (~190 LOC) with two public functions:
  - `tiptap_json_to_markdown(doc)` -- recursive tree walker producing Markdown
  - `tiptap_json_to_plain_text(doc)` -- text extractor stripping all formatting
- Internal helpers: `_md_nodes`, `_md_inline`, `_md_list_item`, `_md_table`, `_extract_text_from_nodes`
- `_MARK_WRAPPERS` dict for simple mark wrapping (bold, italic, strike, code)
- Special handling: link (bracket syntax), underline (HTML tag), textStyle/highlight (skip)
- All 49 tests passing
- Fixed one test assertion for combined mark ordering (bold+italic+link)
- Commit: `679d20d`

### Task 3: Wire Into Save Pipeline
- Updated `save_document_content` in `document_service.py` to call both converters
- Replaced empty string placeholders with actual converter calls
- Updated `convert_tiptap_to_markdown` and `convert_tiptap_to_plain_text` stubs to delegate to content_converter module
- Commit: `db4d218`

## Test Coverage

49 test cases across 14 test classes:

| Area | Tests | Key Scenarios |
|------|-------|---------------|
| Empty/invalid input | 4 | None, empty dict, wrong type, empty doc |
| Paragraphs | 3 | Single, multiple, empty |
| Headings | 4 | Levels 1, 2, 3, 6 |
| Marks | 10 | bold, italic, strike, code, underline, link, textStyle skip, highlight skip, combined |
| Bullet lists | 3 | Simple, nested (2 levels), deeply nested (3 levels) |
| Ordered lists | 1 | Simple numbered |
| Task lists | 3 | Checked, unchecked, mixed |
| Code blocks | 4 | With language, plaintext language, no language, empty language |
| Blockquotes | 2 | Simple, multiline |
| Tables | 1 | 2x2 with header |
| Horizontal rule | 1 | Basic |
| Hard break | 1 | Mid-paragraph |
| Unknown nodes | 2 | With children, without content |
| Plain text | 8 | Empty, paragraph, heading, marks stripped, code block, multiple paragraphs, hard break, task list |

## Decisions Made

1. **Mark ordering in combined marks**: Marks are applied sequentially in array order. For `[bold, italic, link]`, bold wraps text first, then italic wraps that, then link wraps everything: `[_**text**_](url)`
2. **Presentation-only marks skipped**: textStyle (fontSize/fontFamily/color) and highlight (color) produce no Markdown output -- these are visual-only attributes
3. **Plaintext code blocks**: CodeBlockLowlight's `defaultLanguage: 'plaintext'` means all unlabeled code blocks get `language: 'plaintext'` in JSON. Converter renders these as bare ``` fences for clean Markdown
4. **No external dependencies**: Converter uses only Python stdlib (typing, json). No new pip packages required

## Deviations from Plan

None -- plan executed exactly as written.

## Next Phase Readiness

- Content pipeline is complete: every `save_document_content` call now stores JSON + Markdown + plain text
- Markdown output ready for future AI knowledge agent consumption
- Plain text output ready for Phase 9 full-text search indexing
- No blockers for subsequent plans
