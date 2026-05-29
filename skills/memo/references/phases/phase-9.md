<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 9 — Revision loop (max 3 iterations)

**Heads-up message BEFORE entering the revision loop.** Print this to chat first (substitute `<K>` = `len(state.json.config.reviewer_list)`, `<MAX>` = `state.json.config.max_iterations`):

```
🔁 Starting revision loop. Up to <MAX> iteration(s), each runs <K> reviewers in parallel followed by a mediator and a writer revision pass. This is a long autonomous block — please be patient. Per-iteration `**Progress —**` blocks will appear at iteration start, after reviewers complete, and after the mediator.
```

Do NOT include specific wall-time estimates in this message — real durations vary widely and stale numbers mislead the user.

Load the methodology skill `lib/revision-loop.md` (auto-invokable; if not auto-loaded, read explicitly).

**Ownership note:** `state.json.current_iteration` is initialized by the main session when `drafts/v1.md` exists. After a revision iteration starts, the **mediator** advances this field or moves the task to `export`. Main session and continue skill must not increment it after reviewer dispatch.

For each iteration N (1 to `state.json.config.max_iterations`):

1. **Mode-aware reviewer dispatch.** Read `state.json.config.reviewer_list` (canonical reviewer kinds are `logic`, `clarity`, `style`, `citations`, `counterarguments`). Dispatch exactly those reviewers in parallel — emit ONE assistant message containing one Agent tool call per reviewer kind in the list. Mapping reviewer kind → subagent_type:
   - `logic` → `logic-reviewer`
   - `clarity` → `clarity-reviewer`
   - `style` → `style-reviewer`
   - `citations` → `citation-auditor`
   - `counterarguments` → `counterargument-reviewer`

   Output filename pattern is always `reviews/v<N>-<reviewer_kind>.json` (use the plural canonical kind, e.g. `reviews/v<N>-counterarguments.json`).

   Example for Full mode (all five) — adjust the set for Brief (logic + citations + counterarguments only). **Every reviewer prompt MUST include the absolute path to `state.json`** so the reviewer can read `config.prose_style_path` / `config.template_path` and apply the user's custom style profile when one is in effect (those fields are null in the common case → reviewer uses built-in rules):
   ```
   Agent(subagent_type="logic-reviewer", prompt="Review drafts/v<N>.md at <full_path>. State at <work_dir>/state.json. Emit JSON to reviews/v<N>-logic.json.")
   Agent(subagent_type="clarity-reviewer", prompt="Review drafts/v<N>.md at <full_path>. State at <work_dir>/state.json. Emit JSON to reviews/v<N>-clarity.json.")
   Agent(subagent_type="style-reviewer", prompt="Review drafts/v<N>.md at <full_path>. State at <work_dir>/state.json. Emit JSON to reviews/v<N>-style.json.")
   Agent(subagent_type="citation-auditor", prompt="Audit drafts/v<N>.md at <full_path> against research/*.md, research/source-pack.md, and research/currency-report.json (canonical machine-readable view; markdown fallback at research/currency-report.md) at <paths>. Emit JSON to reviews/v<N>-citations.json.")
   Agent(subagent_type="counterargument-reviewer", prompt="Stress-test drafts/v<N>.md at <full_path> against source-pack and intake assumptions. State at <work_dir>/state.json. Emit JSON to reviews/v<N>-counterarguments.json.")
   ```
   (`citation-auditor` does not need state.json — it audits source-grounding, which is independent of style profile.)
   All dispatched reviewers resolve before the next assistant turn. Do NOT serialize these — that wastes wall-time and reviewer isolation depends on each receiving a focused prompt.
   Print a progress update before dispatching reviewers: iteration N, draft path, reviewer list (from `config.reviewer_list`).

