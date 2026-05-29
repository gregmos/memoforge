<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 7.5 — Source-review checkpoint (END THE TURN here)

**This is the single most important UX point in the pipeline.** Phase 5 dispatched parallel researcher Tasks, and Phases 6 / 6.5 / 7 ran inline immediately after — all in the same assistant turn. Per documented Cowork behaviour (issues #26805 / #29773 / #29547 / #33564 / #44776), assistant text and AskUserQuestion modals fired in this state are buffered and not visible until end-of-turn or user input. **The fix is to explicitly END THE ASSISTANT TURN here**, which is Cowork's only documented mid-pipeline flush trigger. Once the turn ends, Cowork paints all queued Progress blocks from Phases 5 → 6 → 6.5 → 7, plus the source-review digest below.

Do NOT call `AskUserQuestion` at this checkpoint — it has been observed to silently fail post-parallel-Task in plugin-skill context. The earlier `Phase 2a` migration to `visualize:show_widget` for the intake gate documents the same pattern (see `references/phases/phase-2a.md` and `agents/fact-assumption-analyst.md`). The user has also confirmed that `visualize:show_widget` ALSO does not render post-parallel in our pipeline, so widget swap is not an option here either — plain text + explicit end-turn is the only reliable mechanism.

Steps:

1. **Read source-pack and currency-report files** into the turn so they appear as Cowork artifact cards above the next assistant message:

   ```
   Read research/source-pack.md
   Read research/currency-report.md
   ```

2. **Print the source-review digest + checkpoint instructions as plain assistant text.** Use this exact shape (substitute counts and titles from the source pack):

   ```
   **Progress — <task_id>**
   - Current phase: `source_review_pending`
   - Completed: Research, sufficiency, currency, and source-pack all done
   - Next: Awaiting your reply (`continue` to draft, `cancel` to stop)
   - Notes: <X> statutes / <Y> cases / <Z> doctrine items; <N> evidence rows; <K> contrary-authority rows; <M> do-not-use; <P> manual-check; <Q> blocking-currency

   📋 Source pack ready — review before drafting.

   Top sources (most load-bearing, from `research/source-pack.md` artifact card above):
   - <Source title 1> — <one-line relevance>
   - <Source title 2> — <one-line relevance>
   - <Source title 3> — <one-line relevance>
   - <Source title 4> — <one-line relevance>
   - <Source title 5> — <one-line relevance>
   (Full evidence table: <N> rows in `source-pack.md`.)

   Reply with one of:
   - `continue` — proceed to drafting (memo-writer + revision loop + client-readiness + export)
   - `cancel` — stop here; the work directory and source-pack remain for later use

   From another Cowork session: /memoforge:continue <task_id> continue
   ```

   The 5 "top sources" lines are picked by the orchestrator from `source-pack.md` evidence-row order (the source-pack-builder orders by load-bearing weight per `agents/source-pack-builder.md` — pick the first 5). If the pack has fewer than 5 rows, list all available.

3. **Emit a `gate_announced` event** (audit log, distinct from `gate_answered` which fires when the user replies in the next turn):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
     --workdir "$WORK_DIR" --event gate_announced --phase source_review_pending --actor memo-skill \
     --data '{"gate_name":"source-review","options_offered":["continue","cancel"]}'
   ```

4. **End the assistant turn EXPLICITLY.** No inline-continue to Phase 8. No AskUserQuestion call. No further tool calls. The skill execution ends; control returns to the user.

   The user's next chat message is parsed by Phase 8 (in-session resume) or by `skills/continue/SKILL.md` (cross-session resume via `/memoforge:continue <task_id> [continue|cancel]`).

**Why no AskUserQuestion here:** the question is two-option (`continue` / `cancel`) and text-parsable. Adding an AskUserQuestion call on top of the text instructions risks the silent-fail behaviour documented in issue #29773 (modal exists in DOM but isn't painted), which would leave a Cowork user uncertain whether the modal failed or is just slow. Plain text instructions, post-end-of-turn-flush, are unambiguous.

**Legacy compatibility.** Tasks created on v0.0.42 or earlier may have `current_phase == heartbeat_pending` and possibly `state.json.heartbeat_choice` set. `skills/continue/SKILL.md` migrates them to `source_review_pending` on resume (drops the `heartbeat_choice` field), so the v0.0.43 source-review checkpoint becomes the resume target for those tasks too.

