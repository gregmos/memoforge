<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 1 — Initialize task & preliminary intake

**Order of steps in this phase:**
1. **Task setup** — resolve work_dir, mkdir, initialize `state.json`, create `events.jsonl`, AND mint the live-progress master artifact. Sub-steps 1a→1e. This MUST happen first because the precheck steps below write events and `state.json.config.*` keys, and because the live-progress mint must happen BEFORE any subagent dispatch.
2. **MCP availability precheck** — detect Legal Data Hunter / CourtListener namespaces, record results, append `mcp_precheck_result` event, push fallback banner if MCP missing.
3. **Visualize widget precheck** — detect `visualize` namespace, write `state.json.config.visualize_enabled` and `visualize_namespace`, append `visualize_precheck_result` event.
4. **Dispatch `fact-assumption-analyst`** — preliminary triage to generate intake questions.

The Phase 1.5 mode pick happens later (after Phase 2 intake completes); the visualize-enabled and live-progress-enabled flags set here are read by Phase 1.5 to decide widget vs text fallback. Phase 1.5 MERGES mode config into `state.json.config` and MUST preserve `visualize_*` and `live_progress_enabled` keys.

> **v0.5.6 restructure:** prior versions placed the live-progress mint at step 3.5 (between Visualize precheck and fact-assumption-analyst dispatch). Empirical observation showed orchestrators reliably skipping that separate step. As of v0.5.6 the mint is part of Step 1 (Task setup) — bundled with state.json init and events.jsonl creation, which orchestrators never skip. See sub-step 1d below.

### Task setup (step 1)

Take the user query from `$ARGUMENTS`. Read `lib/prose-style.md` for house style (auto-invocation should have already loaded it; if not, read explicitly).

**Resolve the working directory directly inside the user's output folder.** All artifacts (state.json, plan.md, intake/, research/, drafts/, reviews/, the final docx) live in ONE place from Phase 1 onwards. There is no separate "staging" location; no copy step at the end. Links in chat point to the same directory throughout the run.

Resolution order (first writable wins):

1. `$CLAUDE_PLUGIN_OPTION_OUTPUT_FOLDER` (plugin option set by the user).
2. `$MEMOFORGE_OUTPUT_FOLDER` (environment variable).
3. `$HOME/Documents/memoforge` (default for desktop installs).
4. `outputs/memoforge-work` (sandbox fallback for Cowork sessions where the previous paths are not writable — this path is **relative to CWD** so the user can navigate to it manually from the file viewer; clickability inside chat still comes from artifact cards on Read/Write/Edit calls, not from the path text).

Run via Bash — `scripts/resolve_work_dir.sh` does the resolution, creates the directory tree, and prints `task_id=`, `work_dir=`, `rel_work_dir=`, `output_folder=` lines for the orchestrator to parse:

```bash
SLUG="<2-4 word kebab-case descriptor of the query>"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_work_dir.sh" "$SLUG"
```

The script applies the resolution order above, computes `REL_WORK_DIR` via the `realpath → python3 → python → echo` fallback chain (Cowork only renders relative paths as clickable in chat — see `references/progress-contract.md` §"How file references work in Cowork"), and creates the `{intake, checkpoints, research, research/raw, drafts, reviews, widgets, cache}` subtree. Exits non-zero if no candidate is writable.

Record the resolved path in `state.json.work_dir` (canonical filesystem field — every downstream phase, agent dispatch, and `/continue` call resolves paths against this for Read/Write/Bash operations). When SKILL.md or agent prompts say "work directory" or use the legacy placeholder `${CLAUDE_PLUGIN_DATA}/work/<task_id>/`, they mean `<state.json.work_dir>`.

**Also record `state.json.rel_work_dir` — the CWD-relative form computed by the bash above.** Use `work_dir` for filesystem operations (Read, Write, Bash). Use `rel_work_dir` for the plain-text `Work directory: <path>` line in the first Progress block and for any informational path reference you print in chat. (File-reference rule D2 — see `references/progress-contract.md` §"How file references work in Cowork".) The two fields point to the same directory — only the format differs.

