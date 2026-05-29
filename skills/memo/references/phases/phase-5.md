<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 5 — Parallel research

Set `current_phase = research`.

**Anti-inline guard (hard rule).** Phase 5 research MUST be performed by researcher subagents dispatched via the `Agent` tool. The main session MUST NOT call `WebSearch`, `WebFetch`, or any MCP search tools directly during Phase 5. Specifically:

- Do NOT call `WebSearch` from the main session at any point in Phase 5. WebSearch IS available to researcher subagents now (as a discovery tool, per each researcher's "WebSearch discovery boundaries" section), but the discipline of canonical-source citation belongs in the subagent's audited Methodology — not in the orchestrator's untracked main-thread calls.
- Do NOT call `WebFetch` from the main session in Phase 5 — researchers have their own WebFetch policy and source-discovery discipline.
- Do NOT call MCP search/get_document tools from the main session in Phase 5.
- Do NOT rationalize that "MCPs are unavailable so I'll just do the research inline" or "official EU portals are canonical so I don't need the MCP" or "WebSearch is fine for me to call directly" — those decisions belong to the researcher subagent, not the orchestrator.

If you find yourself reaching for a research tool directly from the main session in Phase 5, stop and dispatch the appropriate researcher subagent instead. The only research-adjacent reads allowed inline are `Read` of files already in the working directory.

**Heads-up message BEFORE dispatching researchers.** Print this to chat first, then dispatch in the next turn. Cowork batches text blocks emitted between tool calls; this upfront message is the user's only signal that a long autonomous block is starting:

```
🔎 Dispatching **<N> parallel researcher agents** (<list>). This is an autonomous block of several minutes. Cowork may show only 1 agent tile in the chat at first — the others will appear as they return. Per-agent progress is visible in the task panel on the right (3 sub-items appear under "Parallel research"); for raw step-level logs see `<state.json.rel_work_dir>/logs/<agent>.log`. The `<work_dir>/events.jsonl` file is a separate orchestrator-level audit log.
```

Substitute `<N>` with `len(state.json.dispatched_researchers)`, `<list>` with the agent names joined by `+` (e.g. `statutory + case-law + doctrinal`), and `<state.json.rel_work_dir>` with the actual short path. Do NOT include specific wall-time estimates — real durations vary widely and stale numbers mislead the user. The explicit `<N> parallel` count and the "Cowork may show only 1 tile" caveat are critical — without them, users with a Cowork UI quirk see one tile and think only one agent is running.

**Also append this paragraph to the heads-up** — it pre-warns the user about the v0.0.43 mid-pipeline flush behaviour AND the v0.0.44 autonomous post-source-review block, so they understand what to expect:

```
After research completes, the chat will appear quiet through the sufficiency check, currency check, and source-pack assembly — those phases run silently in the same assistant turn because Cowork only flushes chat at end-of-turn (documented host behaviour, see issues #26805 / #29773 family). The pipeline then stops at a source-review checkpoint where the assistant turn ENDS explicitly. At that point Cowork flushes everything and you will see the full Progress audit trail plus the source-pack digest at once. Reply `continue` to proceed to drafting, or `cancel` to stop. The TodoWrite panel item #9 reflects the live state throughout.

If the sufficiency reviewer surfaces facts that the analysis still needs from you (rather than from more research), the pipeline may also stop ONE more time at a Phase 6.6 follow-up gate BEFORE the source-review checkpoint — same end-of-turn flush mechanism, with a short elicitation widget asking the missing facts. Reply with letter answers (`1A 2C`), free-text (`1:my custom answer`), `proceed` to accept defaults, or `cancel`. This gate fires at most once per run (capped by the `research_followup` budget) and is silent when no user-facing gaps remain.

After `continue` at source-review, the pipeline runs fully autonomously through drafting, revision loop (up to <max_iterations> iterations), client-readiness review, optional polish, and docx export — ALL in one assistant turn with NO further user gates (per v0.0.44 — gates were removed because they hit the same Cowork silent-fail bug after parallel Tasks). Expect ~15-40 minutes of visual silence in chat during this block. Monitor real-time progress via the task panel on the right: items #10 (Draft v1), #11 (Revision loop), #12 (Client-readiness review), #13 (Export to docx), #14 (Finalize) advance through the phases. The chat flushes the complete audit trail at end-of-turn when the final docx is written.
```

**TodoWrite + mark_chapter BEFORE the heads-up.** Issue these in the same assistant message as the heads-up text (so the side panel updates BEFORE the long parallel block starts):

- `TodoWrite`: mark #5 ("Parallel research") = `in_progress` (already done at Phase 4 approve, but re-affirm). **Add N sub-items** right under #5 — one per researcher in `dispatched_researchers`:
  - `"  · statutory-researcher"` / activeForm `"Running statutory-researcher"` = `in_progress`
  - `"  · case-law-researcher"` / activeForm `"Running case-law-researcher"` = `in_progress` (only if in `dispatched_researchers`)
  - `"  · doctrinal-researcher"` / activeForm `"Running doctrinal-researcher"` = `in_progress` (only if in `dispatched_researchers`)
  
  The leading two spaces visually nest the sub-items in the panel. These sub-items are the user's primary signal that N agents are running in parallel.
- `mcp__ccd_session__mark_chapter(title="Parallel research", summary="<N> researchers dispatched in parallel")`. Silent skip if unavailable.

Read `plan.md` for issues, jurisdictions, and the doctrine flag.

**Compute `dispatched_researchers` first** (subset of the candidate `state.json.config.researcher_set`, filtered by plan):
- `statutory` — always dispatched.
- `case-law` — dispatched if it is in `config.researcher_set` (skipped in Brief mode where the candidate set is `["statutory"]`).
- `doctrinal` — dispatched if it is in `config.researcher_set` AND plan says `Doctrine: yes`. If `Doctrine: no`, doctrinal stays in the CANDIDATE set (`config.researcher_set` is not mutated) but is omitted from the dispatch.

Write the filtered list to `state.json.dispatched_researchers` BEFORE the parallel Agent dispatch (atomic state write). This makes the candidate-vs-dispatched distinction visible in state, in audit events, and to the validator.

Dispatch researchers in **one message with multiple Agent tool calls in parallel** — one Agent call per item in `state.json.dispatched_researchers`.

**Dispatch ALL researchers in `dispatched_researchers` in the SAME assistant message, even if you suspect MCP services may be rate-limited or partially unavailable.** Rate limits and per-service outages are handled INSIDE each researcher via the `skills/memo/references/mcp-ratelimit-contract.md` fallback (WebSearch + WebFetch on canonical URLs). The orchestrator does NOT skip a researcher dispatch on suspicion of throttling, and does NOT serialize dispatches to "spread load". The malformed-check is: number of Agent tool calls in your message == `len(state.json.dispatched_researchers)`. A legitimate `Doctrine: no` skip is NOT malformed because doctrinal was already excluded from `dispatched_researchers` upstream.

Pass each researcher: path to `plan.md`, the working directory path, the relevant issue list, the MCP detection result from Phase 1 precheck (which prefix to use for LDH / CourtListener), and a reminder to follow both the MCP-first contract AND the MCP rate-limit fallback contract in the researcher's own agent file. They write `research/statutes.md`, `research/case-law.md`, `research/doctrine.md` respectively.

Append a `phase5_dispatch` event to `events.jsonl` with `{"candidate": <config.researcher_set>, "dispatched": <state.json.dispatched_researchers>, "skipped": <set_difference>, "skip_reasons": {"doctrinal": "plan.doctrine_required=false"}, "timestamp": "<ISO>"}`. If `events.jsonl` shows no `phase5_dispatch` event after this phase, the pipeline is malformed — surface to the user and stop.

**Per-researcher dispatch events** (in addition to the aggregated `phase5_dispatch`). Per `events-contract.md` §"agent_dispatched / agent_returned", emit one `agent_dispatched` event BEFORE each researcher's `Task(...)` call and one `agent_returned` AFTER it returns, using a unique `dispatch_id` to pair them (e.g. `phase5-statutory-1`):

```bash
# Before dispatch
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
  --workdir "$WORK_DIR" --event agent_dispatched --phase research --actor memo-skill \
  --data '{"subagent_type":"statutory-researcher","purpose":"initial-research","expected_outputs":["research/statutes.md"],"dispatch_id":"phase5-statutory-1"}'

# After return (compute duration_seconds from the Bash timestamp delta)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
  --workdir "$WORK_DIR" --event agent_returned --phase research --actor memo-skill \
  --data '{"subagent_type":"statutory-researcher","dispatch_id":"phase5-statutory-1","duration_seconds":47.3,"outputs_written":["research/statutes.md"],"final_response_summary":"<≤120 chars>"}'
```

Wait for all researchers to complete (Agent tool calls block until each subagent returns).

**Post-return: check for MCP rate-limit fallback events.** After all researchers return, grep `events.jsonl` for `mcp_ratelimit_fallback` entries. If any are present, push the rate-limit banner from `skills/memo/references/always-deliver.md` Phase 5 row into `state.json.fallback_banners[]` (de-duplicated — push only one entry per task even if multiple researchers fell back). Mention the fallback in the next Progress block's `Notes:` field (which researcher(s) fell back, what items_fallback counts were).

Update `state.json.current_phase = research_sufficiency`.

**TodoWrite update.** Mark all Phase 5 sub-items (`statutory-researcher`, `case-law-researcher`, `doctrinal-researcher` — those that were dispatched) = `completed`. Mark #5 ("Parallel research") = `completed`. Mark #6 ("Research sufficiency review") = `in_progress`. Silent skip if unavailable.

Print a chat Progress block listing the research files produced and any explicit gaps. Phrase it so it is clear that all N researchers ran AND returned in parallel — do NOT use sequential language like "case law done, now doctrinal" (the agents finished simultaneously). Use this prescriptive shape:

```
**Progress — <task_id>**
- Current phase: `research_sufficiency`
- Completed: All <N> researchers returned in parallel — statutes.md (<lines> lines), case-law.md (<lines>), doctrine.md (<lines> — if dispatched)
- Next: Research sufficiency review
- Notes: <gaps each researcher flagged in its final_response_summary>
```

