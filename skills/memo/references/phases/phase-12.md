<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 12 — Return summary to user

**Visualize widget (final dashboard) — render BEFORE the text summary.**

If `state.json.config.visualize_enabled == true`:

a. Build the data payload per `skills/memo/references/widget-schemas.md §Final dashboard` (≤2KB JSON) from `state.json` + the source pack. Source counts: read `research/source-pack.md` and count by category. Final word count via `wc -w "<current_draft_path>"`. Duration: `(now - state.json.created_at)` in minutes.

b. Following the cached `data_viz` module guidelines, generate self-contained HTML/SVG (≤30KB) using the layout in `widget-schemas.md §Final dashboard`. No JavaScript callbacks.

c. Save to `$WORK_DIR/widgets/phase12-final-dashboard.html`. Call `<visualize_namespace>__show_widget` with the title / loading_messages / widget_code per `widget-schemas.md §Final dashboard`.

d. Append `visualize_widget_rendered` event per the same section.

If `visualize_enabled == false` or the call throws, skip silently — proceed straight to the text summary below.

**Print the final Progress block as plain text.** This is checkpoint #16 from the Required progress updates checklist. By this point, the `Read memo-<slug>.docx` and `Write memo-<slug>.md` calls from Phase 11 have inserted artifact cards above this message — the docx and its markdown mirror are the user's clickable access to the final memo.

```
**Progress — <task_id>**
- Current phase: `done`
- Completed: Memo exported (`<final_status>` on v<N>)
- Next: Review the docx (artifact card above) and the audit trail
- Notes: <selected_template_id>; <N> statutes / <M> cases / <K> doctrine items; <I> revision iterations; plan <edited|unchanged>
```

Then, immediately below the Progress block (same message or a follow-up), append a delivery summary as plain text:

```
📄 Final memo: memo-<slug>.docx (see Read artifact card above; markdown mirror also available as memo-<slug>.md)
📁 Audit trail: <state.json.rel_work_dir>/ — plan.md, intake answers, research, source pack, every draft (v1-v<N>), reviewer reports, mediator briefs, events.jsonl, state.json all live in this single folder

<Memo summary — 3-5 sentences in the user's language, describing what the memo concludes>

Template used: <selected_template_id>
Status: <approved on v<N> | forced exit on v<N> with N blocking issues remaining | manual review required on v<N>>
Stats: <N> statutes / <M> cases / <K> doctrine items found; <I> revision iterations; plan <edited|unchanged>
```

If status is `forced exit` or `manual review required`, add a final line directing the user to the mediator brief as plain text (the user can open the file from the work directory):

```
Open the blockers list at reviews/v<N>-mediator.md to see the remaining issues.
```

Do not wrap any of these file references in markdown links — they don't render as clickable in Cowork. The user already has artifact cards (from Read/Write tool calls) for the docx and markdown mirror; for other files in the audit trail, they navigate from the work directory.

**Final TodoWrite update.** Mark #14 ("Finalize and summarize") = `completed`. All 14 items should now be `completed`. The side panel shows the full pipeline as completed. Silent skip if `TodoWrite` is unavailable.