Initialize `state.json` with:
```json
{
  "task_id": "<task_id>",
  "user_query": "<original>",
  "created_at": "<ISO>",
  "language": "en",
  "work_dir": "<resolved path used for filesystem operations>",
  "rel_work_dir": "<CWD-relative form of work_dir>",
  "output_folder": "<the parent OUTPUT_FOLDER>",
  "mode": null,
  "config": {},
  "revision_gate_choice": null,
  "client_readiness_gate_choice": null,
  "polish_gate_choice": null,
  "fallback_banners": [],
  "classification": null,
  "intake": {
    "status": "preliminary_research",
    "questions_iteration": 1,
    "user_response": null,
    "assumptions_accepted": false
  },
  "plan_approval": {
    "status": "not_started",
    "iterations": [],
    "final_plan_iteration": null
  },
  "current_phase": "intake_preliminary_research",
  "current_iteration": 0,
  "max_plan_edit_iterations": 5,
  "max_intake_iterations": 2,
  "exit_threshold_score": 85,
  "current_draft_path": null,
  "iterations": [],
  "client_readiness": null,
  "final_status": null,
  "final_docx_path": null,
  "attempts": {
    "research_followup": 0,
    "research_followup_pending_review": false,
    "client_readiness_polish": 0,
    "client_readiness_polish_pending_review": false,
    "reviewer_json_retry": {}
  },
  "remaining_blocking_issues": [],
  "events_path": "events.jsonl",
  "live_progress": null
}
```

Write `state.json` atomically (write to `state.json.tmp`, then `mv` to `state.json`). Create `events.jsonl` in the work directory and append one JSON line for `task_created` with timestamp, phase, and task_id. Also append one `work_dir_resolved` event with the resolved path and which candidate was chosen — the audit trail of where artifacts actually live.

After this, `state.json` exists with `config: {}`, `live_progress: null`, and `events.jsonl` exists. The two precheck steps below (steps 2 and 3) will append events and `Edit` `state.json` to populate `config.visualize_*` keys. Phase 1.5 mode-pick (later) MUST merge mode config into existing `config` without overwriting `visualize_*` or `live_progress_enabled`.

### Mint live-progress master artifact (step 1d — MANDATORY, immediately after state.json init)

> **STOP — this is the step v0.5.0–v0.5.5 orchestrators were observed skipping.** Without this mint, the user sees no sidebar dashboard for the entire run. The mint is one HTML render + one `mcp__cowork__create_artifact` tool call. Do not skip it. Do not "do it later". Do not "do it at the precheck step". Do it NOW, before MCP precheck (step 2), before visualize precheck (step 3), before anything else. The reason it lives here in Step 1 (and not in a separate step 3.5 like v0.5.5) is that Step 1 (Task setup) is non-skippable; every other step has been observed to be skippable under context pressure.

**Sub-action 1d-1: Probe artifact tool availability via ToolSearch.**

Call `ToolSearch(query="select:mcp__cowork__create_artifact,mcp__cowork__update_artifact,mcp__cowork__list_artifacts", max_results=3)`. Inspect the result:

- If `mcp__cowork__create_artifact` AND `mcp__cowork__update_artifact` schemas BOTH load → live-progress is available. Proceed to 1d-2.
- If either schema fails to load → live-progress is NOT available (you are running outside Cowork, or Cowork's host does not expose artifact tools). Atomic-`Edit` `state.json` to set `config.live_progress_enabled = false`. Append a `live_progress_unavailable` event to `events.jsonl` with `{"reason": "create_artifact or update_artifact schema did not load"}`. **Skip sub-actions 1d-2 through 1d-5.** Continue to step 2 (MCP precheck) without live-progress.

**Sub-action 1d-2: Atomic-`Edit` `state.json` to populate the `live_progress` block AND set the enabled flag.**

```json
"config": { "live_progress_enabled": true },
"live_progress": {
  "artifact_id": "memo-<task_id>-live",
  "html_path": "<state.json.work_dir>/live-progress.html",
  "started_at_iso": "<NOW_ISO>",
  "phase_started_at_iso": "<NOW_ISO>",
  "timeline": [
    { "phase": "intake_preliminary_research", "started_at_iso": "<NOW_ISO>", "completed_at_iso": null }
  ],
  "active_subagents": null,
  "source_counts": null,
  "topic": "<short 3-7 word theme generated from user_query>"
}
```

**About `topic`:** write a concise 3–7 word theme summarising the user's query. This becomes the dashboard header line (replaces the truncated raw query). Examples for the question *"We're a US-based SaaS company planning to launch a new feature that uses AI to analyze customer support chat transcripts (from EU users) to automatically suggest responses to agents. The transcripts contain names, email addresses, and sometimes account details. Do we need a separate legal basis under GDPR for this AI processing, or does it fall under our existing 'contract performance' basis for providing the support service? Also, does this trigger any DPIA requirement or AI Act obligations?"* — good topics:
- `"GDPR compliance for AI support feature"`
- `"AI-on-support-transcripts: GDPR basis + AI Act"`
- `"Contract basis vs separate basis for AI analytics"`

Bad topics: `"User wants legal advice"` (too generic), `"Memo"` (uninformative), or copying the first 7 words of the query verbatim. Aim for an analytical hook the user could glance at and immediately recognise as their question. If you can't think of one in <10 seconds, ship `null` and the renderer falls back to truncating `user_query`.

Where:
- `<task_id>` is `state.json.task_id` from sub-step 1b.
- `<NOW_ISO>` is the current ISO-8601 timestamp.
- `<state.json.work_dir>` is the resolved absolute work directory.

Atomic write (temp + rename) per the state-schema contract.

**Sub-action 1d-3: Render the initial HTML.**

> **HARD RULE — `live-progress.html` is owned by `render_live_progress.py` (v0.7.1+, tightened v0.7.2).** The renderer below is the ONLY writer of `<work_dir>/live-progress.html`. Do NOT `Write` / `Edit` this file directly with custom HTML constructed inline. Do NOT use Bash `cat` / `echo` / heredoc / `python3 -c` to emit HTML into this path. Do NOT mint side-car artifacts via `mcp__cowork__create_artifact` with a non-master id (e.g. `memo-<task_id>-research-snapshot`) — v0.7.2 explicitly REMOVED the side-car escape hatch that v0.7.1 had inadvertently sanctioned. The master `memo-<task_id>-live` is the sole Cowork artifact the pipeline mints; this Step 1d call is the one permitted `create_artifact` invocation per task. If the standard dashboard output ever feels insufficient (e.g. you want richer per-researcher status after a subagent returns), add a new field to `state.json.live_progress`, extend `render_live_progress.py` + tests + `state-schema.md`, and ship a new plugin version — DO NOT improvise. See `references/live-progress-contract.md` §"HARD RULE — `<work_dir>/live-progress.html` is owned by `render_live_progress.py`" for the full contract, rationale, and the two sanctioned paths.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}"/scripts/render_live_progress.py \
  --state-json "<state.json absolute path>" \
  --current-step "Pipeline starting — Phase 1 intake setup" \
  --output "<state.json.work_dir>/live-progress.html"
