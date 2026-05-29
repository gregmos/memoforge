<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 8 — Drafting (v1)

**FIRST: parse the user's source-review reply.** Phase 8 is entered either by inline-resume in the same session (user's next chat message at `current_phase == source_review_pending`) or by the `continue` skill (cross-session). On entry:

1. Read `state.json` for `current_phase` and the latest user message.
2. **If `current_phase == source_review_pending`**, parse the user's chat message (case-insensitive, leading/trailing punctuation ignored):
   - Starts with `continue` (or `proceed`, `go`, `draft`, `yes`, `ok`) → set `state.json.current_phase = drafting`. Continue to step 3 below.
   - Starts with `cancel` (or `stop`, `abort`, `no`) → set `state.json.current_phase = cancelled_by_user`. Print "Pipeline stopped at source-review. Working directory preserved at `<state.json.rel_work_dir>/`. Resume with `/memoforge:continue <task_id> continue`." End turn.
   - Anything else → re-show the source-review checkpoint instructions (per Phase 7.5 template above). End turn. Do not advance.
   - **Also emit `gate_answered`** for the audit log:
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
       --workdir "$WORK_DIR" --event gate_answered --phase source_review_pending --actor memo-skill \
       --data '{"gate_name":"source-review","options_offered":["continue","cancel"],"chosen":"<continue|cancel|reprompt>","was_fallback":false}'
     ```
3. **If `current_phase == drafting`** (set by the parser above OR already set on resume), proceed with the drafting dispatch below.

**TodoWrite update.** Mark #9 ("Source review") = `completed`, #10 ("Draft v1 (memo-writer)") = `in_progress`. Call `mcp__ccd_session__mark_chapter(title="Drafting", summary="Memo-writer composing v1")`. Silent skip if either tool is unavailable.

**Heads-up message BEFORE dispatching `memo-writer`.** Print this to chat first; memo-writer typically blocks the main session for many minutes (one IRAC block per issue), so the user needs explicit notice plus a pointer to live logs:

```
✍️ Drafting v1 of the memo. This is a long autonomous block — `memo-writer` will run silently for several minutes while it produces one IRAC section per issue. The chat will look quiet; that is expected. The next `**Progress —**` block will appear once the draft is written.

If you want to see live progress during this block, open `<state.json.rel_work_dir>/logs/memo-writer.log` — the writer appends a step entry before each issue (e.g. `step=issue-3-of-7`), so you can see exactly which section it is working on right now.
```

Substitute `<state.json.rel_work_dir>` with the actual short path before printing. Do NOT include specific wall-time estimates — duration varies with issue count, mode, and template.

Dispatch `memo-writer` via Agent tool. Pass:
- Path to working directory.
- Selected `template_id`.
- Path to `state.json` — **mandatory**, the writer reads `state.json.mode`, `state.json.config.template_id`, `state.json.config.max_iterations`, `state.json.intake.assumptions_accepted`, and `state.json.language` for mode-aware composition and assumption-disclosure obligations (per `agents/memo-writer.md` §Inputs (v1) and §Rules State-aware inputs).
- Paths to `plan.md`, intake files, research files, `research/research-sufficiency.json`, `research/currency-report.md` (human-readable view), `research/currency-report.json` (canonical machine-readable view, if present — memo-writer prefers it for status enum lookups; the `blocking[]` array is canonical for "do_not_use" source IDs the writer MUST avoid citing), and `research/source-pack.md`.
- Paths to house-style skill (`lib/prose-style.md`) and docx-render skill (`lib/docx-render/README.md`).

It writes `drafts/v1.md` and creates `changelog.md`. Set `state.json.current_draft_path = drafts/v1.md`, `current_phase = revision_loop`, `current_iteration = 1`.

**TodoWrite update.** Mark #10 ("Draft v1") = `completed`, #11 ("Revision loop") = `in_progress` (activeForm: `"Running revision loop (iteration 1)"`). Silent skip if unavailable.

Print a progress update with draft path, selected template, and that revision iteration 1 is starting.

