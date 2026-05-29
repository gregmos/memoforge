<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 6 — Research sufficiency gate

Dispatch `research-sufficiency-reviewer` via Agent tool. Pass:
- `plan.md`
- `intake/fact-assumption-report.md`
- `intake/user-facts.md` if present
- All existing `research/*.md` files
- Working directory path

It writes `research/research-sufficiency.json`.

Read the JSON. Branch on `overall_verdict`:

- `overall_verdict = sufficient` → continue. No mode-driven override exists any more — the sufficiency reviewer's verdict is honoured verbatim.
- `overall_verdict = targeted_followup_needed` → **partition `blocking_gaps[]` by `target_agent`** into two subsets, then branch:
  - **Subset R** = entries with `target_agent ∈ {statutory-researcher, case-law-researcher, doctrinal-researcher}` — researcher-resolvable gaps.
  - **Subset U** = entries with `target_agent == "main-session"` — user-fact gaps (each MUST have a non-null `followup_question` block per `agents/research-sufficiency-reviewer.md` §"Generating followup_question for main-session gaps"; if any Subset U entry has `followup_question == null`, that is a reviewer-output bug — log a `research_sufficiency_schema_violation` warning event, treat the entry as if it were in Subset R with a `recommended_followup_prompt` fabricated from the `gap` text, and continue).

  Then read `state.json.attempts.research_followup` and apply ONE of these four branches:

  - **Branch B6a — Subset U non-empty AND `attempts.research_followup == 0`** (Phase 6.6 user-followup gate fires):
    1. Atomically `Edit` `state.json`:
       - `current_phase = "research_sufficiency_followup_pending"`
       - `attempts.research_followup = 1` (consumes the single follow-up budget)
       - `attempts.research_followup_pending_review = true`
       - Populate the new `sufficiency_followup` object (see `state-schema.md`):
         ```json
         "sufficiency_followup": {
           "status": "questions_pending",
           "questions": <Subset U entries augmented with sequential `question_number` starting at 1>,
           "subset_r": <Subset R as a separate array — researcher-resolvable gaps queued for re-dispatch after user replies; each item references the matching `issue_coverage[].recommended_followup_prompt`>,
           "user_response": null,
           "asked_at": "<NOW_ISO>",
           "answered_at": null
         }
         ```
    2. Append `research_followup_user_gate_started` event to `events.jsonl` with `{"main_session_gap_count": <len(Subset U)>, "researcher_gap_count": <len(Subset R)>, "research_followup_attempt": 1}`.
    3. Emit a `gate_announced` event (separate from above, follows the events-contract.md taxonomy) with `gate_name: "sufficiency-followup"`, `options_offered: ["letter-answers", "free-text", "proceed-on-defaults", "cancel"]`.
    4. **Path A (`state.json.config.visualize_enabled == true`)** — render the elicitation widget for Subset U follow-up questions:
       - Build the data payload per `skills/memo/references/widget-schemas.md §Sufficiency follow-up` (reuses §Elicitation shape). Letter-label each `options[]` entry (A/B/C/D) per question, in order.
       - Following the cached `elicitation` module guidelines, generate self-contained HTML/SVG (≤40 KB, no JavaScript callbacks).
       - Save snapshot to `$WORK_DIR/widgets/phase66-followup-elicitation.html`.
       - Call `<visualize_namespace>__show_widget` with the title / loading_messages / widget_code per `widget-schemas.md §Sufficiency follow-up`.
       - Append `visualize_widget_rendered` event with `{"phase": "6.6-followup", "module": "elicitation", "question_count": <len(Subset U)>}`.
       - Print the framing message + answer instructions to chat (always in English; verbatim structure — only placeholders change):
         ```
         Research surfaced <N> fact(s) the analysis still needs from you before drafting can proceed. The card below lays them out; pick a letter per question, or type your own answer. Skipping a question applies a conservative default assumption shown in the card.

         📄 Full sufficiency report: research/research-sufficiency.json (open via the artifact card above; plain path: <state.json.rel_work_dir>/research/research-sufficiency.json)

         👆 The follow-up card above shows the questions. Reply in chat with your answers:

         - **Follow-up answers** (questions 1..<N>): one letter per question, space-separated, in order. Example: `1A 2C 3B`.
         - **Free-text answer**: use `2:my custom text` (the question number, colon, then your text). Example: `1A 2:we use Azure OpenAI 3B`.
         - **Skip everything and run on default assumptions**: reply with just `proceed` (the memo will apply the default assumption shown for each question and continue to drafting).
         - **Cancel the task**: reply with just `cancel`.

         From another Cowork session: /memoforge:continue <task_id> followup: <answers>
         ```
    5. **Path B (`visualize_enabled == false` OR Path A widget call throws)** — text fallback:
       - Print the framing + question list as plain text:
         ```
         Research surfaced <N> fact(s) the analysis still needs from you before drafting. Each question is below with its options and the default assumption that will apply if you skip.

         📄 Full sufficiency report: research/research-sufficiency.json (plain path: <state.json.rel_work_dir>/research/research-sufficiency.json)

         Questions:

         **1. <question_text>** (rationale: <rationale_md>)
            A. <option label> — <option description>
            B. <option label> — <option description>
            ...
            Default if skipped: <default_assumption_if_skipped>

         <repeat for each Subset U question>

         Reply with one of:
         - `/memoforge:continue <task_id> followup: 1A 2C 3:my custom text` — provide answers
         - `/memoforge:continue <task_id> proceed` — skip all and apply defaults
         - `/memoforge:continue <task_id> cancel` — stop the task
         ```
    6. **End the assistant turn EXPLICITLY.** No inline-continue. No further tool calls. Control returns to the user. The next user message is parsed by `skills/continue/SKILL.md` §`research_sufficiency_followup_pending` handler (in-session or cross-session via `/memoforge:continue`).

  - **Branch B6b — Subset U empty AND `attempts.research_followup == 0`** (researcher re-dispatch path):
    Atomically increment `attempts.research_followup` to `1`, set `attempts.research_followup_pending_review = true`, append `research_followup_started` to `events.jsonl`, then re-dispatch researchers **proportionally per §"Proportional researcher re-dispatch (D)" below — do NOT blanket-re-run all researchers**, then re-run `research-sufficiency-reviewer` once and set `attempts.research_followup_pending_review = false`. If proportional scoping leaves zero researchers to re-dispatch (all gaps `weak`/informational → promoted to `drafting_warnings[]`), skip the researcher re-dispatch and the sufficiency re-run; proceed to currency_check.

  - **Branch B6c — `attempts.research_followup >= 1` and `attempts.research_followup_pending_review == true`** (resume after either user or researcher follow-up already happened): do NOT re-dispatch follow-up on resume. Re-run `research-sufficiency-reviewer` once against the current research files (which now include any newly-written `intake/user-facts.md` follow-up answers AND any re-dispatched researcher updates), then set `attempts.research_followup_pending_review = false`.

  - **Branch B6d — `attempts.research_followup >= 1` and `attempts.research_followup_pending_review == false`** (single follow-up budget consumed): do NOT re-dispatch follow-up. Treat remaining gaps as either `insufficient_for_client_ready_memo` or drafting warnings, using the sufficiency reviewer's latest JSON. If any Subset U gap remains and was not resolved (user provided no useful answer), promote it to `drafting_warnings[]` so the memo writer carries the assumption-based caveat into the draft.

  - **Proportional researcher re-dispatch (D — scope cost to gap severity).** Whenever Subset R (researcher-resolvable) gaps are sent back (Branch B6b, OR after a B6a user reply — same rule applies in the `skills/continue/SKILL.md` follow-up handler), do NOT blanket-re-run all researchers. The 2026-05-28 run spent ~21 min re-running 3 researchers for gaps the user had classified *informational* — poor ROI. Instead:
    - For each Subset R gap, read its `issue_coverage[].status`. **`missing`** (no source support; a conclusion cannot stand without it) → queue its `recommended_followup_prompt` for ONLY the named `target_agent`. **`weak`** (support exists but could be deeper) → do NOT re-dispatch; append the gap to `drafting_warnings[]` so the memo discloses it as a limitation.
    - If `state.json.sufficiency_followup.user_response.reply_scope == "informational"`, treat ALL Subset R gaps as `weak` — skip re-dispatch entirely, promote them to `drafting_warnings[]`, and proceed. (`consequential` / `mixed` / `not_sure` → apply the per-gap `missing`/`weak` rule above.)
    - Re-dispatch only the DISTINCT `target_agent`s that have ≥1 `missing` gap; each gets only its own gaps' prompts (never the full researcher set unless every researcher genuinely has a `missing` gap). If no `missing` gaps remain after partitioning, skip re-dispatch and go to currency_check with `drafting_warnings[]` recorded.