```

The renderer writes `<output>.tmp` then atomically renames. Includes `<meta charset="UTF-8">` (Cowork iframe requires this for em-dashes / Cyrillic).

**Sub-action 1d-4: Mint the artifact via `mcp__cowork__create_artifact`.**

Call the tool directly:

```
mcp__cowork__create_artifact(
  id="memo-<task_id>-live",
  html_path="<state.json.work_dir>/live-progress.html",
  description="Live pipeline dashboard for memoforge — auto-refreshes as phases progress"
)
```

`create_artifact` is first-write-wins. If the call errors with "An artifact with id X already exists" (resumed task where the prior run minted the same id), fall back to a single `mcp__cowork__update_artifact` call with the same id and html_path — the artifact already exists, just refresh its content. Append a `live_progress_existing_artifact_reused` event.

The v0.5.4 plugin-bundled PreToolUse hook (`hooks/auto_approve_cowork.py`) auto-approves this call so no permission prompt surfaces in chat. If the hook is somehow not honored (Cowork build doesn't load plugin hooks, etc.) the user sees a prompt — they click Approve once and the mint proceeds.

**Sub-action 1d-5: Append two events to `events.jsonl`:**

- `live_progress_precheck_result` with `{"enabled": true, "artifact_id": "memo-<task_id>-live", "html_path": "<work_dir>/live-progress.html"}`.
- `live_progress_artifact_minted` with `{"artifact_id": "memo-<task_id>-live"}`.

**Sub-action 1d-6 (self-verify): Read `state.json`. Confirm `live_progress.artifact_id` is non-null AND `config.live_progress_enabled` is `true`.** If either is missing, you skipped sub-action 1d-2 — atomic-`Edit` `state.json` to fix it now, then proceed. This is the verification step that catches the v0.5.x failure mode that motivated this restructure.

After step 1d completes successfully (or skips gracefully on tool unavailability), continue to step 2 (MCP precheck). The remaining downstream contract is unchanged from prior versions — see "MANDATORY — orchestrator's downstream responsibility at every phase transition" below for what to do at later phase boundaries.

### MCP availability precheck (step 2 — requires state.json and events.jsonl from step 1)

The plugin bundles two HTTP MCP servers via `.mcp.json`: `legal-data-hunter` (broad multi-jurisdictional law) and `courtlistener` (US case law / PACER / citation verification). Cowork lists them as available but does **not** auto-connect them — the user must connect each from the plugin details panel, and the first call may require OAuth/sign-in.

**Detect by tool function name, not namespace prefix.** In Cowork (the primary plugin host), all authenticated MCP tools surface under an **opaque UUID namespace** (`mcp__<uuid>__*`) regardless of whether they were authenticated via the plugin's own `complete_authentication` flow or via user-level Cowork settings. Cowork generates and persists a UUID at connector-creation time and ignores both server metadata and the `.mcp.json` server-name slug — so the plugin-scoped vs user-level distinction is **not detectable from the namespace**. (Bootstrapping tools like `mcp__plugin_memoforge_<server>__authenticate` exist under the plugin prefix, but they are auth helpers, not the data tools you care about.) Reference: [anthropics/claude-ai-mcp#167](https://github.com/anthropics/claude-ai-mcp/issues/167), [anthropics/claude-code#29360](https://github.com/anthropics/claude-code/issues/29360).

Inspect your available tool list and apply these detection rules:

- **Legal Data Hunter is connected** if you can see any tool whose name (after the last `__`) is one of `discover_countries`, `discover_sources`, `get_filters`, `resolve_reference`, `report_source_issue`, `get_document`. (`search` alone is too generic — many MCPs expose a `search` tool.)
- **CourtListener is connected** if you can see any tool whose name (after the last `__`) is one of `analyze_citations`, `extract_citations`, `resume_citation_analysis`, `get_endpoint_schema`, `call_endpoint`, `subscribe_to_docket_alert`, `create_search_alert`.

Record the full namespace prefix each MCP lives under (everything before `__<function_name>`). Researchers in Phase 5 need it so they call tools under the same prefix. Do **not** try to label a prefix as "plugin-scoped" vs "user-level" — that distinction does not exist at the namespace level in Cowork. Treat any namespace exposing the LDH/CourtListener function set as a connected MCP.

After detection, print **one** combined status line as a standalone chat message (not inside any `Progress —` block — the Progress block's `Notes:` field must NOT duplicate this status). In English:

```
MCP status: LDH <✓ connected | ✗ not connected>; CourtListener <same options>.
```

The visualize precheck below appends `; visualize: ✓ | ✗` to the same line. **Do NOT also print this in the next `Progress —` Notes field** — the status line is the single source of truth; Progress.Notes should focus on phase-specific information (what was just completed, what's next), not connector status.

Append a `mcp_precheck_result` event to `events.jsonl` with `{ "ldh": "<status>", "ldh_namespace": "<prefix or null>", "courtlistener": "<status>", "courtlistener_namespace": "<prefix or null>" }`.

Branch:
- **Both connected** → continue to "Task setup", no extra warning.
- **One or both missing entirely** → print this heads-up before continuing Phase 1 (adapt language RU/EN to the query):

  ```
  ⚠️ Plugin MCP servers are not connected for this session.

  Missing: <list which of legal-data-hunter / courtlistener is not connected>.

  What this means. Without these MCP servers, the researchers can only use WebFetch against official primary-source portals — no generic WebSearch. Research quality will be limited and some conclusions will be marked "not confirmed against primary source".

  How to connect:
  1. Cowork → Settings → Plugins → memoforge (or the plugin icon in the side panel).
  2. In the MCP / Connectors block, click Connect next to `legal-data-hunter` and `courtlistener`.
  3. The first call may ask for OAuth / sign-in — follow the prompts.
  4. After connecting you can either restart the task with `/memoforge:memo "<query>"`, or continue this one with `/memoforge:continue <task_id>`.

  If you cannot connect, the pipeline still runs in WebFetch-fallback mode. The final memo will include a yellow callout noting that the user should verify each citation against the primary source.
  ```

**Push the MCP fallback banner to `state.json.fallback_banners[]`.** When one or both MCPs are missing, atomically Edit `state.json.fallback_banners` to include the matching banner string from `skills/memo/references/always-deliver.md` Phase 5 table (idempotent — do not duplicate if the banner is already present):

- **Both missing** → push `"MCP servers unavailable. Research conducted via public WebFetch only — verify against primary sources before client use."`
- **Only one missing** (e.g. LDH up, CourtListener down, or vice versa) → push `"Partial MCP coverage — only <available> was reachable."` with the connected MCP name substituted in.

Also append a `fallback_invoked` event to `events.jsonl` with `fallback_name: mcp_unavailable` (both missing) or `fallback_name: mcp_partial` (one missing). These banners flow into the docx warning box at export time via `md_to_docx.py` regardless of `final_status` — that is the contractual user-facing disclosure.

Do not block on a missing MCP — the pipeline must still produce a memo, the MCP absence is degradation, not failure. **But also do not "rationalize" skipping MCP when it IS connected.** If detection succeeds, researchers in Phase 5 are required to attempt at least one MCP call before any WebFetch fallback (see Phase 5 anti-inline guard and the MCP-first contract in `agents/<researcher>.md`). The orchestrator MUST NOT do research inline.

### Visualize widget precheck (step 3 — after MCP precheck)

`visualize` is Anthropic's built-in MCP App for rendering custom HTML/SVG widgets inline in Claude chat. It is one-way (render only, no callback). Three phases of this pipeline will use it to give the user a richer visual context before decision points and at delivery: Phase 1.5 (mode mockup), Phase 3 (plan diagram), Phase 12 (final dashboard).

Detect by tool function name (do not assume a namespace prefix):

- **Visualize is available** if you can see a tool whose name (after the last `__`) is `show_widget` AND another tool whose name ends in `read_me`, both under a namespace that contains `visualize`.

Record:
- `state.json.config.visualize_enabled = true | false`.
- `state.json.config.visualize_namespace = "<prefix>"` (the full tool prefix up to but not including `__show_widget`).

Append a `visualize_precheck_result` event to `events.jsonl` with `{"enabled": <bool>, "namespace": "<prefix or null>"}`.

Append to the MCP status line — same chat message, do NOT print as a separate line and do NOT include in the next Progress block's Notes:

```
; visualize: ✓ — widgets enabled (mode choice / plan diagram / final dashboard)
```
or
```
; visualize: ✗ — markdown fallback only
```

**Graceful fallback rule for every visualize touchpoint.** Each Phase 1.5 / 3 / 12 step that calls `visualize:show_widget` MUST first check `state.json.config.visualize_enabled`. If `false`, skip the widget step entirely and continue with the existing markdown/text flow. If the widget call throws, log to `events.jsonl` as `visualize_call_failed` and continue without the widget — do NOT block the pipeline.

**Caching read_me guidelines.** The first widget call in the run (typically Phase 1.5) should call `visualize:read_me(modules=["mockup", "diagram", "data_viz"], platform="desktop")` ONCE and cache the result in `state.json.cache.visualize_guidelines` (or write to `$WORK_DIR/cache/visualize-guidelines.md` if the payload is large). Subsequent widget calls reuse the cached guidelines — do not re-fetch.

### Live-progress at phase transitions (downstream responsibility)

> The initial mint of the live-progress master artifact has been moved to **Step 1 sub-step 1d (Mint live-progress master artifact)** as of v0.5.6 — bundled with the non-skippable Task setup rather than as a separate step. See sub-step 1d above for the mint procedure. The downstream-responsibility block below describes what the orchestrator does at every SUBSEQUENT phase transition (Phase 1 → 2, Phase 4 → 5, Phase 7 → 7.5, etc.).

**MANDATORY — orchestrator's downstream responsibility at every phase transition.** At every `current_phase` change later in the pipeline, the orchestrator MUST execute the following sequence as ONE atomic action (treat it the same as the existing TodoWrite + mark_chapter mantras at phase transitions):

> **HARD RULE reminder — `live-progress.html` is owned by `render_live_progress.py` (v0.7.1+, tightened v0.7.2).** Step 2 below runs the renderer. That is the ONLY way the file gets refreshed at this transition. Do NOT, even when a subagent just returned with rich data you'd like to surface (per-researcher counts, citation lists, mediator iteration scores), construct custom HTML inline and Write it to `live-progress.html`. Do NOT mint a side-car artifact via `mcp__cowork__create_artifact` with a non-master id — v0.7.2 explicitly removed that escape hatch. The master `memo-<task_id>-live` is the sole Cowork artifact the pipeline maintains; phase-transition refreshes go through `mcp__cowork__update_artifact` on its existing id after the renderer overwrites the html file. New data flows through `state.json.live_progress.*` + the renderer + `state-schema.md` — never inline HTML, never side-car artifacts. Full contract and rationale in `references/live-progress-contract.md` §"HARD RULE — `<work_dir>/live-progress.html` is owned by `render_live_progress.py`".

1. Update `state.json` (atomic write — temp + rename) to:
   - Set the previous phase's `live_progress.timeline[last].completed_at_iso = NOW`.
   - Append a new entry `{ "phase": "<new phase>", "started_at_iso": "<NOW>", "completed_at_iso": null }`.
   - Set `live_progress.phase_started_at_iso = NOW`.
2. Re-render the HTML: `Bash: python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_live_progress.py" --state-json "<state.json>" --current-step "Phase <new_phase> — starting" --output "<html_path>"`.
3. Call `mcp__cowork__update_artifact(id=<artifact_id>, html_path=<html_path>, update_summary="phase-<new_phase>-start")`.

