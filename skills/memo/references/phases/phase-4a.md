<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 4a — Run interactive plan approval (preferred) or fall back to text

Path selection is identical to Phase 2a: try interactive first, fall back to text if AskUserQuestion is unavailable in the host.

### Path A — Interactive plan approval via AskUserQuestion (happy path)

1. Print a compact summary block in chat. Do **NOT** dump the full plan.md content inline — Cowork's chat renderer strips `<details>`/`<summary>` HTML tags inconsistently, leaving the entire plan as a wall of text without folding. Instead, print:
   - A 2-4 sentence executive summary (classification, jurisdictions, issues short list, researchers to run, mode).
   - A plain-text reference to `plan.md` (per D2 — clickability comes from the artifact card produced by the `Write plan.md` tool call earlier in this phase; markdown link syntax in chat text does NOT make file paths clickable in Cowork).
   - 5-8 bullet "what's in the plan" preview so the user can decide without opening the file.

   Required format (verbatim structure — only the placeholders change):

   ````
   Research plan for `<task_id>`: <classification>, <jurisdictions>, <N> issues, <M> researchers, mode=<mode>.

   📄 Open full plan: plan.md (see artifact card above; full path: <state.json.rel_work_dir>/plan.md)

   **Plan at a glance:**
   - **Issues (<N>):** <short comma list of issue titles, ≤80 chars total>
   - **Researchers:** <set from config.researcher_set>
   - **Template:** `<selected_template_id>` (forced / bounded / open per mode)
   - **Doctrine:** <yes/no + 1-line reason>
   - **Sources:** <hierarchy short summary, 1 line>
   - **Critical missing facts:** <count, or "none flagged">
   - **Assumptions adopted:** <count>
   ````

   Notes on the format:
   - File reference rule D2 applies — `plan.md` is plain text, clickability comes from the `Write plan.md` artifact card above this message. See `progress-contract.md` §"How file references work in Cowork".
   - **Do NOT inline the full plan.** The visualize widget below (step 1b) plus the artifact card replaces what the old `<details>` block tried to do. Users who want full audit text click the artifact card; users who want a visual map see the diagram widget; users who want a quick decision read the 5-8 bullet preview.
   - If `visualize_enabled == false`, the bullet preview is the user's only summary — make sure it's substantive enough to support an Approve/Edit decision.

**1b. Visualize widget (plan diagram) — render AFTER the summary block, BEFORE `AskUserQuestion`.**

If `state.json.config.visualize_enabled == true`:

a. Build the data payload per `skills/memo/references/widget-schemas.md §Plan diagram` (≤2KB JSON) from `plan.md` + `state.json.classification`. Keep issue titles tight (≤60 chars); fall back to plain enumeration if `plan.md` doesn't expose clean titles.

b. Following the cached `diagram` module guidelines, generate self-contained HTML/SVG (≤40KB) using the layout in `widget-schemas.md §Plan diagram`. No JavaScript callbacks.

c. Save to `$WORK_DIR/widgets/phase3-plan-diagram.html`. Call `<visualize_namespace>__show_widget` with the title / loading_messages / widget_code per `widget-schemas.md §Plan diagram`.

d. Append `visualize_widget_rendered` event per the same section.

If `visualize_enabled == false` or the call throws, skip silently. The bullet preview + `plan.md` artifact card from step 1 above already give the user access to the full plan content (Cowork strips `<details>` HTML inconsistently, so the old `<details>` collapsible was removed — never inline `<details>` here, even as a fallback). The diagram widget is a visual complement, not a replacement.

2. Call AskUserQuestion (single question):
   - `question`: "Research plan is ready. What's next?"
   - `header`: "Plan review" (must be ≤12 chars).
   - `multiSelect`: false.
   - `options`:
     - label: "Approve plan", description: "Dispatch researchers as planned and proceed to Phase 5"
     - label: "Request edits", description: "Next prompt collects your edit instructions"
     - label: "Cancel task", description: "Stop the pipeline; work directory persists, resumable with /continue"