- `overall_verdict = insufficient_for_client_ready_memo` → continue only if the blocker is expressly disclosed in `drafting_warnings`; otherwise set `current_phase = failed`, write a short failure reason to state, and tell the user manual research or missing facts are required.

Before dispatching `currency-checker`, atomically update `state.json.current_phase = currency_check`.

**TodoWrite update.** Mark #6 ("Research sufficiency review") = `completed`, #7 ("Currency check of sources") = `in_progress`. Silent skip if unavailable.

Then dispatch `currency-checker` (single Agent call). It writes BOTH `research/currency-report.md` (human-readable) AND `research/currency-report.json` (machine-readable — canonical for downstream readers, per `skills/memo/references/pipeline-contract.md` Phase 6.5 outputs).
Print a progress update with the research sufficiency verdict, follow-up status, blocker count, and drafting warning count before moving on.

**Re-gate sufficiency on currency invalidation (Phase 6.5 → 6 loop, bounded).** After `currency-checker` returns, read `research/currency-report.json`. If `len(currency.blocking) > 0` AND `state.json.attempts.sufficiency_regate == 0`:
1. Append `currency_invalidated_sources` event to `events.jsonl` with the `blocking` array (source_ids).
2. Atomically: set `state.json.current_phase = research_sufficiency`, set `state.json.attempts.sufficiency_regate = 1`, set `state.json.attempts.research_followup_pending_review = false` (reset).
3. Re-dispatch `research-sufficiency-reviewer` ONCE against the post-currency source landscape (pass `research/currency-report.json` explicitly so it can treat `blocking` source_ids as removed from the pool).
4. Read the new `research/research-sufficiency.json`. Then handle the verdict per the Phase 6 branching above — `targeted_followup_needed` triggers the existing `research_followup` budget (NOT a second regate); `insufficient_for_client_ready_memo` either fails or proceeds with explicit `drafting_warnings`.
5. After the re-gate completes, set `current_phase = source_pack` and continue.

If `len(currency.blocking) == 0` OR `attempts.sufficiency_regate >= 1` (re-gate already used), skip the re-gate path: set `current_phase = source_pack` and continue directly.

**TodoWrite update** (either path). Mark #7 ("Currency check of sources") = `completed`, #8 ("Source pack assembly") = `in_progress`. Silent skip if unavailable.

After this block, print a progress update with blocking issue count and manual-check count read from `research/currency-report.json` (`len(blocking)` / `len(warnings)`) — not from the .md (parsing emoji is fragile fallback).