These three steps are paired the same way TodoWrite-update + mark_chapter + Progress-block are paired. Treat the live-progress update as a peer of those — do not skip it because "the user can't see it until end-of-turn anyway". Orchestrator-side updates DO buffer to end-of-turn (v0.2.0 falsification confirmed), but they keep the dashboard state consistent at the next flush moment (user gate / end-of-turn) AND they update `state.json.live_progress.timeline` which subsequent subagent emissions read.

Skip the entire sequence if `state.json.config.live_progress_enabled == false`.

**Subagents** call `update_artifact` at their own internal step boundaries — see each agent's "Live progress" section, each agent's "Pre-return checklist" section (added in v0.5.1 to enforce the `done` emission), and `references/live-progress-contract.md`.

**MANDATORY — orchestrator's active_subagents plumbing at every subagent dispatch (v0.6.0+, list-form v0.6.2+).** The live-progress dashboard renders one `🛠 <name>` chip per element of `state.json.live_progress.active_subagents`. To keep those chips honest, the orchestrator MUST set + clear the list around every `Task(subagent_type=...)` dispatch. Treat this as a peer of the TodoWrite + mark_chapter mantras that already surround subagent dispatches.

Exact sequence around every `Task(subagent_type="<name>", ...)` call:

1. **Before dispatch:** atomic-`Edit` `state.json.live_progress.active_subagents = ["<name>"]`. Single-element list for a single dispatch. (e.g. `["case-law-researcher"]`, `["memo-writer"]`, `["revision-mediator"]`.)
2. **Re-render + update_artifact** so the chip surfaces immediately (this is one of the orchestrator-side updates already covered by the "downstream responsibility at every phase transition" block above when the dispatch coincides with a phase change; do an extra update_artifact here when the dispatch is mid-phase).
3. **Dispatch** via `Task(...)`. Block until return as usual.
4. **After return:** atomic-`Edit` `state.json.live_progress.active_subagents = null` (or `[]`, both treated as "no chip"). No extra render/update needed — the next event (subagent done, next dispatch, phase transition) will refresh the artifact anyway.

