<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 1.5 — Pipeline mode choice

After intake is recorded (`current_phase = mode_pick_pending` has just been set, in either Path A or Path B) and before doing any planning work, the user must pick a pipeline **mode** (Brief or Full). Modes control how thorough the pipeline runs (researcher count, reviewer count, iteration cap, polish budget) AND the template used for the output — each mode hard-codes its template (Brief → executive-brief, Full → classical-memo). The `mode_pick_pending` phase is the hard gate — `state.json.mode` MUST be set via the AskUserQuestion below before `current_phase` advances to `planning`. /continue resumes a task in this phase by re-running this AskUserQuestion (never by silently jumping to `planning`).

**Do not infer the mode from natural-language phrasing in the original query.** Even if the user wrote "short memo" / "brief check" / "deep dive" / "full analysis" in `state.json.user_query`, do NOT treat those phrasings as the answer to this gate. NL phrasing is **never** a substitute for the explicit `AskUserQuestion` choice — those words could mean "quick research" (mode) or "short output" (template) or both, and the user must disambiguate explicitly. The question MUST be asked. Skipping this gate based on inferred intent is a pipeline violation that the user has explicitly flagged in prior runs.

1. Read `skills/memo/references/modes.md` for the full mode matrix (Brief / Full) and AskUserQuestion call shape.

**1b. Visualize widget (mode mockup) — render BEFORE `AskUserQuestion`.**

If `state.json.config.visualize_enabled == true`:

a. If `state.json.cache.visualize_guidelines` is empty, call `<visualize_namespace>__read_me` with `{ "modules": ["mockup", "diagram", "data_viz"], "platform": "desktop" }` and persist the response to `state.json.cache.visualize_guidelines` (or `$WORK_DIR/cache/visualize-guidelines.md` if large).

b. Build the data payload per `skills/memo/references/widget-schemas.md §Mode mockup`. Values mirror `references/modes.md` — keep them in sync.

c. Following the cached `mockup` module guidelines, generate self-contained HTML/SVG (≤30KB) using the layout described in `widget-schemas.md §Mode mockup`. No JavaScript callbacks — visualize is one-way.

d. Save the generated HTML to `$WORK_DIR/widgets/phase15-mode-mockup.html` for audit (mkdir -p if needed), then call `<visualize_namespace>__show_widget` with the title / loading_messages / widget_code per `widget-schemas.md §Mode mockup`.

e. Append `visualize_widget_rendered` event to `events.jsonl` per the schema in `widget-schemas.md §Mode mockup`.

If `visualize_enabled == false` or the call throws, skip silently and proceed to step 2 — the existing `AskUserQuestion` descriptions already include page-count hints from the modes.md update.

