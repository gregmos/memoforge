# Reference documents — index

Quick map of the canonical reference documents under `skills/memo/references/` and `skills/memo/state-schema.md`. When in doubt, consult the table below to find the authoritative source for a topic. Higher entries beat lower entries on conflict (per `operating-contract.md` authority hierarchy).

| Topic | Canonical document | Notes |
|---|---|---|
| Pipeline phase ordering, owners, inputs, outputs, gates, mode branches | `pipeline-contract.md` | Single source of truth for the phase table. All other docs cite this. |
| Orchestrator control flow per phase (dispatch, **parallelism**, state writes, events, turn) | `skills/memo/PHASE-MACHINE.md` (in `skills/memo/`) | Compact cheat-sheet, **re-read at every phase boundary** (summarization defense); authoritative for control flow. Its Globals carry the essence of the progress/events/live-progress contracts, so those are demand-read for format only. |
| Full step-by-step procedure for each pipeline phase | `skills/memo/references/phases/phase-<n>.md` | Verbatim phase prose extracted from SKILL.md (B1b router refactor). `SKILL.md` §"Phase procedures" maps `current_phase` → file; read the file on entering that phase. SKILL.md itself is now a thin router (~140 lines). |
| `state.json` canonical schema (field names, types, ownership) | `state-schema.md` (in `skills/memo/`, not `references/`) | Validator enforces a subset of this; see `scripts/validate_state.py`. |
| Mode-specific config matrix (Brief / Full) | `modes.md` | Drives `MODE_CANONICAL_CONFIG`, `MODE_RESEARCHER_SET`, `MODE_TEMPLATE_ID` in the validator. |
| Fallback chain (per-phase failure modes + banner text) | `always-deliver.md` | Universal fallback at the bottom — pipeline never ends silently. |
| MCP rate-limit detection + fallback procedure | `mcp-ratelimit-contract.md` | Researchers cite this from their own prompts; `mcp_ratelimit_fallback` event is canonical. |
| Per-subagent log files in `<work_dir>/logs/<agent>.log` | `logging-contract.md` | Separate from `events.jsonl` (which is the orchestrator-owned audit log). |
| `events.jsonl` schema + canonical event names (audit log) | `events-contract.md` | Schema v1: every event has `{ts, event, phase, iteration, actor, severity, data}`. Helper: `scripts/log_event.py`. |
| Main-session role, authority hierarchy, untrusted-content boundary, tool-use contract, when to stop, **hard constraints** | `operating-contract.md` | Read this on every orchestrator activation. |
| Chat-visible Progress message schema, file-reference UX rule (D2), 16-row mandatory-update checklist | `progress-contract.md` | Read once before pipeline work. Sibling of events/logging contracts. |
| Visualize milestone-tracker widget spec (5 render points) | `progress-tracker.md` | Renders only when `state.json.config.visualize_enabled == true`. |
| Visualize widget data-payload schemas (elicitation, mode mockup, plan diagram, final dashboard) | `widget-schemas.md` | Demand-loaded per phase: 2a, 1.5, 4a, 12. Separate from the milestone-tracker widget. |
| Live-progress sidebar dashboard (subagent-side `mcp__cowork__update_artifact` streaming) | `live-progress-contract.md` | Introduced v0.5.0 (postmortem §9 resolved). Master artifact minted at Phase 1 step 3.5; heavy subagents call `update_artifact` at internal step boundaries — those calls flush live to the parent chat scroll. |
| WebSearch discovery-vs-citation policy | `pipeline-contract.md §WebSearch` | Mirrored in README; researcher prompts cite the canonical paragraph. |
| Tool inheritance per subagent (allowlist / inherit-all) | `pipeline-contract.md §Tool inheritance` | Cross-checked against agent frontmatter. |
| Validator scripts contract | `pipeline-contract.md §Validators` | `validate_state.py` and `validate_review_json.py`. |
| File-link UX (plain text vs markdown links in chat) | `pipeline-contract.md §File-link UX` | Empirical Cowork behavior. |
| Release hygiene (version sync across README / plugin.json / dist / git tag) | `pipeline-contract.md §Release hygiene` | Single atomic procedure. |
| House style (prose tone, definitions format, four-beat Risk pattern, reviewer priority) | `lib/prose-style.md` | Rhetorical — what the prose reads like. |
| docx visual spec (margins, fonts, banners) | `lib/docx-render/README.md` + `lib/docx-render/scripts/md_to_docx.py` | Visual — how the prose looks in docx. |
| Revision loop methodology (reviewer dispatch, mediator consolidation, exit conditions) | `lib/revision-loop.md` | Methodology only — operational dispatch is in memo Phase 9 and continue/SKILL.md `revision_loop` branch. |