**Parallel dispatches** (Phase 5 parallel researchers, Phase 9 parallel reviewers): set `active_subagents` to a list of ALL dispatched subagent names — the renderer makes one chip per element so the user sees them side-by-side. Set to null/empty after the whole batch returns.

Examples:
- Phase 5 parallel research (Full mode, doctrinal included): `["statutory-researcher", "case-law-researcher", "doctrinal-researcher"]` → three 🛠 chips.
- Phase 5 parallel research (Brief mode): `["statutory-researcher"]` → one chip.
- Phase 9 parallel reviewers (Full mode, 5 reviewers): `["logic-reviewer", "clarity-reviewer", "style-reviewer", "citation-auditor", "counterargument-reviewer"]` → five chips.
- Single dispatch (memo-writer, mediator, client-readiness): `["<single-name>"]` → one chip.

The list-form is preferred — v0.6.0–v0.6.1 used a single string and collapsed parallel dispatches into a coarse label like `"3 researchers (parallel)"`; that hid which specific subagents were running. The list-form gives per-subagent visibility, which is what the user wants to see in the dashboard.

**Backwards compatibility:** the renderer also accepts a bare string in `active_subagent` (singular, legacy field) and treats it as a single-element list. New code should always write `active_subagents` (plural, list).

Skip the entire sequence when `state.json.config.live_progress_enabled == false`.

