<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 4b — Parse plan response (text fallback path only)

This phase runs only when the user replies via plain text (or `/continue`) after Path B was used in Phase 4a. The Path A interactive flow handles its branches inline and never reaches Phase 4b.

On reactivation, parse the last user message:

- Starts with `approve` (case-insensitive, any punctuation) → set `state.json.plan_approval.status = approved`, `state.json.plan_approval.final_plan_iteration = <current>`, `state.json.current_phase = research`. Print a progress update summarizing classification, selected template, and researchers to run. If `state.json.config.visualize_enabled == true`, render the milestone-3 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "3 — Plan approved"); save snapshot to `$WORK_DIR/widgets/progress-03-plan-approved.html`; graceful skip if disabled or call fails. **TodoWrite update**: mark #4 `completed`, #5 `in_progress`. Go to Phase 5.
- Starts with `edit:` or `edit ` → check `max_plan_edit_iterations` (default 5). If exceeded, print "Edit limit reached, reply approve or cancel" and end turn. Otherwise:
  1. Read user instructions.
  2. Apply edits to `plan.md` (use Edit tool).
  3. Append new iteration to `checkpoints/plan-approval.md`.
  4. Update `state.json.plan_approval.iterations` with the new iteration metadata.
  5. **Watch for template conflicts**: if edits expand scope beyond the selected template (e.g. user asks deep analysis but template is `executive-brief`), warn in the updated plan.md: "**Warning:** edits expand scope relative to <template>. Consider switching to <suggestion>."
  6. Re-show updated plan (Phase 4a), end turn.
- Starts with `cancel` → set `plan_approval.status = cancelled`, `current_phase = cancelled_by_user`. Print: "Pipeline stopped. Working directory preserved at <state.json.rel_work_dir>/ (plain text path — open from the Cowork file viewer). Resume with: `/memoforge:continue <task_id>`." End turn.
- **Anything else** → ask the user to use one of the three formats (don't increment `max_plan_edit_iterations`). End turn.

