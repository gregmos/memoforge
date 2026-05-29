<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 11 — docx export

Read `state.json` for `work_dir`, `classification.selected_template_id`, `final_status`, and the path to the final draft `drafts/vN.md`.
Print a progress update before export with final draft path, final_status, and the work_dir path (which IS the user-visible output folder for this task — there is no copy step).

Run via Bash. The docx is written directly to `<work_dir>/memo-<slug>.docx` — the same directory where all other artifacts live. No staging, no copy:

```bash
WORK_DIR="<state.json.work_dir>"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/docx-render/scripts/md_to_docx.py" \
  --input "$WORK_DIR/drafts/v<N>.md" \
  --output "$WORK_DIR/memo-<slug>.docx" \
  --template-id <selected_template_id> \
  --final-status <final_status> \
  --state "$WORK_DIR/state.json" \
  --language en
```

The plugin is English-only — always pass `--language en`. The `language` field in `state.json` is fixed to `en`.

If the script fails:
1. Try `pandoc "$WORK_DIR/drafts/v<N>.md" -o "$WORK_DIR/memo-<slug>.docx"` as best-effort fallback. Pandoc is not guaranteed in Cowork/Claude Code; expect failure if it's missing.
2. **If pandoc also fails — deliver the markdown as the final artifact** (per `skills/memo/references/always-deliver.md` Phase 11 row, which IS the canonical contract for this fallback):
   a. Resolve the source draft deterministically (the no-polish path does NOT produce `v<N>-client-ready.md`): (1) if `drafts/v<N>-client-ready.md` exists for the highest N, use it; (2) else use `state.json.current_draft_path` (which always points at the latest `drafts/v<N>.md` after Phase 8 / 9); (3) else `ls $WORK_DIR/drafts/v*.md` and pick the highest-N file. Then copy to the canonical artifact filename: `cp "<resolved source>" "$WORK_DIR/memo-<slug>.md"`.
   b. Update `state.json.final_docx_path` to the absolute path of the `.md` file (i.e. `<work_dir>/memo-<slug>.md`). The field name `final_docx_path` is preserved for schema stability; the extension is `.md` instead of `.docx`.
   c. Push the banner string `"docx export failed — markdown file delivered. Convert manually with pandoc or save-as docx."` to `state.json.fallback_banners[]` (dedupe — push only once).
   d. Set `state.json.final_status` and `state.json.current_phase = done`.
   e. Call `Read` on `<work_dir>/memo-<slug>.md` so Cowork inserts an artifact card.
   f. Print the final Progress block; mention the banner in `Notes:`.

   Do NOT leave the pipeline with `final_docx_path = null` and only a chat message — that violates the `always-deliver.md` invariant "the user must always see a final chat message and a file at the documented output path".

**No copy step (success path).** All artifacts already live at the user-visible `$WORK_DIR` (resolved at Phase 1 to the user's chosen output folder or the sandbox-accessible `outputs/memoforge-work/<task_id>/`). The final docx joins them in the same folder. The user can browse to that folder at any time during or after the run. The markdown-fallback `cp` above is intra-`$WORK_DIR` only — it just renames the latest draft to the canonical artifact filename so downstream tooling (Read tool / artifact card / state.json) sees a stable path.

**Emit a `phase_transition` event** to mark docx delivery (per `events-contract.md`):

```bash
# On success path (docx written by python-docx OR pandoc):
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
  --workdir "$WORK_DIR" --event phase_transition --phase done --actor memo-skill \
  --data '{"from":"export","to":"done","reason":"docx_written"}'

# On markdown-delivery fallback:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/log_event.py" \
  --workdir "$WORK_DIR" --event phase_transition --phase done --actor memo-skill --severity warn \
  --data '{"from":"export","to":"done","reason":"markdown_fallback_written"}'
```

Update `state.json`: `final_status`, `final_docx_path = "$WORK_DIR/memo-<slug>.docx"` (absolute path equal to `<work_dir>/memo-<slug>.docx`; on the markdown fallback path above the extension is `.md`), `current_phase = done`. Close the prior timeline entry (`export`) by setting its `completed_at_iso` and append a new entry `{"phase":"done","started_at_iso":"<now>","completed_at_iso":null}` to `state.json.live_progress.timeline`. Also set `state.json.live_progress.phase_started_at_iso = "<now>"`. If `state.json.config.live_progress_enabled == true`, re-render and `mcp__cowork__update_artifact`. The legacy `final_artifacts_dir` field is removed — the audit trail folder IS `work_dir` itself.

**TodoWrite update.** Mark #13 ("Export to docx") = `completed`, #14 ("Finalize and summarize") = `in_progress`. Silent skip if unavailable.

### Make the docx visible to Cowork (critical UX step)

The docx was created by a Python `Bash` subprocess (`md_to_docx.py`), not by a native `Write`/`Edit` tool — so Cowork's UI does **not** automatically render an artifact card for it. Without the steps below, the user has no clickable affordance for the docx; they would have to find it in the file viewer manually.

After the script succeeds:

1. **Read the docx with the `Read` tool.** `Read` is a native Anthropic tool that Cowork tracks. Calling it on `<work_dir>/memo-<slug>.docx` lets Cowork's UI register the file's existence and (in many cases) render an artifact card linking to it. This is cheap (no content piped to chat — `Read` on a docx returns parsed metadata) and is the primary mechanism we rely on.
2. **Write a markdown mirror via the `Write` tool.** Copy the final draft content (the same `drafts/v<N>-client-ready.md` or `drafts/v<N>.md` source) to `<work_dir>/memo-<slug>.md` using the `Write` tool. Markdown files reliably get artifact cards from Cowork. This gives the user a guaranteed-clickable preview of the same memo content in plain markdown form even if the docx card from step 1 fails to render.

Both steps add roughly ~1-2 seconds and consume no extra orchestrator context (no chat output from either tool — just the artifact cards Cowork inserts automatically).