## Conflict resolution

If two documents in this list appear to disagree, follow this order (highest authority wins):

1. `.claude-plugin/plugin.json` / `.mcp.json` (platform manifest)
2. `pipeline-contract.md` (canonical contract — declared as such in its preamble)
3. `state-schema.md` (canonical state schema)
4. `modes.md`, `always-deliver.md`, `mcp-ratelimit-contract.md`, `logging-contract.md`, `operating-contract.md`, `progress-contract.md`, `progress-tracker.md`, `widget-schemas.md`, `live-progress-contract.md`, `events-contract.md` (canonical for their topic)
5. `skills/memo/PHASE-MACHINE.md` (authoritative for orchestrator **control flow** — dispatch/parallelism/state-writes/events/turn; SKILL.md prose yields to it on control-flow conflicts)
6. `skills/memo/SKILL.md` / `skills/continue/SKILL.md` / `skills/status/SKILL.md` (orchestration prose + rationale)
7. `lib/prose-style.md` (domain conventions)
8. `lib/docx-render/README.md` (visual conventions)
9. Agent prompts in `agents/*.md`

When a lower-tier doc looks stale, file a follow-up to bring it in sync — do not let the lower-tier wording override the higher-tier source.

## When to read what (by orchestrator phase)

| Phase | First read | Then |
|---|---|---|
| pre-Phase-1 (always) | `PHASE-MACHINE.md` + `operating-contract.md` | Activation preamble. The cheat-sheet (control flow + the essence of progress/events/live-progress) is the always-read map; `operating-contract.md` carries the global invariants. |
| **every phase boundary (always)** | `PHASE-MACHINE.md` (re-read the current `current_phase` row) | Summarization defense — re-grounds dispatch/parallelism/events/turn in fresh context |
| on first need (format/taxonomy) | `progress-contract.md` / `events-contract.md` / `live-progress-contract.md` | Demand-read for exact format the first time you emit that kind of thing — NOT every activation (their per-phase essence is in the cheat-sheet) |
| 1 init | `state-schema.md` for the Phase 1 init template | — |
| 1 step 3.5 live-progress mint | `live-progress-contract.md` §"How the channel works" | mint artifact, write `state.json.live_progress` |
| 1.5 mode pick | `modes.md` + `widget-schemas.md §Mode mockup` | `progress-tracker.md` (Milestone 1) if visualize enabled |
| 2a intake | `widget-schemas.md §Elicitation` | `agents/fact-assumption-analyst.md` for JSON schema |
| 4a plan approval | `widget-schemas.md §Plan diagram` | — |
| 5 research | researcher agent prompts + `mcp-ratelimit-contract.md` | `logging-contract.md` for per-agent logs |
| 6 sufficiency / 6.5 currency | `pipeline-contract.md` Phase 6 / 6.5 rows | re-gate logic in `pipeline-contract.md` §State schema |
| 7→8 source-review checkpoint (v0.0.43+) | `always-deliver.md` Phase 7→8 source-review row; `progress-contract.md` row 9.5 | (legacy `heartbeat_pending` phase removed in v0.0.43; resumed v0.0.42 tasks migrate to `source_review_pending`) |
| 8 drafting | `lib/prose-style.md` (rhetorical) + `agents/memo-writer.md` | `templates/<id>.md` for the chosen template |
| 9 revision loop | `lib/revision-loop.md` | `lib/prose-style.md` §Reviewer priorities for mediator conflict resolution |
| 10 client-readiness | `agents/client-readiness-reviewer.md` | `modes.md` §Phase 10 for polish budget |
| 11 export | `lib/docx-render/README.md` | `always-deliver.md` Phase 11 row for fallback chain |
| 12 final dashboard | `widget-schemas.md §Final dashboard` | — |
| any failure | `always-deliver.md` Universal final fallback | write `fallback-summary.md`, end gracefully |