3. Branch on the answer:

   - **Approve picked** → set `state.json.plan_approval.status = approved`, `final_plan_iteration = <current>`, `current_phase = research`. Print a progress update summarizing classification, selected template, and researchers to run. Append `plan_approved` to `events.jsonl`. **Also emit a `gate_answered` event** per `events-contract.md` (canonical gate-audit shape):
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
       --workdir "$WORK_DIR" --event gate_answered --phase research --actor memo-skill \
       --data '{"gate_name":"plan-approval","options_offered":["Approve plan","Request edits","Cancel task"],"chosen":"Approve plan","was_fallback":false,"fallback_reason":null}'
     ```
     If `state.json.config.visualize_enabled == true`, render the milestone-3 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "3 — Plan approved"); save snapshot to `$WORK_DIR/widgets/progress-03-plan-approved.html`; graceful skip if disabled or call fails. **TodoWrite update.** Mark item #4 ("Plan approval") = `completed`, item #5 ("Parallel research") = `in_progress`. Silent skip if unavailable. **Continue inline to Phase 5 — no end-turn.**

   - **Cancel picked** → set `plan_approval.status = cancelled`, `current_phase = cancelled_by_user`. Print: "Pipeline stopped. Working directory preserved at <state.json.rel_work_dir>/ (plain text path — open from the Cowork file viewer). Resume with: `/memoforge:continue <task_id>`." End turn.

   - **Request edits picked** → check `max_plan_edit_iterations` (default 5). If exceeded, print "Edit iteration limit reached. Please approve or cancel." and re-ask the previous AskUserQuestion (without the Edit option). Otherwise, run the **edit collection** step:

     Call AskUserQuestion (second question):
     - `question`: "Which edits to the plan? Pick an option or enter your own text via 'Other'."
     - `header`: "Edits" (≤12 chars).
     - `multiSelect`: false.
     - `options`:
       - label: "Add or remove jurisdiction", description: "Extend or narrow the geographic scope of the analysis"
       - label: "Add or remove research issue", description: "Change which legal questions are analyzed"

     There is no template-switch edit option: template is bound to mode (Brief → executive-brief, Full → classical-memo) and cannot be changed mid-task. If the user wants a different template, they cancel and rerun in the other mode.

     Capture the answer:
     - If label is one of the two preset categories, treat it as the edit *category*. If the user's intent needs specifics (e.g. "which jurisdiction?"), call ONE follow-up AskUserQuestion to narrow it down (e.g. options "Add Cyprus", "Add US", "Remove Switzerland", with auto-Other for free text). Apply the resulting edit to `plan.md`.
     - If the user picked "Other" with free text, use that text verbatim as the edit instructions and apply to `plan.md`.

     Then:
     1. Apply edits to `plan.md` (use Edit tool).
     2. Append new iteration to `checkpoints/plan-approval.md`.
     3. Update `state.json.plan_approval.iterations` with the new iteration metadata.
     4. **Watch for template conflicts in Brief mode**: if edits expand scope beyond `executive-brief`'s 1200-word cap (e.g. user adds a new issue or jurisdiction that pushes total analysis past the cap), warn in the updated plan.md: "**Warning:** edits expand scope relative to `executive-brief` cap. Consider cancelling and rerunning in Full mode for full classical-memo treatment."
     5. Loop back to step 1 of Path A (re-summarize the updated plan and re-ask the verdict question). No end-turn.

### Path B — Text fallback (rescue / legacy / host without AskUserQuestion)

If AskUserQuestion is unavailable in the current host or the call fails, fall back to the original text prompt and end turn.

Print to chat:
```
Research plan ready: plan.md (see the artifact card above if plan.md was just created via Write, otherwise open the file at <state.json.rel_work_dir>/plan.md)

Review and confirm with one of these (the reliable form is via explicit resume):
- `/memoforge:continue <task_id> approve` — proceed as is
- `/memoforge:continue <task_id> edit: <instructions>` — apply edits
- `/memoforge:continue <task_id> cancel` — stop

If you are still in the same Cowork session, the short replies `approve`, `edit: <instructions>`, and `cancel` may be picked up automatically. If not, use `/memoforge:continue <task_id> ...`.

Awaiting your reply.
```

**STOP. End your turn.** Do not call any Agent tools. State is persisted; Phase 4b will pick up the user's response.