2. **JSON validation**: each reviewer writes `reviews/v<N>-<reviewer>.json`. Validate the configured set with:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_review_json.py" \
     --workdir "<state.json.work_dir>" \
     --iteration <N>
   ```
   The validator reads `state.json.config.reviewer_list` and validates ONLY the configured reviewers (3 for Brief, 5 for Full). If you need to override, pass `--reviewers logic,citations,counterarguments`.

   **Emit a `validator_ran` event** for audit (`events-contract.md`):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
     --workdir "$WORK_DIR" --event validator_ran --phase revision_loop --iteration <N> --actor validator \
     --data '{"script":"validate_review_json.py","args_summary":"--iteration <N>","exit_code":<int>,"errors_count":<int>,"warnings_count":<int>,"invoked_by":"memo-skill","purpose":"reviewer-json-check"}'
   ```
   On non-zero exit code, set `--severity warn` (will retry below).

   If `python3` is unavailable, try `python` with the same args. If the validator reports invalid reviewers, atomically increment `state.json.attempts.reviewer_json_retry["v<N>-<reviewer>"]` for each invalid reviewer, append `reviewer_json_retry_started` to `events.jsonl`, then re-dispatch ONLY those reviewers once. Run the validator again. If any reviewer is still invalid, run:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_review_json.py" \
     --workdir "<state.json.work_dir>" \
     --iteration <N> \
     --write-failure-stubs
   ```
   Then validate once more. Do not let missing or malformed reviewer output count as approval.
   Print a progress update after validation: valid reviewer count, invalid/retried reviewer count, and whether failure stubs were written.

3. Dispatch `revision-mediator` (single Agent call, separate turn after reviewers complete). It reads the review JSONs for every reviewer in `state.json.config.reviewer_list` (3 in Brief, 5 in Full) + state.json + house-style skill, writes `reviews/v<N>-mediator.md`, and **updates `state.json` including `current_iteration`** atomically.

4. Validate the mediator's state update before trusting it:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_state.py" \
     --state "<state.json.work_dir>/state.json"
   ```
   If invalid, re-dispatch `revision-mediator` once with the validation errors and require it to repair only `state.json` / `reviews/v<N>-mediator.md`. If state is still invalid, set `current_phase = failed` only if `state.json` is parseable enough to update safely; otherwise stop and surface "state.json corrupted; manual intervention required".

5. Re-read `state.json` to learn the mediator's verdict.
   Print a progress update after mediator: mediator path, verdict, blocking issue count, next iteration or client-readiness.

   **Emit a `phase_transition` event** (mediator advanced `current_phase` and/or `current_iteration` directly inside state.json — orchestrator emits the audit event on its behalf, per `events-contract.md`):

   ```bash
   # If mediator advanced to next iteration (verdict needs_revision, iteration incremented):
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
     --workdir "$WORK_DIR" --event phase_transition --phase revision_loop --iteration <new_iteration> --actor memo-skill \
     --data '{"from":"revision_loop","to":"revision_loop","reason":"iteration_advance"}'

   # If mediator approved and moved to client_readiness:
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
     --workdir "$WORK_DIR" --event phase_transition --phase client_readiness --iteration <N> --actor memo-skill \
     --data '{"from":"revision_loop","to":"client_readiness","reason":"mediator_approved"}'

   # If forced exit (max_iterations reached with blockers):
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
     --workdir "$WORK_DIR" --event phase_transition --phase client_readiness --iteration <N> --actor memo-skill --severity warn \
     --data '{"from":"revision_loop","to":"client_readiness","reason":"mediator_forced_exit"}'
   ```

