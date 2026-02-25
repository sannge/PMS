# UI/UX Pro Max -- Integration Guide for PM Desktop

**Last updated**: 2026-02-24

---

## Important Clarification

**UI/UX Pro Max is NOT an npm component library.** It is an **AI skill** (design intelligence system) that augments AI coding assistants like Claude Code with a searchable knowledge base of UI styles, color palettes, typography pairings, UX guidelines, and design system generation capabilities. It does not ship React components, CSS files, or runtime JavaScript. Instead, it guides the AI assistant to produce higher-quality, more consistent UI code when you ask it to build interfaces.

- **GitHub**: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- **npm CLI**: `uipro-cli` (installer only, not a runtime dependency)
- **Latest version**: v2.2.1 (January 2025)
- **License**: MIT

---

## Table of Contents

- [Package Overview](#package-overview)
- [What It Provides](#what-it-provides)
- [Installation and Setup](#installation-and-setup)
- [Integration with PM Desktop Stack](#integration-with-pm-desktop-stack)
- [Using It for Blair (AI Copilot) Features](#using-it-for-blair-ai-copilot-features)
- [Best Practices and Patterns](#best-practices-and-patterns)
- [Conflicts and Considerations](#conflicts-and-considerations)

---

## Package Overview

UI/UX Pro Max is a design intelligence skill for AI coding assistants. When installed in a project, it provides the AI with:

1. **A searchable design knowledge base** -- 344+ curated design resources in CSV format
2. **A BM25 search engine** -- Python-based retrieval that ranks design recommendations by relevance
3. **A design system generator** -- Analyzes project requirements and produces a complete, tailored design system with reasoning
4. **Stack-specific guidelines** -- Targeted guidance for 13 technology stacks including React, shadcn/ui, and Tailwind CSS

The skill activates automatically when you request UI/UX work in Claude Code. It does not add any runtime dependencies to your application.

---

## What It Provides

### Design Resource Databases

| Domain | Records | Description |
|--------|---------|-------------|
| UI Styles | 67 | Visual styles (glassmorphism, minimalism, neobrutalism, AI-native, etc.) with CSS patterns and AI prompts |
| Color Palettes | 96 | Industry-organized palettes (SaaS, fintech, healthcare, etc.) with primary, secondary, CTA, background, and text colors |
| Font Pairings | 57 | Curated heading + body font combinations with Google Fonts URLs |
| UX Guidelines | 99 | Best practices with severity levels, anti-patterns, and accessibility rules |
| Chart Types | 25 | Dashboard chart recommendations with library suggestions and best practices |
| Landing Patterns | 24 | Page structure patterns with CTA strategies and section breakdowns |
| Icon Sets | 100 | Lucide icon mappings by usage category |
| Product Rules | 100 | Industry-specific reasoning rules for design decisions |
| Reasoning Rules | 100 | JSON-based decision logic for automated design system generation |

### Priority-Based Rule System

| Priority | Category | Impact |
|----------|----------|--------|
| 1 | Accessibility | CRITICAL -- 4.5:1 contrast ratios, aria-labels, keyboard navigation |
| 2 | Touch/Interaction | CRITICAL -- 44x44px min touch targets, loading states, error messaging |
| 3 | Performance | HIGH -- Async content placeholders, optimized rendering |
| 4 | Layout/Responsive | HIGH -- Mobile-first, viewport meta, z-index scales |
| 5 | Typography/Color | MEDIUM -- 1.5-1.75 line-height, 65-75 chars per line |
| 6 | Animation | MEDIUM -- Smooth transitions without layout shifts |
| 7 | Style Selection | MEDIUM -- Consistent visual language |
| 8 | Charts/Data | LOW -- Appropriate visualization types |

---

## Installation and Setup

### Prerequisites

- **Python 3.x** -- Required for the BM25 search engine scripts
- **Node.js 14.x+** and **npm 6.x+** -- For the CLI installer

### Step 1: Install the CLI globally

```bash
npm install -g uipro-cli
```

### Step 2: Verify installation

```bash
uipro --version
```

### Step 3: Initialize in the PM Desktop project

```bash
cd D:/FTX_CODE/pm-project
uipro init --ai claude
```

This creates the skill files at `.claude/skills/ui-ux-pro-max/` containing:

```
.claude/skills/ui-ux-pro-max/
  SKILL.md          # Instructions for Claude Code (auto-loaded)
  scripts/
    search.py       # Main search entry point
    core.py         # BM25 search engine
    design_system.py # Design system generator
  data/
    *.csv           # All design resource databases
```

### Step 4: Verify installation

```bash
ls -la .claude/skills/ui-ux-pro-max/
```

### Step 5 (Optional): Generate a project-specific design system

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "project management SaaS dashboard" --design-system --persist -p "PM Desktop"
```

This creates a `design-system/` directory with a Master design system file and optional page-specific overrides.

### Offline Installation

If GitHub is unreachable (rate limits, air-gapped environment):

```bash
uipro init --ai claude --offline
```

The CLI bundles a fallback copy of all assets (~564KB).

---

## Integration with PM Desktop Stack

### How It Works at Development Time

UI/UX Pro Max does **not** change your runtime stack. Your existing dependencies remain exactly the same:

| Existing Dependency | Role | Unchanged? |
|-------------------|------|-----------|
| React 18 | UI framework | Yes |
| TailwindCSS | Utility-first CSS | Yes |
| Radix UI | Accessible primitives | Yes |
| shadcn/ui pattern | Component composition | Yes |
| TipTap | Rich text editing | Yes |
| Zustand | State management | Yes |
| @dnd-kit | Drag and drop | Yes |

The skill operates purely as **AI-time intelligence**. When you ask Claude Code to build a UI component, the skill:

1. Analyzes your request for product type, style keywords, and industry context
2. Searches its design databases using BM25 ranking
3. Retrieves stack-specific guidelines for your technology (React + shadcn + Tailwind)
4. Applies reasoning rules to recommend styles, colors, typography, and patterns
5. Validates the output against accessibility and UX anti-patterns

### Stack-Specific Modes

When using the skill, specify the `shadcn` stack for PM Desktop since it combines React + Tailwind + Radix UI:

```bash
# Search for shadcn-specific patterns
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "dashboard sidebar" --stack shadcn

# Search for React-specific patterns
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "chat interface" --stack react
```

The `shadcn` stack filter prioritizes:
- Radix UI primitive composition patterns
- Tailwind utility class combinations
- Accessible component architecture
- Light/dark mode theming via CSS variables

### No Conflicts with Existing Dependencies

Since the skill adds zero runtime packages, there are no version conflicts. The `.claude/skills/` directory is a development-time asset only. You should add it to `.gitignore` if you do not want it tracked in version control, or keep it tracked if all team members use Claude Code.

---

## Using It for Blair (AI Copilot) Features

The following sections map each Blair feature area (from Phase 5 and Phase 7 of the AI agent plan) to specific UI/UX Pro Max capabilities.

### Chat Sidebar UI (Phase 5, Task 5.3)

The Blair chat sidebar is a collapsible right-side panel with streaming messages, tool execution cards, and source citations.

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "AI chat sidebar SaaS" --design-system -p "Blair"
```

**Domain-specific searches:**
```bash
# Style recommendations for chat interfaces
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "chat conversation AI assistant" --domain style

# Color palette for AI-branded elements
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "AI technology SaaS" --domain color

# Typography for chat messages vs system text
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "chat messaging interface" --domain typography
```

**Key guidelines the skill will enforce:**
- Message bubbles with proper contrast ratios (4.5:1 minimum)
- Streaming text indicators with smooth animation (no layout shifts)
- Touch targets >= 44x44px for action buttons
- Accessible keyboard navigation through message history
- SVG icons (Lucide) instead of emojis for UI elements
- `cursor-pointer` on all interactive elements

**Implementation pattern (shadcn/ui):**
```tsx
// The skill guides Claude to produce components like:
// - ScrollArea from Radix for message list (already in project)
// - Tailwind prose classes for AI response formatting
// - Proper aria-live regions for streaming content
// - Collapsible sidebar using existing Sheet/Dialog patterns
```

### Inline Confirmation/Clarification Cards (Phase 5, Task 5.5)

These are the human-in-the-loop cards that appear when Blair needs user approval to perform actions (create task, update status, etc.).

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "confirmation dialog inline card action approval" --domain style
```

**UX guidelines search:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "confirmation dialog user action" --domain ux
```

**Key guidelines the skill will enforce:**
- Clear visual hierarchy: action description, affected entities, approve/reject buttons
- Destructive actions use red/warning color treatment
- Non-blocking inline cards (not modal dialogs) to maintain chat flow
- Loading states on approve/reject buttons during execution
- Success/failure feedback after action completion
- Form labels with proper `htmlFor` attributes

### Settings Panels (Phase 7, Task 7.1)

The AI settings panel lets users configure LLM provider, API keys, model selection, and temperature.

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "settings configuration panel SaaS admin" --design-system -p "Blair Settings"
```

**Domain searches:**
```bash
# Form and input patterns
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "settings form configuration" --domain ux

# Layout for settings pages
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "settings panel layout" --domain landing
```

**Key guidelines the skill will enforce:**
- Grouped settings with clear section headers
- Input validation with inline error messages
- Password/API key fields with show/hide toggle and proper masking
- Save confirmation feedback (toast or inline)
- Responsive layout that works in the sidebar context
- Proper `aria-describedby` for help text

### Admin Dashboard (Phase 7, Tasks 7.2-7.4)

The admin dashboard shows AI usage metrics, token consumption, cost tracking, and system health.

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin dashboard analytics metrics SaaS" --design-system --persist -p "Blair Admin" --page admin-dashboard
```

**Chart-specific search:**
```bash
# Chart type recommendations for usage metrics
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "usage analytics dashboard time series" --domain chart

# Dashboard layout patterns
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin dashboard metrics cards" --domain style
```

**Key guidelines the skill will enforce:**
- KPI cards at top with clear number formatting
- Appropriate chart types (line charts for time series, bar charts for comparisons, donut for distribution)
- Chart library recommendations (the project already uses Recharts for dashboard charts)
- Reserved space for async-loading chart data (skeleton placeholders)
- Consistent color coding across all visualizations
- Responsive grid layout for metric cards
- Dark mode compatibility for all chart colors

### Import Dialogs (Phase 6, Task 6.3)

Document import dialogs for PDF, DOCX, PPTX files processed by Docling.

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "file upload import dialog progress" --domain style
```

**UX search:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "file upload drag drop progress" --domain ux
```

**Key guidelines the skill will enforce:**
- Drag-and-drop zone with clear visual affordance
- File type validation with user-friendly error messages
- Upload progress indicator (deterministic if possible)
- Processing status with stage information (uploading -> converting -> indexing)
- Cancel capability during long operations
- Success state with link to imported document
- Maximum file size guidance displayed upfront

### Status Badges and Indicators

Status badges appear throughout Blair's UI: connection status, indexing status, model availability, and processing states.

**Design system query:**
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "status badge indicator tag label" --domain style

python3 .claude/skills/ui-ux-pro-max/scripts/search.py "status indicator accessibility" --domain ux
```

**Key guidelines the skill will enforce:**
- Never rely on color alone for status (add icons or text labels)
- Consistent color semantics: green=active, amber=processing, red=error, gray=inactive
- Proper contrast ratios for badge text on colored backgrounds
- Pulse/dot animation for "live" indicators (e.g., AI is thinking)
- Screen reader announcements for status changes via `aria-live`

---

## Best Practices and Patterns

### 1. Always Start with Design System Generation

Before building any new Blair feature, run the design system generator:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<feature description>" --design-system -p "Blair"
```

This produces a holistic recommendation before you dive into individual components.

### 2. Use Persist Mode for Multi-Page Features

For the admin dashboard and settings, use `--persist` to maintain consistency across pages:

```bash
# Generate master design system
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "AI copilot SaaS project management" --design-system --persist -p "Blair"

# Generate page-specific overrides
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "chat sidebar conversation" --design-system --persist -p "Blair" --page chat-sidebar
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "admin dashboard analytics" --design-system --persist -p "Blair" --page admin-dashboard
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "settings configuration" --design-system --persist -p "Blair" --page settings
```

This creates:
```
design-system/Blair/
  MASTER.md              # Global Blair design rules
  pages/
    chat-sidebar.md      # Chat-specific overrides
    admin-dashboard.md   # Admin-specific overrides
    settings.md          # Settings-specific overrides
```

### 3. Specify the shadcn Stack

Always pass `--stack shadcn` for domain searches to get Radix UI + Tailwind-specific guidance:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "modal dialog" --stack shadcn --domain style
```

### 4. Use Natural Language with Claude Code

Since the skill auto-activates in Claude Code, you can simply describe what you need:

> "Build the Blair chat sidebar with a message list, streaming text, source citations, and inline confirmation cards for tool actions. Use our existing shadcn/ui components."

The skill will automatically search its databases and apply relevant guidelines before Claude generates code.

### 5. Validate Against Anti-Patterns

Search the UX domain to check for common mistakes before shipping:

```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "common mistakes chat interface" --domain ux
```

### 6. Follow the Priority System

When the skill's recommendations conflict, follow the priority order:

1. Accessibility (CRITICAL) -- always wins
2. Touch/Interaction (CRITICAL) -- always wins
3. Performance (HIGH) -- override style choices if needed
4. Layout (HIGH) -- override aesthetic preferences
5. Typography/Color (MEDIUM)
6. Animation (MEDIUM)
7. Style (MEDIUM)
8. Charts (LOW)

---

## Conflicts and Considerations

### No Runtime Conflicts

Since UI/UX Pro Max is a development-time AI skill (not a runtime library), it has **zero conflicts** with existing dependencies. It adds no packages to `package.json`, no CSS to the bundle, and no JavaScript to the build output.

### Python 3.x Requirement

The search engine requires Python 3.x. This is already available in the PM Desktop development environment (FastAPI backend uses Python 3.12). The search scripts have no external Python dependencies.

### .gitignore Consideration

Decide whether to track `.claude/skills/` in version control:

- **Track it**: All developers using Claude Code get the same design intelligence. Adds ~1MB to the repo.
- **Ignore it**: Each developer installs independently via `uipro init`. Add to `.gitignore`:
  ```
  .claude/skills/
  design-system/
  ```

### design-system/ Directory

If you use `--persist` mode, the generated `design-system/` directory should be tracked in git so all developers and the CI can reference the agreed design system.

### Coexistence with Existing CLAUDE.md

The skill's `SKILL.md` file lives in `.claude/skills/ui-ux-pro-max/SKILL.md` and is loaded alongside the project's root `CLAUDE.md`. They do not conflict. The SKILL.md provides design-specific instructions while CLAUDE.md provides project-specific coding conventions.

### Team Alignment

If multiple developers use different AI assistants, the skill supports 14 platforms. Run `uipro init` without `--ai` to auto-detect all installed assistants, or use `--ai all` to install for every supported platform.

### Updating the Skill

```bash
uipro update
```

This pulls the latest release from GitHub and updates the local skill files.

---

## Quick Reference Commands

| Task | Command |
|------|---------|
| Install CLI | `npm install -g uipro-cli` |
| Initialize for Claude Code | `uipro init --ai claude` |
| Generate design system | `python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --design-system -p "Name"` |
| Search by domain | `python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --domain <style\|color\|typography\|ux\|chart\|landing\|product>` |
| Search by stack | `python3 .claude/skills/ui-ux-pro-max/scripts/search.py "<query>" --stack shadcn` |
| Persist design system | Add `--persist` and optionally `--page <name>` |
| Update skill | `uipro update` |
| Check version | `uipro --version` |
| Offline install | `uipro init --ai claude --offline` |

---

## Sources

- [GitHub Repository](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
- [npm: uipro-cli](https://www.npmjs.com/package/uipro-cli)
- [DeepWiki: Getting Started](https://deepwiki.com/nextlevelbuilder/ui-ux-pro-max-skill/1.1-getting-started)
- [Skills.sh Listing](https://skills.sh/nextlevelbuilder/ui-ux-pro-max-skill/ui-ux-pro-max)
- [Release Notes](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/releases)
