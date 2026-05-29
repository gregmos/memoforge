#!/usr/bin/env python3
"""Tidy a finished memoforge task work_dir (Phase 12.5).

Deletes the intermediate / off-contract junk that accumulates at the TOP LEVEL
of a task work_dir during a run, leaving the user with a clean deliverable
folder. This is the deterministic engine behind Phase 12.5 — both the `memo`
skill (`references/phases/phase-12_5.md`) and the `continue` skill (`### done`
branch) invoke it with a single Bash line instead of inlining `find ... -delete`
(which is GNU-find-only, silently swallows every error, and was never portable
to a Windows/PowerShell host).

WHY a script and not inline bash: the real 2026-05-29 run
(`memo-20260529T084546Z-gdpr-ai-support-transcripts`) finished cleanly
(`approved_on_v3`) yet left 7 side-car `live-progress-*.html` files and a stray
`_update_state.py` at the top level — because the run's final segment was driven
by the `continue` skill, whose `### done` branch had no tidy step at all (tidy
lived only in the `memo` skill's phase files, and a full run always ends via
`continue`). Folding the logic into ONE tested script that BOTH skills call is
the structural fix: one deterministic call is far harder to drop under
context-summarization than a multi-line `find` block, and it reports what it did
instead of swallowing failures.

WHAT IT DELETES (all best-effort — a failure on one file never aborts the rest):

1. Top-level (non-recursive) ``live-progress-*.html`` — the per-phase /
   per-reviewer SIDE-CAR snapshots an orchestrator improvises off-contract
   (``live-progress-clarity-done.html``, ``live-progress-cr-start.html``,
   ``live-progress-tmp.html``, …). The live-progress contract
   (``references/live-progress-contract.md`` §HARD RULE, v0.7.2) forbids
   side-cars; tidy is the catch-net. NOTE the hyphen in the glob:
   ``live-progress-*.html`` matches only the side-cars and PRESERVES the
   canonical master ``live-progress.html`` (see "What stays" below).

2. Top-level (non-recursive) ``*.py`` — canonical scripts live at
   ``${CLAUDE_PLUGIN_ROOT}/scripts/`` and are NEVER copied into a work_dir, so any
   ``*.py`` at a work_dir top level is a stray inline helper a subagent wrote
   instead of calling the canonical script (e.g. ``_update_state.py``).

3. ``*.tmp`` ANYWHERE under the work_dir (recursive) — atomic-write leftovers
   from interrupted ``write X.tmp; mv X.tmp X`` sequences (incl.
   ``live-progress.html.tmp``). If the interrupt happened, the destination
   already holds the prior valid content; the ``.tmp`` is garbage.

WHAT STAYS at the top level: the deliverable (``memo-<slug>.docx`` / ``.md``),
``state.json``, ``events.jsonl``, ``plan.md``, ``changelog.md``, the canonical
master ``live-progress.html`` (one self-contained "delivered"-state dashboard is
useful in a folder the user keeps/shares/archives — unlike the originating Cowork
chat's artifact card, the folder has no other fallback), and every canonical
subdirectory (``intake/ research/ drafts/ reviews/ logs/ widgets/ checkpoints/``).
Subdirectory contents are never touched except recursive ``*.tmp``.

WHEN IT SKIPS (leaves the work_dir completely untouched for forensics): when
``state.json`` is unreadable, when ``final_status`` is unset (run not finished)
or starts with ``fallback_``, or when ``current_phase`` is ``failed`` /
``cancelled_by_user``. Mirrors ``phase-12_5.md`` §"When NOT to run tidy".

Usage:
    python3 scripts/tidy_workdir.py --workdir <task work_dir>
    python3 scripts/tidy_workdir.py --workdir <dir> --dry-run        # report only
    python3 scripts/tidy_workdir.py --workdir <dir> --json           # machine-readable

Exit code is ALWAYS 0 on a reachable work_dir (best-effort posture — tidy must
never break a finished pipeline). Argparse usage errors exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional


def _load_state(workdir: Path) -> Optional[dict[str, Any]]:
    """Read <workdir>/state.json. Returns None if missing or unparseable."""
    state_path = workdir / "state.json"
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def skip_reason(state: Optional[dict[str, Any]]) -> Optional[str]:
    """Return a human reason to SKIP tidy, or None to proceed.

    Mirrors phase-12_5.md §"When NOT to run tidy": only normal completions
    (approved_/forced_exit_/manual_review_required_/accepted_early_on_v<N>) tidy.
    """
    if state is None:
        return "state.json unreadable — skipping tidy (nothing deleted)"
    phase = state.get("current_phase")
    if phase in ("failed", "cancelled_by_user"):
        return f"current_phase={phase} — forensic state, leaving work_dir untouched"
    final_status = state.get("final_status")
    if isinstance(final_status, str) and final_status.startswith("fallback_"):
        return f"final_status={final_status} — fallback path, leaving work_dir untouched"
    if not final_status:
        return "final_status not set — run not finished, skipping tidy"
    return None


def _collect_targets(workdir: Path) -> dict[str, list[Path]]:
    """Find deletion candidates. Extensions are mutually exclusive, so no dedup."""
    return {
        # Hyphen in the glob is deliberate: matches side-cars, preserves master
        # live-progress.html.
        "side_car_html": sorted(
            p for p in workdir.glob("live-progress-*.html") if p.is_file()
        ),
        "stray_py": sorted(p for p in workdir.glob("*.py") if p.is_file()),
        # Recursive — *.tmp is always atomic-write garbage wherever it lands.
        "tmp_files": sorted(p for p in workdir.rglob("*.tmp") if p.is_file()),
    }


def tidy(workdir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Run the tidy pass. Always returns a report dict; never raises on file ops."""
    state = _load_state(workdir)
    reason = skip_reason(state)
    if reason is not None:
        return {
            "skipped": True,
            "reason": reason,
            "removed": [],
            "failed": [],
            "dry_run": dry_run,
        }

    targets = _collect_targets(workdir)
    removed: list[str] = []
    failed: list[dict[str, str]] = []

    for category, paths in targets.items():
        for path in paths:
            rel = path.relative_to(workdir).as_posix()
            if dry_run:
                removed.append(rel)
                continue
            try:
                path.unlink()
                removed.append(rel)
            except OSError as exc:  # best-effort: record and keep going
                failed.append({"path": rel, "error": str(exc), "category": category})

    return {
        "skipped": False,
        "reason": None,
        "counts": {k: len(v) for k, v in targets.items()},
        "removed": removed,
        "failed": failed,
        "dry_run": dry_run,
    }


