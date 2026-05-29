<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 2b — Parse intake response

On reactivation or the user's next chat message after the elicitation widget, parse the user response. Try parsers in this order — first match wins:

**Parser 1 — Elicitation format (`1A 2C 3D 4B` style; Path A response):**
- Detect: response contains a sequence of `<number><letter>` tokens (with optional `<number>:free-text` mixed in) separated by spaces, commas, or newlines.
- For each `<n><L>` token: look up question `n` in `intake-questions.json` (merged must_answer + optional, numbered in the order rendered in the widget), then look up option with `letter == L` from the letter-labeled list. Record `{question_text: option_label}`.
- For each `<n>:<text>` token: record `{question_text: text}` as a free-text answer (equivalent to "Other" in AskUserQuestion).
- For any must-answer question with NO token in the user's reply: apply the corresponding `default_assumptions_if_skipped` entry if present, otherwise flag as `unanswered_must_answer` and ask the user to fill in via /continue (do not silently proceed).
- For any optional question with NO token: apply the corresponding default assumption (or mark as "not provided" in user-facts.md).
- Write `intake/user-facts.md` with the Q/A pairs in the format documented below.
- Update `state.json.intake.user_response` = the parsed answer map, `state.json.intake.status = answered`, `state.json.current_phase = mode_pick_pending`. Append `intake_completed` event.
- If `state.json.config.visualize_enabled == true`, render the milestone-2 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "2 — Intake done"); graceful skip if disabled or call fails.
- **TodoWrite update.** Mark item #1 ("Intake") = `completed`, item #2 ("Mode pick") = `in_progress`. Silent skip if `TodoWrite` is unavailable.
- Continue inline to Phase 1.5.

**Parser 2 — Legacy `answer:` prefix (Path B text-fallback response):**
- Starts with `answer:` or `answers:` → treat the rest of the message as free-form intake; write `intake/user-facts.md` capturing the user's free text against the must-answer questions in order (best-effort match).
- Same state updates and milestone-2 rendering as Parser 1.

**Parser 3 — Proceed-on-assumptions:**
- Starts with `proceed` or `assume` → write `intake/user-facts.md` with "User chose to proceed on default assumptions" and copy `default_assumptions_if_skipped` into the file. Set `assumptions_accepted = true`, `state.json.intake.status = assumptions_accepted`, `state.json.current_phase = mode_pick_pending`. Render milestone-2 tracker as above. **TodoWrite**: mark #1 `completed`, #2 `in_progress`. Continue inline to Phase 1.5.

**Parser 4 — Cancel:**
- Starts with `cancel` → set `current_phase = cancelled_by_user`, print stop message, end turn.

**Parser 5 — Fallback (nothing matched):**
- Re-render the elicitation widget if visualize_enabled, or re-show `checkpoints/intake-questions.md` link if not. Print a short clarification: "Couldn't parse your reply. Use the format `1A 2C 3D` (one letter per question) or type `proceed` to run on defaults, or `cancel` to stop." End turn.

**user-facts.md format (used by all parsers):**

```markdown
# User intake — <task_id>

## Must-answer questions

### Q1: <question text>
**Answer:** <selected label, free text, or "default assumption applied: <text>">

<repeat for each must-answer item>

## Optional questions
<Either the user answered in the same Q/A shape, or:
"User chose to proceed on default assumptions. Applied assumptions:
1. <assumption>
2. ..." >
```

