<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 12.5 — Workdir tidy (best-effort, v0.7.0+)

After the Phase 12 delivery summary has been emitted to chat AND `TodoWrite` is marked complete, but BEFORE end-turn, do a final cleanup pass on the task `work_dir` top level. The goal is leaving the user with a clean folder containing only user-relevant artifacts.

**Best-effort throughout.** A tidy failure is non-fatal — the script reports any file it could not remove and still exits 0. The user already has the docx + audit trail; tidy is purely cosmetic UX polish.

### What stays at the top level

After tidy, `<work_dir>/` (top level only) MUST contain only:

- `memo-<slug>.docx` (the final deliverable; on markdown-fallback path the extension is `.md`)
- `memo-<slug>.md` (markdown mirror written for Cowork artifact-card visibility — present in both success and fallback paths)
- `state.json` (schema-referenced; needed for `/memoforge:continue <task_id>` and post-completion validators)
- `events.jsonl` (schema-referenced; the audit log per `state.json.events_path` — keep at top level since the field is the relative form `"events.jsonl"`)
- `plan.md` (user-facing planning artifact — referenced in Phase 12 delivery summary "Audit trail" line)
- `changelog.md` (revision-history summary appended by memo-writer across v1→vN drafts; user-facing)
- `live-progress.html` (the **canonical master** dashboard — exactly ONE, in its terminal "delivered" state). Kept because it is a useful self-contained visual summary of the run in a folder the user keeps, syncs, shares, or archives. The Cowork chat's content-addressed artifact card survives deletion, but that only helps inside the originating chat session — the delivered folder has no other fallback, so the master stays. Its off-contract `live-progress-*.html` siblings are deleted (see below).
- Canonical subdirectories: `intake/`, `research/`, `drafts/`, `reviews/`, `logs/`, `widgets/`, `checkpoints/` (each present iff the pipeline reached the phase that creates it)

### What gets DELETED by tidy (and why)

1. **Top-level side-car `live-progress-*.html` files** (the hyphen matters) — per-subagent / per-reviewer / per-phase snapshots like `live-progress-clarity-done.html`, `live-progress-logic-start.html`, `live-progress-cr-start.html`, `live-progress-tmp.html`, etc. These are off-contract: the live-progress HARD RULE (`references/live-progress-contract.md`, v0.7.2) says the renderer writes exactly ONE file, `live-progress.html`, and side-cars are NOT a sanctioned escape hatch. Their existence means an orchestrator improvised sibling renders instead of updating the master path — a separate bug; tidy is the catch-net. They carry no audit value post-completion because:
   - The pipeline's chronological timeline is preserved in `state.json.live_progress.timeline[]`.
   - Phase transitions are preserved as `phase_transition` events in `events.jsonl`.
   - The master `live-progress.html` (kept — see "What stays") already shows the run's terminal state.

   **The canonical master `live-progress.html` is PRESERVED** (it has no hyphen, so the `live-progress-*.html` glob never matches it). Earlier drafts of this phase (≤v1.1.0) deleted the master too, on the theory that Cowork's chat artifact card makes the local file redundant — but that only holds inside the originating chat; a delivered/synced/archived folder benefits from keeping its one dashboard. Only the redundant siblings go.

2. **Top-level `*.py` files** — canonical Python scripts for this plugin live at `${CLAUDE_PLUGIN_ROOT}/scripts/` (e.g. `render_live_progress.py`, `log_event.py`, `validate_state.py`). They are NEVER copied into a task's `work_dir`. Any `*.py` file at the top level of `work_dir` is a stray artifact — typically from a subagent that wrote an inline Python helper into work_dir instead of invoking the canonical `${CLAUDE_PLUGIN_ROOT}/scripts/*` (the screenshot that motivated this phase showed `lp_done_render.py` and `lp_run.py`). These files have no canonical purpose and are safe to delete.

3. **`*.tmp` files anywhere in `work_dir`** — atomic-write leftovers from interrupted `cat > X.tmp; mv X.tmp X` sequences. If the interrupt happened, the destination already has the prior valid content (mv didn't run); the `.tmp` is garbage. Recursively delete.

### Invocation — call the canonical script (best-effort)

Tidy is a single deterministic, tested, cross-platform script (`scripts/tidy_workdir.py`, covered by `scripts/tests/test_tidy_workdir.py`). Do NOT inline `find ... -delete` — that is GNU-find-only (breaks on a Windows host), silently swallows every error, and historically lived only in the `memo` skill's phase files while the path that actually ends a run (`continue` skill `### done`) had no tidy at all (the v1.1.0 catch-net gap).

```bash
WORK_DIR="<state.json.work_dir>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tidy_workdir.py" --workdir "$WORK_DIR" \
  || python "${CLAUDE_PLUGIN_ROOT}/scripts/tidy_workdir.py" --workdir "$WORK_DIR" \
  || true
```

The script self-guards (reads `state.json`; skips on `failed` / `cancelled_by_user` / `fallback_*` / unfinished — so the "When NOT to run tidy" rules below are enforced in-script, not just by the caller), reports what it removed (it does not swallow silently), and always exits 0 on a reachable work_dir so it can never break a finished pipeline. The `python3 || python` chain mirrors the validator call sites for hosts where only `python` is on PATH.

### What tidy does NOT touch

- Anything inside canonical subdirs (`intake/`, `research/`, `drafts/`, `reviews/`, `logs/`, `widgets/`, `checkpoints/`) — those are the per-phase artifact stores. The two top-level globs (`live-progress-*.html`, `*.py`) never recurse into them; the only recursive sweep is `*.tmp`, which is always atomic-write garbage wherever it lands.
- Files at the top level matching the "what stays" list (docx, .md mirror, state.json, events.jsonl, plan.md, changelog.md, master `live-progress.html`).
- Anything outside `work_dir`. The script operates only under `--workdir`.

### When NOT to run tidy

The script enforces all of the following in-process (it reads `state.json` and self-skips), so the orchestrator may call it unconditionally at `done`. It leaves the work_dir completely untouched if EITHER:

- `state.json.final_status` starts with `fallback_` (e.g. `fallback_research_summary_delivered`, `fallback_summary_delivered`) — fallback paths may have unusual artifacts at top level that diagnostics need; better leave the workdir untouched for forensics.
- `state.json.current_phase` is `failed` or `cancelled_by_user` — same forensic reasoning.

If `final_status` indicates a normal completion (`approved_on_v<N>`, `forced_exit_on_v<N>_with_remaining_issues`, `manual_review_required_on_v<N>`, `accepted_early_on_v<N>`), tidy runs.

End turn.

