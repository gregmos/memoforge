# legal-memo-writer

> Multi-agent legal memo drafting plugin for **Claude Cowork** (primary) and **Claude Code** (best-effort).
> Takes a free-form legal question, runs the full lawyer workflow — intake, research, drafting, review, polish — and ships a finished `.docx` memo.

**Version:** `0.6.3` · **Author:** Grigorii Moskalev · **License:** MIT

---

## What it does

You ask one legal question. The plugin runs a 15-agent pipeline that mimics how a real legal team produces a memo:

1. **Triage** — figures out what facts are missing and asks you for them.
2. **Plan** — picks a template, decides which jurisdictions and sources to search, and asks you to approve.
3. **Research** — three researchers run in parallel: statutes, case law, doctrine/regulator guidance.
4. **Sufficiency + currency check** — verifies the sources are enough and still current law.
5. **Draft** — writes the memo in IRAC structure with full citations.
6. **Review** — up to 5 specialist reviewers (logic, style, clarity, counter-arguments, citations) stress-test the draft.
7. **Mediation** — a mediator consolidates reviewer feedback and the writer revises (up to 3 rounds).
8. **Client-readiness polish** — final check before delivery.
9. **Export** — saves a formatted `.docx` and the full source pack to your output folder.

You get a memo that cites real statutes and judgments, names contrary authority, gives a concrete risk score per issue, and ends with actionable recommendations — not generic "consult a lawyer" hedges.

**Languages:** Ask in English (other major languages best-effort). The memo is written in the language of your query.

---

## Quick start

### 1. Install

**Cowork:** Settings → Plugins → drag-and-drop `legal-memo-writer-0.6.3.zip` from the [Releases page](../../releases), or install via marketplace.

**Live-progress dashboard permission setup (one-time, only if needed).** v0.5.4 ships a `PreToolUse` hook that auto-approves the three Cowork artifact tools (`mcp__cowork__create_artifact`, `mcp__cowork__update_artifact`, `mcp__cowork__list_artifacts`) used by the live-progress sidebar dashboard. If that hook is honored by your Cowork build, the plugin runs without surfacing permission prompts during research, drafting, or review. If you still see repeated `Update artifact` prompts after installing 0.5.4, add the following to your user-level `~/.claude/settings.json` as a manual fallback (this is what the hook is doing under the covers; some Cowork builds may not honor plugin-bundled PreToolUse hooks):

```json
{
  "permissions": {
    "allow": [
      "mcp__cowork__create_artifact",
      "mcp__cowork__update_artifact",
      "mcp__cowork__list_artifacts"
    ]
  }
}
```

If the file already exists, merge the `permissions.allow` array. Cowork honors this permissions list out of the box per the documented MCP rule syntax — `mcp__server__tool` matches that exact tool, and `mcp__server__*` matches all tools from a server.

**Visualize widget permission setup (one-time, only if needed).** v0.6.3 extends the `PreToolUse` hook to also pre-approve the two visualize widget tools (`show_widget`, `read_me`) used by Phase 1.5 mode mockup, Phase 2a + 6.6 elicitation widgets, Phase 3 plan diagram, Phase 12 final dashboard, and the 5 inline milestone trackers. The hook matcher requires `visualize` substring inside the MCP namespace token, so it covers both plugin-scoped and Cowork UUID-scoped variants without affecting non-visualize MCPs. If the hook is not honored by your Cowork build and you see repeated `show_widget` prompts during a memo run, add these to your user-level `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_visualize__show_widget",
      "mcp__plugin_visualize__read_me"
    ]
  }
}
```

If Cowork exposes visualize under a UUID namespace (e.g. `mcp__abc123-visualize-uuid__show_widget`) you can either use the exact UUID-prefixed tool names from your session OR a wildcard `mcp__*visualize*__show_widget` if your Cowork build honors glob patterns.

