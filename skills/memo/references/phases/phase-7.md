<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 7 — Source pack

Dispatch `source-pack-builder` via Agent tool. Pass:
- `plan.md`
- `research/statutes.md`
- `research/case-law.md`
- `research/doctrine.md` if present
- `research/currency-report.md` (human-readable view)
- `research/currency-report.json` (canonical machine-readable view; prefer it for status-enum lookups — markdown is fallback only)
- `research/research-sufficiency.json`
- Working directory path

It writes `research/source-pack.md`, a structured evidence table used by the writer and citation auditor.

Update `state.json.current_phase = source_review_pending` (replaces the v0.0.42 `heartbeat_pending`).

**TodoWrite update.** Mark #8 ("Source pack assembly") = `completed`, #9 ("Source review") = `in_progress` (activeForm: `"Awaiting source review confirmation"`). Call `mcp__ccd_session__mark_chapter(title="Source review", summary="User confirmation before drafting")`. Silent skip if either tool is unavailable.

Print a progress update with source-pack path and counts for evidence rows, do-not-use sources, and manual-check sources.

**Milestone-4 tracker (Research done).** If `state.json.config.visualize_enabled == true`, render the milestone-4 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "4 — Research done"). Save snapshot to `$WORK_DIR/widgets/progress-04-research-done.html` and append `visualize_widget_rendered` event. Graceful skip if disabled or call fails. Research is the longest autonomous section — this milestone is the most informative for the user.