### Dispatch fact-assumption-analyst (step 4)

After all **four** preceding steps (Task setup, MCP precheck, Visualize precheck, Live-progress precheck AND mint).

**4-pre. Mandatory verification block before dispatch.** Confirm in your own head, BEFORE proceeding to 4a:

- [ ] `state.json` exists with `task_id`, `work_dir`, `current_phase = intake_preliminary_research`.
- [ ] `state.json.config.visualize_enabled` is set (true or false).
- [ ] `state.json.config.live_progress_enabled` is set (true or false).
- [ ] **If `live_progress_enabled = true`:** `state.json.live_progress.artifact_id` is non-null AND the `mcp__cowork__create_artifact` call was made AND `events.jsonl` has a `live_progress_artifact_minted` line. If any of these are not true, go back to **Step 1 sub-step 1d** and execute the mint NOW before continuing. This is the single most-skipped requirement in v0.5.x and the user-visible failure mode is "live-progress dashboard never appears". Step 4 will not save you if step 1d was incomplete.
- [ ] `events.jsonl` has at minimum: `task_created`, `work_dir_resolved`, `mcp_precheck_result`, `visualize_precheck_result`, `live_progress_precheck_result` (and `live_progress_artifact_minted` when enabled).

If all checkboxes pass, proceed to 4a. Otherwise, fix the gap and re-run the verification.

**4a. Initialize TodoWrite side-panel.** Per `references/progress-contract.md` §"TodoWrite side-panel channel", call `TodoWrite` ONCE with the canonical 14-item list. Item #1 ("Intake — fact triage and questions") = `in_progress`; items #2–#14 = `pending`. This populates the right-side task panel from the start so the user can see the full pipeline shape and know where work currently is. If `TodoWrite` is unavailable in this host, skip silently and continue — chat Progress remains the primary channel.

**4b. Mark chapter.** Call `mcp__ccd_session__mark_chapter(title="Intake & planning", summary="Triage facts, build research plan")` once here. This adds a divider to the chat and a TOC anchor on the side. If the tool is unavailable, skip silently. (`mark_chapter` is also a no-op outside Cowork sessions — that is acceptable.)

**4c. Print the first chat Progress block** (per `progress-contract.md` row 1) — include the `Work directory:` field.

**4d. Dispatch `fact-assumption-analyst`** via Agent tool. Pass:
- Original query.
- Working directory path.
- House-style skill path.

It writes:
- `intake/fact-assumption-report.md`
- `checkpoints/intake-questions.md`
- `checkpoints/intake-questions.json`

Update `state.json.current_phase = intake_questions_pending`, `state.json.intake.status = questions_pending`.

**TodoWrite update.** Item #1 ("Intake") stays `in_progress` here — intake is not complete until the user answers (Phase 2b). No update needed at this transition.

