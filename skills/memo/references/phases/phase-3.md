<!-- Extracted from SKILL.md (B1b router refactor). Control flow is authoritative in skills/memo/PHASE-MACHINE.md; this file is the full procedure prose for the phase(s) below. -->

## Phase 3 — Classify & build plan

Read:
- Original user query from `state.json`.
- `intake/fact-assumption-report.md`.
- `intake/user-facts.md` if it exists.
- `lib/prose-style.md`.

Classify:
- **Type**: `regulatory_analysis` / `transactional` / `litigation_risk` / `cross_border` / `compliance_check` / `mixed`
- **Jurisdictions** (priority-ordered list, e.g. `[EU, CY]`)
- **Doctrine required**: `yes` / `no` with one-sentence justification
- **Complexity**: `low` / `medium` / `high`

**Template selection** — read `state.json.config.template_id` and set `selected_template_id` directly:

```
selected_template_id = state.json.config.template_id
```

This is the entire template-selection logic in Phase 3. Brief mode hard-codes `executive-brief`; Full mode hard-codes `classical-memo`. The classifier does NOT pick the template — the template is a function of the mode chosen at Phase 1.5. If `selected_template_id` would be `null` or empty at this point, that is a pipeline-state bug — Phase 1.5 should have written `config.template_id`; surface to the user and stop.

Write a one-line note in `plan.md`: "Template `<selected_template_id>` set by `<mode>` mode."

The classifier still produces `type`/`jurisdictions`/`doctrine_required`/`complexity` — those drive the dispatched-researcher decisions (doctrinal only fires when `doctrine_required: yes`) and provide context for `plan.md`. They no longer feed template selection.

Read `${CLAUDE_PLUGIN_ROOT}/templates/<template_id>.md` to understand the template structure.

Write `plan.md` to the working directory with:
- Understanding of the query (2-3 paragraphs in English)
- Facts provided by user
- Assumptions adopted from intake
- Critical missing facts still unresolved
- Classification (type, jurisdictions, complexity)
- Selected template + rationale
- Issues to research (numbered list)
- Researchers to run (statutory always; case-law almost always; doctrinal per flag)
- Doctrine: yes/no + rationale
- Expected source hierarchy
- Estimated budget (informational)

Update `state.json.classification`, `state.json.plan_approval.status = pending`, add plan approval iteration 1, and set `state.json.current_phase = plan_approval_pending`.

**TodoWrite update.** Mark item #3 ("Build research plan") = `completed`, item #4 ("Plan approval") = `in_progress`. Silent skip if unavailable.

Create `checkpoints/plan-approval.md` with the first iteration:
```markdown
# Plan approval history

## Iteration 1 — proposed
<full text of plan.md>
```