6. **End-of-iteration auto-advance (no user gate as of v0.0.44).** Decision depends entirely on mediator verdict + remaining budget. No AskUserQuestion call here — the pipeline runs autonomously through the entire revision loop until mediator approval or `max_iterations` is reached (see issues #26805 / #29773 / #29547 / #33564 / #44776 for why post-parallel-Task AskUserQuestion was removed).

   **6a. Verdict = `approved_on_v<N>` (mediator approved current draft):**
   - **Milestone-5 tracker (Revision done).** If `state.json.config.visualize_enabled == true`, render the milestone-5 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "5 — Revision done"). Save snapshot to `$WORK_DIR/widgets/progress-05-revision-done.html` and append `visualize_widget_rendered` event. Graceful skip if disabled or call fails. Render only once per pipeline run (not per iteration).
   - **TodoWrite update.** Mark #11 ("Revision loop") = `completed`, #12 ("Client-readiness review") = `in_progress`. Call `mcp__ccd_session__mark_chapter(title="Client polish", summary="Final review before export")`. Silent skip if either tool is unavailable.
   - Go to Phase 10 inline.

   **6b. Verdict = `needs_revision` AND `current_iteration < config.max_iterations` (another iteration would run):**

   This is a **strict less-than** comparison — matches `continue/SKILL.md` revision_loop branch and `revision-mediator.md` exit logic. When `current_iteration == config.max_iterations` and the mediator returns `needs_revision`, no further iteration is possible; the mediator should have written `forced_exit_on_v<N>` and the run falls to gate 6c instead.

   - Skip this branch if `config.max_iterations == 1` (Brief mode — no further iteration possible anyway; mediator should have written `forced_exit_on_v1` in this case, which falls to 6c).
   - Print a one-paragraph chat summary: iteration N completed, top reviewer scores (e.g. `logic 86 / clarity 72 / style 84 ✓ / citations 92 ✓ / counterargs 78`), blocking issue count from mediator, current_draft_path, mediator report path.
   - **Auto-advance**: write `state.json.revision_gate_choice = "continue"` (no user input — orchestrator-driven), append `gate_auto_advanced` event with `gate_name: "revision-iter"`, `chosen: "continue"`, `reason: "mediator_needs_revision_with_budget"`.
   - **TodoWrite update**: keep #11 `in_progress` with updated activeForm `"Running revision loop (iteration <N+1>)"`. Call `mcp__ccd_session__mark_chapter(title="Revision iteration <N+1>")` (only on N+1 ≥ 2). Silent skip if either tool is unavailable.
   - Proceed inline to step 7 (dispatch memo-writer for v<N+1>).

   **6c. Verdict = `forced_exit_on_v<N>_with_remaining_issues` (loop exhausted with blockers):**
   - Print a one-paragraph summary: forced exit reason, remaining blocker count, current_draft_path, mediator report path.
   - **Auto-advance to client-readiness**: write `state.json.client_readiness_gate_choice = "continue"` (no user input), append `gate_auto_advanced` event with `gate_name: "revision-forced-exit"`, `chosen: "continue"`, `reason: "mediator_forced_exit"`. The unresolved-blockers banner from mediator is already in `state.json.fallback_banners[]` (per always-deliver matrix) and flows into the docx regardless.
   - If `state.json.config.visualize_enabled == true`, render the milestone-5 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "5 — Revision done"); save snapshot to `$WORK_DIR/widgets/progress-05-revision-done.html`; graceful skip if disabled or call fails.
   - **TodoWrite**: mark #11 `completed`, #12 `in_progress`. `mark_chapter(title="Client polish")`. Silent skip if unavailable.
   - Inline continue to Phase 10. (The v0.0.43-and-earlier "Export as-is" option was removed in v0.0.44 — pipeline always runs client-readiness even at forced exit. The banner ensures the docx still discloses unresolved blockers.)

7. **Loop continuation** (only reached from 6b auto-advance). **Pre-seed the new versioned draft first (C2 — targeted edits):** before dispatching the writer, copy the prior draft into the new version path via Bash so the writer can `Edit` it in place rather than regenerate the whole memo. Full regeneration re-touches clean sections, wastes output-token time (the slow part of inference), and causes score regressions in sections that were already fine (observed on the 2026-05-28 run: logic 91→79 between v2 and v3).

   ```bash
   cp "$WORK_DIR/drafts/v<N>.md" "$WORK_DIR/drafts/v<new_iteration>.md"
   ```

   Then dispatch `memo-writer` for v<new_iteration> (it reads `drafts/v<N>.md` for reference + `reviews/v<N>-mediator.md` + changelog + state; also pass `research/*.md` if mediator instructions mention citations, unsupported claims, source drift, currency, or Sources section fixes). Instruct it explicitly in the dispatch prompt: **"`drafts/v<new_iteration>.md` is pre-seeded with v<N>'s content. `Edit` ONLY the sections named in the mediator report, plus their explicit cross-references (the Exec-Summary bullet, Conclusion-matrix row, and Risk line that cite a changed section). Leave clean sections byte-stable. Do a full rewrite ONLY if the mediator's blocking issues span more than half the analytical sections or are structural/template-level."** The writer appends to changelog. Go back to step 1.

Do not increment `current_iteration` from main session after reviewer dispatch; that's mediator's responsibility (preventing double-increment races).

**No AskUserQuestion in the revision loop as of v0.0.44.** The pipeline auto-advances per mediator verdict. The previous "AskUserQuestion-unavailable fallback" line is no longer needed — there is no AskUserQuestion to be unavailable. If the user wants to abort mid-loop, they cancel the task at the Cowork session level.