def _print_human(report: dict[str, Any]) -> None:
    if report["skipped"]:
        print(f"tidy: skipped — {report['reason']}")
        return
    verb = "would remove" if report["dry_run"] else "removed"
    counts = report.get("counts", {})
    summary = (
        f"{counts.get('side_car_html', 0)} side-car dashboard(s), "
        f"{counts.get('stray_py', 0)} stray .py, "
        f"{counts.get('tmp_files', 0)} .tmp leftover(s)"
    )
    # ASCII hyphen (not em-dash) so the status line is clean on cp1252 consoles.
    print(f"tidy: {verb} {len(report['removed'])} file(s) - {summary}")
    for rel in report["removed"]:
        print(f"  - {rel}")
    if report["failed"]:
        print(f"tidy: {len(report['failed'])} file(s) could not be removed (ignored):")
        for f in report["failed"]:
            print(f"  ! {f['path']}: {f['error']}")
    print("tidy: kept master live-progress.html + deliverable + audit trail.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tidy a finished memoforge task work_dir (Phase 12.5)."
    )
    parser.add_argument(
        "--workdir",
        required=True,
        help="Task work_dir (the directory that contains state.json).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit the report as JSON instead of human text.",
    )
    args = parser.parse_args(argv)

    workdir = Path(args.workdir)
    if not workdir.is_dir():
        # Best-effort: a missing work_dir is not an error worth failing a finished
        # pipeline over. Report and exit 0.
        report = {
            "skipped": True,
            "reason": f"work_dir not found: {workdir}",
            "removed": [],
            "failed": [],
            "dry_run": args.dry_run,
        }
    else:
        report = tidy(workdir, dry_run=args.dry_run)

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
