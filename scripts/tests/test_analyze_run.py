"""Smoke tests for scripts/analyze_run.py.

Run from the plugin root:
    python3 -m unittest scripts.tests.test_analyze_run

Targets the behaviour the optimization plan depends on:
- A slow run (events truncated mid-revision-loop + serial reviewer staircase)
  is detected: events_truncated True, >=1 serial round, score regression flagged.
- A fast run (complete events + clustered/parallel reviewer mtimes) shows
  events_truncated False and zero serial rounds.
- Missing inputs exit 2; malformed event lines are tolerated; --compare runs.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ANALYZER = PLUGIN_ROOT / "scripts" / "analyze_run.py"

BASE = dt.datetime(2026, 1, 1, 10, 0, 0, tzinfo=dt.timezone.utc)


def at(minutes: float) -> dt.datetime:
    return BASE + dt.timedelta(minutes=minutes)


def iso(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_file(path: Path, content: str, when: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts = when.timestamp()
    os.utime(path, (ts, ts))


def write_events(workdir: Path, events: list[dict], last_when: dt.datetime) -> None:
    p = workdir / "events.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    ts = last_when.timestamp()
    os.utime(p, (ts, ts))


def transition(ts: dt.datetime, to: str, reason: str, frm: str = "") -> dict:
    return {"ts": iso(ts), "event": "phase_transition", "phase": to, "iteration": None,
            "actor": "memo-skill", "severity": "info",
            "data": {"from": frm, "to": to, "reason": reason}}


def run_analyzer(*args: str) -> tuple[int, dict, str]:
    result = subprocess.run(
        [sys.executable, str(ANALYZER), *args, "--json"],
        capture_output=True, text=True,
    )
    parsed = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, parsed, result.stderr


def build_slow_run(td: Path) -> None:
    """Events die at revision_loop; one serial reviewer staircase; score regresses."""
    events = [
        {"ts": iso(at(0)), "event": "task_created", "phase": "intake_preliminary_research",
         "actor": "memo-skill", "data": {"task_id": "memo-slow"}},
        transition(at(5), "research", "plan_approved", "plan_approval_pending"),
        transition(at(50), "drafting", "user_continue", "source_review_pending"),
        transition(at(60), "revision_loop", "v1_done", "drafting"),  # last event
    ]
    write_events(td, events, at(60))

    state = {
        "task_id": "memo-slow", "mode": "full",
        "created_at": iso(at(0)),
        "config": {"reviewer_list": ["logic", "clarity", "style", "citations", "counterarguments"]},
        "final_status": "forced_exit_on_v3_with_remaining_issues",
        "iterations": [
            {"iteration": 1, "aggregate_score": 81.8, "verdict": "needs_revision", "blocking_count": 12},
            {"iteration": 2, "aggregate_score": 87.2, "verdict": "needs_revision", "blocking_count": 9},
            {"iteration": 3, "aggregate_score": 86.0, "verdict": "forced_exit", "blocking_count": 6},
        ],
    }
    write_file(td / "state.json", json.dumps(state), at(90))

    # v1 draft, then a SERIAL reviewer staircase in reviewer_list order.
    write_file(td / "drafts" / "v1.md", "draft", at(62))
    serial = {"logic": 64, "clarity": 70, "style": 78, "citations": 82, "counterarguments": 85}
    for kind, m in serial.items():
        write_file(td / "reviews" / f"v1-{kind}.json",
                   json.dumps({"reviewer": kind, "verdict": "needs_revision"}), at(m))
    write_file(td / "reviews" / "v1-mediator.md", "mediator", at(87))


def build_fast_run(td: Path) -> None:
    """Complete events through done; reviewers cluster (parallel); single clean iter."""
    events = [
        {"ts": iso(at(0)), "event": "task_created", "phase": "intake_preliminary_research",
         "actor": "memo-skill", "data": {"task_id": "memo-fast"}},
        transition(at(5), "research", "plan_approved", "plan_approval_pending"),
        transition(at(50), "drafting", "user_continue", "source_review_pending"),
        transition(at(60), "revision_loop", "v1_done", "drafting"),
        transition(at(64), "client_readiness", "approved_on_v1", "revision_loop"),
        transition(at(65), "export", "polish_done", "client_readiness"),
        transition(at(66), "done", "docx_written", "export"),
    ]
    write_events(td, events, at(66))

    state = {
        "task_id": "memo-fast", "mode": "full",
        "created_at": iso(at(0)),
        "config": {"reviewer_list": ["logic", "clarity", "style", "citations", "counterarguments"]},
        "final_status": "approved_on_v1",
        "iterations": [
            {"iteration": 1, "aggregate_score": 90.0, "verdict": "approved", "blocking_count": 0},
        ],
    }
    write_file(td / "state.json", json.dumps(state), at(66))

    write_file(td / "drafts" / "v1.md", "draft", at(60))
    # All five complete within ~40s of each other → clustered, not serial.
    cluster = {"logic": 62.0, "clarity": 62.2, "style": 62.4, "citations": 62.6, "counterarguments": 62.8}
    for kind, m in cluster.items():
        write_file(td / "reviews" / f"v1-{kind}.json",
                   json.dumps({"reviewer": kind, "verdict": "approved"}), at(m))
    write_file(td / "reviews" / "v1-mediator.md", "mediator", at(63))


class TestSlowRun(unittest.TestCase):
    def test_detects_truncation_serial_and_regression(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            build_slow_run(tdp)
            code, m, err = run_analyzer("--workdir", str(tdp))
            self.assertEqual(code, 0, err)
            self.assertTrue(m["events_truncated"], "should detect the dark-events gap")
            self.assertEqual(m["events_died_at_phase"], "revision_loop")
            self.assertGreaterEqual(m["serial_round_count"], 1, "serial staircase must flag")
            self.assertEqual(m["score_regressions_at_iter"], [3])
            self.assertIsNotNone(m["total_s"])
            self.assertGreater(m["total_s"], 0)

    def test_serial_round_estimates_recoverable_time(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            build_slow_run(tdp)
            _, m, _ = run_analyzer("--workdir", str(tdp))
            r = next(r for r in m["revision_rounds"] if r["iteration"] == 1)
            self.assertTrue(r["serial"])
            self.assertEqual(r["order"],
                             ["logic", "clarity", "style", "citations", "counterarguments"])
            self.assertTrue(r["monotonic_in_list_order"])
            self.assertIsNotNone(r["savings_est_s"])
            self.assertGreater(r["savings_est_s"], 0)


class TestFastRun(unittest.TestCase):
    def test_complete_events_no_serial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            build_fast_run(tdp)
            code, m, err = run_analyzer("--workdir", str(tdp))
            self.assertEqual(code, 0, err)
            self.assertFalse(m["events_truncated"])
            self.assertEqual(m["serial_round_count"], 0, "clustered reviewers are not serial")
            self.assertEqual(m["score_regressions_at_iter"], [])


class TestEdgeCases(unittest.TestCase):
    def test_missing_inputs_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, _, _ = run_analyzer("--workdir", str(Path(td)))
            self.assertEqual(code, 2)

    def test_malformed_lines_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "events.jsonl").write_text(
                json.dumps({"ts": iso(at(0)), "event": "task_created",
                            "actor": "memo-skill", "data": {}}) + "\n"
                + "{ this is not valid json\n",
                encoding="utf-8",
            )
            code, m, err = run_analyzer("--workdir", str(tdp))
            self.assertEqual(code, 0, err)
            self.assertEqual(m["malformed_event_lines"], 1)

    def test_compare_runs(self) -> None:
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            build_slow_run(Path(ta))
            build_fast_run(Path(tb))
            result = subprocess.run(
                [sys.executable, str(ANALYZER), "--compare", ta, tb],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("compare", result.stdout)
            self.assertIn("serial reviewer rounds", result.stdout)


if __name__ == "__main__":
    unittest.main()