2. **MUST call AskUserQuestion** with two options (Brief / Full) using exactly the descriptions documented in `modes.md`. Do not skip, do not pre-fill the answer, do not interpret the original query as the answer. If you find yourself about to write "given you asked for a short memo, I'll route to Brief mode" — stop and call AskUserQuestion instead.
3. Record the answer:
   - Update `state.json.mode` with the chosen label (lowercase: `"brief"` | `"full"`).
   - Resolve the mode config from the matrix in `modes.md`, then **MERGE** it into the existing `state.json.config` (do NOT overwrite — the visualize precheck may have already written `visualize_enabled` and `visualize_namespace` into this object). Use a read-modify-write pattern, e.g. via Bash + Python:
     ```bash
     python3 - <<'PY'
     import json, pathlib
     p = pathlib.Path("<WORK_DIR>/state.json")
     s = json.loads(p.read_text())
     # Brief preset:
     s["mode"] = "brief"
     mode_cfg = {
       "researcher_set": ["statutory"],
       "reviewer_list": ["logic", "citations", "counterarguments"],
       "max_iterations": 1,
       "client_polish_enabled": False,
       "max_client_polish": 0,
       "template_id": "executive-brief"
     }
     # Full preset (substitute for Brief above when user picks Full):
     # s["mode"] = "full"
     # mode_cfg = {
     #   "researcher_set": ["statutory", "case-law", "doctrinal"],
     #   "reviewer_list": ["logic", "clarity", "style", "citations", "counterarguments"],
     #   "max_iterations": 3,
     #   "client_polish_enabled": True,
     #   "max_client_polish": 1,
     #   "template_id": "classical-memo"
     # }
     s["config"] = {**(s.get("config") or {}), **mode_cfg}
     s["current_phase"] = "planning"  # atomic transition out of mode_pick_pending — must happen in the same write as mode/config
     tmp = p.with_suffix(".json.tmp"); tmp.write_text(json.dumps(s, indent=2)); tmp.replace(p)
     PY
     ```
     The resulting `state.json.config` MUST include all of: `researcher_set`, `reviewer_list`, `max_iterations`, `client_polish_enabled`, `max_client_polish`, AND `template_id`. Pre-existing `visualize_enabled` and `visualize_namespace` MUST survive the merge. After this merge `state.json.current_phase` is `planning` (advanced from `mode_pick_pending` in the same atomic write).
   - Append `mode_selected` event to `events.jsonl` with the chosen mode and resolved config.
4. If user picks "Other" with free text, default to Full and print one-line note: "Defaulting to Full mode; rerun with /memo if you wanted Brief."
5. Print a Progress block as plain assistant text (v3 format — see `references/progress-contract.md` §"Progress block format"):

   ```
   **Progress — <task_id>**
   - Current phase: `planning`
   - Completed: Mode selected (`<mode>`)
   - Next: Building research plan
   - Notes: Config — <N> researchers, <max_iterations> iteration(s), <M> reviewers per iteration, client polish <on/off>, template `<template_id>`
   ```

   The widget HTML (if rendered) and any other files written by this phase already appear above the Progress block as Cowork artifact cards from their Write tool calls — no need to list them in `Artifacts:`.
6. **Milestone-1 tracker (Setup done).** If `state.json.config.visualize_enabled == true`, render the milestone-1 pipeline tracker per `skills/memo/references/progress-tracker.md` (status map row "1 — Setup done"). Save snapshot to `$WORK_DIR/widgets/progress-01-setup-done.html` and append `visualize_widget_rendered` event. Graceful skip if disabled or call fails.

7. **TodoWrite update.** Mark item #2 ("Mode pick") = `completed`, item #3 ("Build research plan") = `in_progress`. Silent skip if `TodoWrite` is unavailable.

