# RAG Intelligence Studio Page Rules

> These rules override `../MASTER.md` for the RAG Admin workspace.

## Product Character

RAG Intelligence Studio is a data-rich operational workspace, not a marketing showcase. It should feel precise, calm, and trustworthy while keeping authoring approachable for non-technical store administrators.

## Information Architecture

Use three persistent, deep-linkable tabs:

1. **Knowledge Base** — Knowledge Items, popular categories, filters, CSV import, bulk publication.
2. **Retrieval Methods** — four method cards, Published Retrieval Configuration, version history, rollback.
3. **Tests & Performance** — ad hoc retrieval, Retrieval Test Cases, Evaluation Runs, charts, Miss Explorer, CSV export.

The workspace header always shows the current store, RAG Readiness, Published Retrieval Method, index health, and one primary action: **Add Knowledge**. Do not repeat primary CTAs at the bottom of sections.

When the Store Knowledge Base is empty, replace the table with a four-step readiness guide: add/import knowledge, preview chunks and publish, publish a Retrieval Configuration, then confirm one ad hoc result. After readiness, collapse the guide into the persistent header summary.

## Layout

- Desktop ≥1280px: maximum content width 1440px with 24px gutters.
- Tablet 768–1279px: single-column content; editing drawer becomes a full-width sheet.
- Phone <768px: status and evaluation results are readable; batch import and complex editing are view-only with an explanation.
- Preserve tab, filter, pagination, and scroll state when navigating back.
- Avoid nested scrolling except for the desktop editing drawer.

## Visual System

- Version one supports the Admin light theme only. Keep semantic tokens dark-mode-ready, but do not introduce a page-local dark-mode toggle.
- Background: `#F8FAFC`; primary surfaces: `#FFFFFF`; borders: `#E2E8F0`.
- Foreground: `#1E293B`; secondary text: `#64748B`; CTA and selected state: `#2563EB`.
- Destructive: `#DC2626`; warning: accessible amber with text/icon; success: accessible green with text/icon.
- Use Fira Sans for headings, labels, and body copy. Use Fira Code only for scores, latency, versions, IDs, and technical details.
- Use Lucide-style outline SVG icons with a consistent 1.75–2px stroke. Never use emoji as structural icons.
- Use heat-map color only inside the method-by-metric comparison matrix. Every cell must also display its numeric value and accessible label.

## Knowledge Base

- Popular categories are large icon-and-text chips; show four, followed by “All categories”.
- The desktop list is a sortable table with selection checkboxes, title, category, content type, status, updated time, and labeled actions.
- Selecting rows reveals a sticky bulk-action bar. Never show bulk controls with no selection.
- Add/edit uses a right drawer on desktop and a full-width sheet on tablet.
- The form order is Title (optional), Knowledge Category, RAG Content Type, guided template, Knowledge Content, chunk preview.
- Validate on blur; place errors beside fields and focus the first invalid field after submission.
- Confirm before dismissing unsaved changes.

## Retrieval Methods

- Use a 2×2 method-card grid on desktop and one column on tablet.
- Each card shows use case, limitation, Hit Rate@3, MRR@5, P95 latency, health, and Published/Recommended state.
- Only a Published method card receives the strong selected treatment. Recommendation uses a separate labeled badge.
- Top K uses a 3/5/10 segmented control. Relevance Policy uses Lenient/Balanced/Strict cards.
- Publishing is one primary action with an explicit summary of method, Top K, policy, index version, and evaluation evidence.

## Tests & Performance

- Separate **Ad hoc test**, **Test cases**, and **Evaluation runs** with secondary sub-navigation.
- Ad hoc result rows show rank, title, category, content type, matched chunk, final score, and total latency.
- Technical score components remain collapsed under “Score details”.
- Evaluation summary uses grouped horizontal bars for Hit Rate@1/@3/@5, followed by a sortable data table.
- Use the heat-map matrix only as a compact secondary comparison.
- Miss Explorer lists question, Expected Knowledge, and first relevant rank for each method.
- Charts must include direct values, keyboard-accessible tooltips, a text insight summary, and a table alternative.

## Interaction and Motion

- Provide visible feedback within 100ms of activation.
- Use 150–250ms opacity/transform transitions for drawers, tabs, selection bars, and progress updates.
- Never animate width/height or block input during motion.
- Evaluation and indexing show determinate progress when counts are known; jobs continue after navigation.
- Completion appears as an `aria-live="polite"` toast and Admin notification badge.
- Respect `prefers-reduced-motion`.

## Accessibility

- Minimum 44×44px targets with at least 8px between adjacent controls.
- Normal text contrast ≥4.5:1; large text and data graphics ≥3:1.
- All controls have visible labels; icon-only controls require an accessible name.
- Keyboard order follows the visual order. Tabs implement correct tab semantics and arrow-key navigation.
- Focus is trapped only inside an open modal/drawer and returns to its trigger on close.
- Status and chart meaning always use icon/text/pattern in addition to color.
- Provide a skip link to the RAG workspace main region.

## Anti-Patterns

- No marketing hero, social proof, or repeated CTA sections.
- No dashboard of undifferentiated KPI cards.
- No radar, pie, donut, or decorative gauge charts.
- No color-only heat maps.
- No free-form category creation.
- No hover-only actions, unlabeled icon buttons, or invisible focus rings.
- No raw algorithm parameters in the standard Admin surface.
