<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 10 — Client-readiness gate

Set `state.json.current_phase = client_readiness`.

Dispatch `client-readiness-reviewer` via Agent tool. Pass:
- Final draft path from `state.json.current_draft_path`
- `state.json`
- The latest `reviews/v<N>-mediator.md` if it exists
- `intake/fact-assumption-report.md`
- `intake/user-facts.md` if present
- `research/source-pack.md`
- `research/research-sufficiency.json`
- `research/currency-report.md` (human-readable view)
- `research/currency-report.json` (canonical machine-readable view, if present)
- `lib/prose-style.md`

It writes `reviews/final-client-readiness.json`.

Read the JSON:
- `verdict = client_ready` → set `state.json.client_readiness` summary including `blocking_issues = []` and continue to export.

- `verdict = needs_final_polish`:
  - **First check the mode config and gate.** If `config.client_polish_enabled == false` (Brief mode), skip polish entirely. Set `state.json.final_status = manual_review_required_on_v<N>`, set `state.json.client_readiness.blocking_issues` and `state.json.remaining_blocking_issues` from the reviewer JSON, proceed to export with banner. (No user gate here — Brief mode users opted out of polish at Phase 1.5.)
  - **Auto-apply polish (no user gate as of v0.0.44).** If `state.json.attempts.client_readiness_polish == 0`:
    1. Print a one-paragraph summary of client-readiness verdict: blocker count, top categories from JSON, current_draft_path, reviewer report path.
    2. **Auto-advance**: write `state.json.polish_gate_choice = "apply"` (no user input — orchestrator-driven), append `gate_auto_advanced` event with `gate_name: "polish"`, `chosen: "apply"`, `reason: "needs_final_polish_with_budget"`.
    3. Atomically increment `attempts.client_readiness_polish` to `1`, set `attempts.client_readiness_polish_pending_review = true`, append `client_readiness_polish_started` to `events.jsonl`. Dispatch `memo-writer` once for the polish pass (reads the final draft and `reviews/final-client-readiness.json`, writes `drafts/v<N>-client-ready.md`, updates `current_draft_path`, appends to `changelog.md`). Re-run `client-readiness-reviewer` once, then set `attempts.client_readiness_polish_pending_review = false`.
    
    (The v0.0.43-and-earlier "Export as-is" / "Skip polish" option was removed in v0.0.44 — when polish is enabled by mode config AND the verdict needs it, the pipeline applies it. To skip polish entirely, the user picks Brief mode upstream at Phase 1.5, which sets `client_polish_enabled = false`.)
  - **Polish already attempted.** If `attempts.client_readiness_polish >= 1`:
    - If `attempts.client_readiness_polish_pending_review == true`: do NOT mark manual review yet. Re-run `client-readiness-reviewer` once against `state.json.current_draft_path`, then set `attempts.client_readiness_polish_pending_review = false`.
    - If `attempts.client_readiness_polish_pending_review == false`: Full mode's single polish budget is consumed (`max_client_polish = 1`). Set `state.json.final_status = manual_review_required_on_v<N>`, set `state.json.client_readiness.blocking_issues` and `state.json.remaining_blocking_issues` from the reviewer JSON, and proceed to export with a warning banner.

- `verdict = manual_review_required` → set `state.json.final_status = manual_review_required_on_v<N>`, preserve `blocking_issues` in both `state.json.client_readiness.blocking_issues` and `state.json.remaining_blocking_issues`, proceed to export with a warning banner, and surface the reviewer blockers in the final chat summary.

Update `state.json.current_phase = export`.

**TodoWrite update.** Mark #12 ("Client-readiness review") = `completed`, #13 ("Export to docx") = `in_progress`. Call `mcp__ccd_session__mark_chapter(title="Export")`. Silent skip if either tool is unavailable.

Print a progress update with client-readiness verdict, polish attempt status, manual-review blocker count, and final_status.