8. **Style-profile resolve (zero-overhead when no profiles exist).** Look up the user's saved style profiles. **If none exist, this step is silent — no prompt, no log noise, nothing user-visible. The pipeline behaves exactly as it did before the Style Studio feature shipped.** If at least one profile exists, ask the user which one to use (or fall back to the built-in style).

   ```bash
   # List profiles (empty array if the dir is empty or missing).
   PROFILES_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_style_profile.py" list)
   DEFAULT_NAME=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_style_profile.py" get-default)
   ```

   **8a. No profiles.** If `PROFILES_JSON == "[]"`, write nulls to state.json.config and skip the rest of this step entirely. NO chat output, NO checkpoint:

   ```bash
   python3 - <<'PY'
   import json, pathlib
   p = pathlib.Path("<WORK_DIR>/state.json")
   s = json.loads(p.read_text())
   s["config"]["style_profile"] = None
   s["config"]["style_profile_path"] = None
   s["config"]["prose_style_path"] = None
   s["config"]["template_path"] = None
   tmp = p.with_suffix(".json.tmp"); tmp.write_text(json.dumps(s, indent=2)); tmp.replace(p)
   PY
   ```

   Continue inline to step 9 — nothing else fires for this step.

   **8b. At least one profile exists.** Build an `AskUserQuestion` (English, copy verbatim):

   - **Question:** "Which style should we use for this memo?"
   - **Header:** "Style" (≤12 chars).
   - **multiSelect:** false.
   - **Options:** for each profile in `PROFILES_JSON`, add one option:
     - label: `Your profile: <name>` (if `<name> == DEFAULT_NAME`, mark it preselected by listing it FIRST) OR `Profile: <name>` (non-default profiles).
     - description: 1-line summary from `meta.summary`, plus mode binding (e.g. "From 3 EU GDPR memos. Mode: brief.")
   - Final option (always last):
     - label: "Standard plugin style (built-in)"
     - description: "Skip custom profile and use the bundled prose-style + classical-memo / executive-brief template"

   Cap the options at 4 (AskUserQuestion limit). If more than 3 profiles exist, show the default + first two others + "Standard plugin style". The user can still pick a different profile later via `/memoforge:style use <name>` then re-run /memo.

   Branch on the answer:

   - **"Standard plugin style"** → write nulls (same as step 8a above). Log `style_profile_resolved` event with `{"chosen": "built-in", "profiles_available": <N>}`.

   - **Any profile picked** → resolve paths via:
     ```bash
     PATHS_JSON=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_style_profile.py" resolve-paths "<picked_name>")
     ```
     Parse the JSON and write to state.json.config (atomic merge):
     ```bash
     python3 - <<'PY'
     import json, pathlib
     paths = json.loads('<PATHS_JSON>')
     p = pathlib.Path("<WORK_DIR>/state.json")
     s = json.loads(p.read_text())
     s["config"]["style_profile"] = paths["style_profile"]
     s["config"]["style_profile_path"] = paths["style_profile_path"]
     s["config"]["prose_style_path"] = paths["prose_style_path"]
     s["config"]["template_path"] = paths["template_path"]
     tmp = p.with_suffix(".json.tmp"); tmp.write_text(json.dumps(s, indent=2)); tmp.replace(p)
     PY
     ```
     Log `style_profile_resolved` event with `{"chosen": "<name>", "has_custom_template": <bool>, "profiles_available": <N>}`.

     **Mode-mismatch check.** Read the picked profile's `meta.mode_binding`. If it differs from `state.json.mode`, ask a follow-up `AskUserQuestion`:

     - **Question:** "Profile `<name>` was created for `<mode_binding>`, but you selected `<state.json.mode>`. How should we proceed?"
     - **Header:** "Mode"
     - Options:
       - label: `Use the profile (switch to <mode_binding>)`, description: "Re-runs Phase 1.5 mode-config merge for <mode_binding>; profile is applied"
       - label: `Use built-in template for <state.json.mode>`, description: "Keep <state.json.mode> mode and ignore the profile's template; only prose-style still applies"

     Branch:
     - "Use the profile" → call the merge-config block from Phase 1.5 step 3 again, but with the profile's `mode_binding` instead of the originally chosen mode. Update `state.json.mode`. Re-emit `mode_selected` with `reason: "profile_mode_binding"`.
     - "Use built-in template for X" → clear `state.json.config.template_path` (set to null), keep `prose_style_path` non-null. The writer will use built-in template structure but custom prose style.

   **8c. Heads-up.** Print a one-line Progress note to chat after the choice resolves: `Style profile: <name> (custom prose-style + <built-in / custom> template).` This is the user's signal that their profile was picked up. Skip the note if "Standard plugin style" was chosen (no change from default behaviour).

9. Inline continue to Phase 3 — do not end the turn.

Downstream phases read `state.json.config` and behave accordingly (see `modes.md` "How each downstream phase reads config" section). In particular, Phase 3 will read `config.template_id` directly — Brief mode always produces an `executive-brief` (2-3 pages); Full mode always produces a `classical-memo`. Custom style profiles override `prose_style_path` / `template_path` only — they do NOT change `template_id`, so classifier and validator logic stay stable.

