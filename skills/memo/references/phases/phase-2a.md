<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 2a — Run interactive intake (preferred) or fall back to text

Before asking anything, check whether `checkpoints/intake-questions.json` exists and is valid strict JSON with the schema documented in `agents/fact-assumption-analyst.md`. Branch on that.

### Path A — Visualize elicitation primary intake (when visualize_enabled)

**Why this is the primary path now.** Cowork's `AskUserQuestion` modal for intake (multiple questions with rich descriptions) has been observed to fail silently in production runs: the permission stream throws "permission stream failed", pills render as "Dismissed" without user interaction, and the framing message only flushes to chat AFTER the user presses Stop. Switching intake to `visualize:show_widget` with the `elicitation` module — rendering all questions as a single visual card with letter-labeled options, and parsing the user's chat text reply — is the reliable primary path. AskUserQuestion stays only for single-question gates (Phase 1.5 mode, Phase 4a plan approval) where the smaller payload renders reliably.

This path runs when `state.json.config.visualize_enabled == true` AND `intake-questions.json` exists and parses cleanly. If visualize is disabled, fall through to Path B (text fallback) — there is no AskUserQuestion-based intake any more.

1. Read both `intake-questions.json` and `intake-questions.md`.

**1a. Defensive validation and sanitization.** Walk every entry in `must_answer` and `optional`:
- If `header` length > 12 chars: shorten it in-place (drop articles, prepositions, plus-signs; replace " + " with "/"; cap at 12 chars). Log the original→sanitized pair as a `header_sanitized` event in `events.jsonl`. Examples: `"Art. 27 + DPIA"` (14) → `"Art27/DPIA"` (10); `"Special category"` (16) → `"Special cat."` (12).
- If `options` array has <2 items: skip that question entirely and add it to `default_assumptions_if_skipped` instead (log `question_skipped_invalid_options`).
- If `options` array has >4 items: keep the top 4 by descriptive distinctiveness and move the rest to the rationale_md. Log `options_truncated`.
- If any `description` exceeds 200 chars: truncate to 200 chars with a trailing period. Log `description_truncated`.
After sanitization, the JSON in memory is what you pass to the widget below — do NOT re-write the file on disk.

**1b. Build the elicitation data payload** per `skills/memo/references/widget-schemas.md §Elicitation` (≤4 KB JSON). Letter-label each option (A/B/C/D in order) and merge must-answer + optional into a single ordered list with question numbers.

**1c. Render the elicitation widget.** Following the cached `elicitation` module guidelines (from `visualize:read_me` in Phase 1), generate a self-contained HTML/SVG widget using the layout in `widget-schemas.md §Elicitation` (≤40 KB, no JavaScript callbacks).

Save snapshot to `$WORK_DIR/widgets/intake-elicitation.html`. Call `<visualize_namespace>__show_widget` with the title / loading_messages / widget_code per `widget-schemas.md §Elicitation`. Append `visualize_widget_rendered` event per the same section.

**1d. Print the framing message + answer instructions to chat.** Always in English. Required format (verbatim structure — only placeholders change):

```
I ran a preliminary legal triage and found <N> must-answer + <M> optional facts that materially change the analysis. The card below lays them out; pick a letter per question. The triage report has the full rationale.

📄 Full triage report: intake-questions.md (open via the artifact card above; plain path: <state.json.rel_work_dir>/checkpoints/intake-questions.md)

👆 The elicitation card above shows the questions. Reply in chat with your answers:

- **Must-answer** (questions 1..<N>): one letter per question, space-separated, in order. Example: `1A 2C 3D 4B`.
- **Optional** (questions <N+1>..<N+M>): include if you want to sharpen the memo, skip if not. Example: `5A 7C` (skipping 6, 8, 9).
- **Free-text "Other" answer**: use `2:my custom text` (the question number, colon, then your text). Example: `1A 2:we use Azure OpenAI 3D 4B`.
- **Skip everything and run on default assumptions**: reply with just `proceed`. The memo will run on the conservative defaults shown in the card.
- **Cancel the task**: reply with just `cancel`.
```

(File-reference rule D2 applies — see `progress-contract.md` §"How file references work in Cowork". File paths in chat are plain text; clickability comes from the artifact card produced by the earlier `Write checkpoints/intake-questions.md` call.)

**1e. End turn.** Phase 2b will pick up the user's chat-text answer. Do NOT loop back, do NOT wait for AskUserQuestion-style structured response.

### Path B — Text fallback (rescue / legacy / agent failure)

If `intake-questions.json` is missing, empty, or fails JSON parse:

1. Print the framing text and pointer to `checkpoints/intake-questions.md` (current behaviour):
   ```
   Preliminary legal triage found facts the memo needs to avoid being too conditional.

   Full report: intake-questions.md (see artifact card above; plain path: <state.json.rel_work_dir>/checkpoints/intake-questions.md)

   Reply with one of:
   - `/memoforge:continue <task_id> answer: <your answers>` — add facts
   - `/memoforge:continue <task_id> proceed` — proceed on the proposed assumptions
   - `/memoforge:continue <task_id> cancel` — stop the task
   ```

   The path reference is plain text (file-reference rule D2 — see `progress-contract.md` §"How file references work in Cowork").
2. **STOP. End your turn.** Phase 2b will pick up the user's `/continue` response.

The text path is the safety net — keep it working so older in-flight tasks (without JSON) and any environment where visualize is not available still complete. Enter Path B when EITHER:
- `visualize_enabled == false` (the host has no visualize widget surface — visualize-less Claude Code installs, hosts where the precheck failed), OR
- `intake-questions.json` is missing, empty, or fails strict JSON parse (legacy task, agent failed to emit the JSON, or content corrupted).

This is an OR, not an AND — a host without visualize but with a valid JSON file still goes through Path B, since the Path A widget cannot render without visualize. Without this rule a non-visualize host with valid intake would hang with no progress path forward. The default primary path is Path A (visualize elicitation) when visualize is enabled and the JSON is valid; Path B is the catch-all for every other case.