**Bundled MCP server permission setup (one-time, only if needed).** The plugin's two bundled MCP servers (Legal Data Hunter and CourtListener, registered via `.mcp.json`) are NOT pre-approved by a hook — their function names (`get_document`, `search`, `call_endpoint`) overlap with potential other MCPs you may have installed, and Cowork surfaces them under arbitrary UUID namespaces, so a programmatic hook regex risks unintended auto-approval. Per-call permission prompts during research (Phase 5) are usually one-time-per-session for `Always allow` to stick within a single subagent, but #24433 means the grant doesn't persist across subagent dispatch boundaries — so you may see prompts repeat across the 3 parallel researchers + currency-checker + sufficiency-reviewer dispatches. If you want to suppress them programmatically, add the following to your user-level `~/.claude/settings.json` (Cowork's `mcp__server__*` glob syntax works for plugin-scoped variants; for UUID variants, copy the exact tool names from your first permission prompt):

```json
{
  "permissions": {
    "allow": [
      "mcp__plugin_legal-memo-writer_legal-data-hunter__*",
      "mcp__plugin_legal-memo-writer_courtlistener__*"
    ]
  }
}
```

**Claude Code (local dev):**
```bash
git clone https://github.com/gregmos/legal-memo-writer.git
claude --plugin-dir ./legal-memo-writer
```

The bundled MCP servers (Legal Data Hunter for multi-jurisdictional law, CourtListener for US case law) auto-register via `.mcp.json`. First MCP call may trigger an OAuth sign-in flow in the browser.

### 2. Run

```
/legal-memo-writer:memo "<your legal question>"
```

Examples:
- `/legal-memo-writer:memo "Can we process biometric data for minors in the EU under GDPR Art. 9 and Art. 22?"`
- `/legal-memo-writer:memo "Does our US SaaS need a CCPA notice at collection if we only have B2B users?"`
- `/legal-memo-writer:memo "Is a click-wrap arbitration clause enforceable against UK consumers under the Consumer Rights Act 2015?"`

### 3. Reply at the three checkpoints

The pipeline pauses three times. Reply with `/legal-memo-writer:continue <task_id> <action>`:

| Phase | What you'll see | How to reply |
|---|---|---|
| **Intake** | Up to 5 questions about missing facts | `answer: <facts>` or `proceed` (use defaults) |
| **Mode pick** | Choose Brief vs Full | `mode: brief` or `mode: full` |
| **Plan review** | The proposed research plan (jurisdictions, sources, issues) | `approve`, `edit: <instructions>`, or `cancel` |

After plan approval, the rest runs autonomously. You'll see live progress messages at each phase.

### 4. Get the memo

Output lands in (first that exists):
1. `$CLAUDE_PLUGIN_OPTION_OUTPUT_FOLDER/<task_id>/`
2. `$LEGAL_MEMO_OUTPUT_FOLDER/<task_id>/`
3. `~/Documents/legal-memos/<task_id>/` (default)

Files you'll find there:
- `memo.docx` — the final memo, formatted (Arial 12pt, 1" margins, numbered sections)
- `drafts/v*.md` — every draft revision
- `research/` — statutes, case law, doctrine notes, source pack
- `reviews/` — every reviewer's findings (JSON)
- `state.json` — full pipeline state
- `events.jsonl` — audit log

---

## Commands

| Command | What it does |
|---|---|
| `/legal-memo-writer:memo "<query>"` | Start a new memo |
| `/legal-memo-writer:continue <task_id> <action>` | Reply to an open checkpoint or resume a paused task |
| `/legal-memo-writer:status [<task_id>]` | Show phase, progress, blockers for one task or list all tasks |
| `/legal-memo-writer:style [<action> …]` | Manage custom style + formatting profiles (see [Customization](#customization)) |

`<task_id>` is the slug of the working directory (e.g. `memo-20260522T143010Z`). The pipeline prints it when the task starts.

---

## Modes — Brief vs Full

You pick the mode at the second checkpoint. Both produce a real memo with citations; they differ in depth.

|  | **Brief** | **Full** |
|---|---|---|
| Template | `executive-brief.md` | `classical-memo.md` |
| Target length | 1–3 pages | 5–15 pages |
| Researchers | Statutes + case law (doctrine optional) | All three in parallel |
| Reviewers | 3 (logic, citations, client-readiness) | 5 (all) |
| Revision rounds | 1 | up to 3 |
| Use case | Quick risk read for a known issue | Pre-launch sign-off, regulator response, cross-jurisdictional question |
| Typical runtime | 15–25 min | 40–50 min |

Mid-run switching is not supported — cancel and rerun if you picked the wrong mode.

---

## The pipeline — phase by phase

```
   ┌──────────────────────────────────────────────────────────────┐
   │  Phase 1   Task setup (resolve output folder, create state)  │
   │  Phase 2   Intake — fact-assumption-analyst                  │
   │  Phase 2a  ⏸  User checkpoint: answer or proceed             │
   │  Phase 3   Classification + template selection               │
   │  Phase 4   Research plan                                     │
   │  Phase 4a  ⏸  User checkpoint: approve / edit / cancel       │
   │  Phase 5   Parallel research (3 agents)                      │
   │  Phase 6   Research sufficiency review                       │
   │  Phase 7   Currency check + source pack build                │
   │  Phase 7.5 ⏸  Optional checkpoint: continue / summary-only   │
   │  Phase 8   Drafting — memo-writer                            │
   │  Phase 9   Revision loop — 5 reviewers + mediator (×N)       │
   │  Phase 10  Client-readiness polish                           │
   │  Phase 11  Export to .docx                                   │
   └──────────────────────────────────────────────────────────────┘
```

State persists between turns in `state.json` inside the work directory. If the host session dies, `/legal-memo-writer:continue <task_id>` resumes from the last completed phase.

---

## The agents — what each one does

The main session orchestrates; specialized worker subagents do the actual work. Plugin-shipped subagents cannot spawn other subagents (Anthropic security sandbox), so the orchestrator dispatches them via the `Agent` tool.

### Intake (Phase 2)
| Agent | Role |
|---|---|
| **fact-assumption-analyst** | Reads the query, identifies missing facts that would change the answer, drafts safe default assumptions, and produces up to 5 must-answer intake questions. |

### Researchers (Phase 5, parallel)
| Agent | Role |
|---|---|
| **statutory-researcher** | Primary normative acts: statutes, regulations, directives, secondary legislation. Routes through Legal Data Hunter MCP first; falls back to eCFR/govinfo via WebFetch for US. |
| **case-law-researcher** | Judgments, decisions, opinions. US case law goes to CourtListener MCP; multi-jurisdictional case law to Legal Data Hunter. Structures findings as prevailing / conflicting / recent positions. |
| **doctrinal-researcher** | Activated only when the plan calls for it. Searches regulator guidance (EDPB, national DPAs, etc.), soft law, and peer-reviewed academic commentary. The only researcher allowed to cite third-party authoritative sources for primary-law-adjacent material. |

### Quality gates (Phases 6–7, 11)
| Agent | Role |
|---|---|
| **research-sufficiency-reviewer** | Checks every planned issue has enough primary sources, contrary authority, and explicit gaps before drafting starts. |
| **currency-checker** | Verifies sources are still current law: cross-references between acts, status of cited judgments, age of doctrinal guidance, URL reachability. Produces a blocking / non-blocking report. |
| **source-pack-builder** | Consolidates research and currency reports into a structured evidence table the writer and citation auditor work from. After this, no later agent discovers new sources (source-pack freeze). |
| **citation-auditor** | After drafting, audits every citation against the source pack — verifies the claim is grounded, the paraphrase matches the source, and currency-blocking sources weren't cited. |

### Drafting (Phase 8)
| Agent | Role |
|---|---|
| **memo-writer** | Writes (v1) or rewrites (vN) the memo per the selected template (executive-brief or classical-memo). Produces IRAC analysis per issue, full citations, risk scores, and recommendations. Reads `state.json` to honor mode, assumptions-accepted flag, and currency-blocked sources. |

### Reviewers (Phase 9, run in parallel)
Five specialists in Full mode, three in Brief. Each returns a structured JSON report with `blocking_issues[]` and `improvements[]`.

| Agent | What they check |
|---|---|
| **logic-reviewer** | IRAC soundness, premise-conclusion validity, inter-issue consistency, risk-score drift across sections, Material Assumption ↔ Open Question mapping. |
| **citation-auditor** | Every normative / case / doctrinal claim is grounded, paraphrases match sources, currency-blocked sources respected. |
| **style-reviewer** *(Full only)* | AI-tells, em-dash overuse, vague attributions, heading discipline (no questions, no skip-jumps), `(§ N)` cross-references, action-verb recommendations. |
| **clarity-reviewer** *(Full only)* | Sentence length (≤40 words), paragraph length (≤3 sentences / 100 words), jargon-without-explanation, accessibility for a non-lawyer business stakeholder, per-section length proportionality. |
| **counterargument-reviewer** *(Full only)* | Contrary authority, overconfidence at medium verdicts, trigger conditions for counter-arguments that don't prevail. |

### Mediation & polish (Phases 9–10)
| Agent | Role |
|---|---|
| **revision-mediator** | Consolidates parallel reviewer JSONs into a single actionable revision list for the writer. Resolves reviewer conflicts via house-style priority (logic ≈ citations > style > clarity). Decides whether another iteration is needed. |
| **client-readiness-reviewer** | Final external-client gate. Checks tone, disclaimers, confidentiality, recommendation quality, and whether the memo ships with minimal manual edits. In Brief mode, also runs the style / clarity / counter-argument safety-net checks that were skipped earlier. |

---

## Skills

The plugin ships three slash commands. Methodology and rendering live under `lib/` as internal modules, read by the pipeline but not exposed in slash autocomplete.

| Skill | Type | Purpose |
|---|---|---|
| `memo` | Entry (`/legal-memo-writer:memo`) | Main orchestrator. Loaded once at task start, drives the whole pipeline. |
| `continue` | Entry (`/legal-memo-writer:continue`) | Reply to checkpoints or resume a paused task. |
| `status` | Entry (`/legal-memo-writer:status`) | Inspect one task or list all tasks. |

### Internal library modules (`lib/`)

Not slash commands — the pipeline reads these via `Read` or invokes them via `Bash`. Edit them to customize behaviour.

| Module | Used at | Purpose |
|---|---|---|
| `lib/prose-style.md` | Drafting + revision | House style: tone, four-beat Risk pattern, definitions format, anti-AI-tells, reviewer conflict priorities. Edit to customize style. |
| `lib/docx-render/` | Phase 11 export | DOCX renderer: Arial 12pt, 1" margins, blockquote indent, optional yellow warning banner. `lib/docx-render/scripts/md_to_docx.py` (python-docx) with Pandoc as fallback; `lib/docx-render/README.md` documents the spec. |
| `lib/revision-loop.md` | Phase 9 revision | Methodology for the mode-aware revision loop (3 reviewers Brief, 5 Full; 1 iter Brief, up to 3 Full). |

---

## MCP and web search policy

Single source of truth: `skills/memo/references/pipeline-contract.md §WebSearch`.

- **Bundled MCPs:** Legal Data Hunter (`https://legaldatahunter.com/mcp`), CourtListener (`https://mcp.courtlistener.com`).
- **Primary law search:** MCPs first. Legal Data Hunter for broad multi-jurisdictional sources; CourtListener for US case law, PACER/RECAP dockets, citation networks, and citation verification.
- **WebSearch:** discovery only (find CELEX numbers, docket IDs, canonical URLs, news of amendments). **WebSearch results MUST NEVER be cited as the source of a legal claim.** The canonical text is retrieved via MCP or WebFetch on the discovered official URL.
- **`doctrinal-researcher` exception:** may cite WebFetch results from official regulator guidance, peer-reviewed journals, SSRN-style repositories, and authoritative soft-law sources.
- **MCP unavailable:** WebFetch against known official portals. If no canonical URL is available, the gap is documented explicitly — never fabricated.
- **MCP rate-limited:** back off once with same query, then WebFetch on canonical URLs. Logs `mcp_ratelimit_fallback` event and surfaces a partial-research banner in the memo.

---

## Customization

### Style Studio — your own house style and template (recommended)

Define your style **once**, apply to every memo. The plugin reads your saved profile during Phase 1.5; the writer and reviewers then follow YOUR rules instead of the bundled ones.

**Create a profile** — three input modes:

```bash
# From example memos (PDFs, .docx, .md, .txt)
/legal-memo-writer:style new my-firm --examples ~/memos/2025-q4/ --mode full

# From written rules (inline text or path to a .md file)
/legal-memo-writer:style new compact --rules "no em-dashes; OSCOLA citations; ALL CAPS headings" --mode brief

# Both (rules win on conflict)
/legal-memo-writer:style new acme --examples ~/memos/acme/ --rules ~/style/acme-rules.md --mode full
```

Or just run `/legal-memo-writer:style` with no arguments for an interactive menu.

The Style Studio extractor (Opus subagent) reads your inputs and writes `prose-style.md` + `template.md` + `meta.json` into `~/.claude/plugin-data/legal-memo-writer/profiles/<name>/`. The files are plain markdown — open and edit them by hand if you want.

**Pick a default** so `/legal-memo-writer:memo` preselects it:

```bash
/legal-memo-writer:style use my-firm
```

**Other actions:**

```bash
/legal-memo-writer:style list              # Table of all profiles, mode bindings, defaults
/legal-memo-writer:style show my-firm      # Print meta.json + first 30 lines of style/template
/legal-memo-writer:style delete my-firm    # Remove (with confirmation if it was default)
/legal-memo-writer:style use --clear       # Drop the default — Phase 1.5 will offer all profiles next time
```

**One profile, one mode.** A Brief-bound profile applies to executive-briefs (1-3 pages); a Full-bound profile to classical-memos (5-15 pages). If you need both shapes for the same house style, create two profiles (e.g. `my-firm-brief` + `my-firm-full`).

**Zero overhead when empty.** If you never create a profile, `/legal-memo-writer:memo` runs identically to the pre-Style-Studio versions — no extra prompts, no behaviour change. The Phase 1.5 style-pick checkpoint appears only when at least one profile exists.

**Profile-aware reviewers.** When a custom profile is in effect, `style-reviewer`, `clarity-reviewer`, `logic-reviewer`, `counterargument-reviewer`, and `revision-mediator` all defer to YOUR rules — em-dashes you allow are not flagged, the cap you set replaces the 40-word default, the cross-reference notation you use replaces `(§ N)`. Substantive checks (IRAC, citation accuracy, contrary authority) stay uniform.

### House style without profiles (manual)

If you prefer to edit the bundled style directly (legacy path; affects every user of this plugin install, not just one user):

- Edit `lib/prose-style.md` for tone, sentence/paragraph caps, anti-patterns, reviewer conflict priorities.
- Edit `templates/classical-memo.md` or `templates/executive-brief.md` for the document structure.
- In Cowork: files live at `~/.claude/plugins/cache/legal-memo-writer/lib/` and `.../templates/`.
- In Claude Code dev mode: edit the files in your plugin source directory.

### Output folder (resolution order)
1. `CLAUDE_PLUGIN_OPTION_OUTPUT_FOLDER` (set in Cowork plugin settings)
2. `LEGAL_MEMO_OUTPUT_FOLDER` (env var)
3. `~/Documents/legal-memos/` (default)

---

## Live progress

The plugin emits **at least 17 chat progress messages** in a Full run — phase transitions, agent dispatches, gate answers, validator runs. File references in chat are plain text; clickable artifact cards come from the host's tool-call UI (Cowork's Read/Write/Edit indicators).

Every task also writes an audit log at `<work_dir>/events.jsonl` — JSONL events for `phase_transition`, `agent_dispatched`, `agent_returned`, `gate_answered`, `validator_ran`, and Tier-0 events (`task_created`, `mcp_precheck_result`, `mode_selected`, `mcp_ratelimit_fallback`, etc.). Useful for debugging or replaying a pipeline run.

---

## Always-deliver invariant

Every termination path produces a user-facing artifact. If the docx export fails, the plugin falls back to:
1. Pandoc-based docx render
2. Plain markdown delivery (last resort)

You never end a session with nothing. See `skills/memo/references/always-deliver.md` for the full fallback matrix.

---

## Known limitations

- **No cross-task memory.** Each memo is a fresh task; the plugin does not learn from prior memos.
- **HITL UI** depends on the host. Cowork shows interactive widgets via `visualize:show_widget`; Claude Code falls back to text/file-based checkpoints.
- **Three mandatory user checkpoints** in the default path: intake (Phase 2a), mode (Phase 1.5), plan (Phase 4a). A fourth style-profile checkpoint at Phase 1.5 appears only when the user has at least one saved Style Studio profile. One optional gate after source pack: source review (Phase 7.5).
- **Pandoc docx fallback** is best-effort; primary path is `md_to_docx.py` via python-docx.
- **No generic WebSearch fallback** for statutes / case law when MCP is down. Either canonical primary source via WebFetch, or the gap is reported explicitly.
- **Mid-run mode switching** is not supported — cancel and rerun in the other mode.
- **Claude Code state persistence** between turns differs from Cowork; v0.4.0 guarantees Cowork, Claude Code is best-effort.

---

## Repo layout

```
legal-memo-writer/
├── .claude-plugin/plugin.json     # Plugin manifest
├── .mcp.json                      # Bundled MCP servers (Legal Data Hunter, CourtListener)
├── agents/                        # 16 worker subagents (15 pipeline + style-extractor)
├── skills/                        # 4 entry skills: memo, continue, status, style
├── templates/                     # classical-memo, executive-brief, research-summary-only (built-in fallbacks)
├── lib/                           # Internal modules: prose-style.md, revision-loop.md, docx-render/
├── scripts/                       # log_event.py, validate_*.py, resolve_*.py, tests/
├── dist/                          # Build artifacts (gitignored, published to Releases)
├── README.md
└── CHANGELOG.md                   # Version history
```

---

## Versioning

Plugin version is the single source of truth in `.claude-plugin/plugin.json`. The README badge, the latest `dist/*.zip` filename, and the latest `git tag` MUST match. CHANGELOG follows a relaxed [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Contributing

Issues and PRs welcome. For non-trivial changes, please open an issue first to discuss the approach. Run `python3 -m unittest discover -s scripts/tests` before submitting.
