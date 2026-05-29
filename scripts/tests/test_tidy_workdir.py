"""Tests for scripts/tidy_workdir.py (Phase 12.5 work_dir tidy).

Run from the plugin root:
    python3 -m unittest scripts.tests.test_tidy_workdir

Covers the behaviour the pipeline depends on:
- Normal completion deletes side-car HTML + stray .py + recursive .tmp.
- The canonical master live-progress.html is PRESERVED (only hyphen side-cars go).
- The keep-list (docx/md/state/events/plan/changelog) and subdir contents survive.
- Subdirectory *.py / *.html are NOT touched (only recursive *.tmp is).
- Forensic guards (failed / cancelled / fallback_ / unfinished) skip entirely.
- --dry-run reports targets but deletes nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TIDY = PLUGIN_ROOT / "scripts" / "tidy_workdir.py"


def _seed_workdir(td: Path, *, final_status="approved_on_v3", current_phase="done") -> None:
    """Create a representative finished work_dir with junk + keep-list + subdirs."""
    state = {
        "task_id": "memo-test",
        "current_phase": current_phase,
        "final_status": final_status,
    }
    (td / "state.json").write_text(json.dumps(state), encoding="utf-8")

    # --- top-level keep-list ---
    for keep in (
        "memo-test.docx",
        "memo-test.md",
        "events.jsonl",
        "plan.md",
        "changelog.md",
        "live-progress.html",  # master — MUST survive
    ):
        (td / keep).write_text("x", encoding="utf-8")

    # --- top-level junk that MUST go ---
    for side_car in (
        "live-progress-tmp.html",
        "live-progress-logic-start.html",
        "live-progress-clarity-done.html",
        "live-progress-cr-done.html",
    ):
        (td / side_car).write_text("x", encoding="utf-8")
    (td / "_update_state.py").write_text("x", encoding="utf-8")
    (td / "live-progress.html.tmp").write_text("x", encoding="utf-8")

    # --- subdirs: contents must survive (except recursive *.tmp) ---
    for sub in ("intake", "research", "drafts", "reviews", "logs", "widgets", "checkpoints"):
        (td / sub).mkdir()
    (td / "drafts" / "v1.md").write_text("x", encoding="utf-8")
    (td / "widgets" / "phase12-final-dashboard.html").write_text("x", encoding="utf-8")
    # A .py living INSIDE a subdir is out of scope for the top-level *.py rule.
    (td / "research" / "helper.py").write_text("x", encoding="utf-8")
    # A nested *.tmp IS in scope (recursive).
    (td / "reviews" / "scratch.tmp").write_text("x", encoding="utf-8")


def _run(workdir: Path, *extra: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(TIDY), "--workdir", str(workdir), "--json", *extra],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr  # best-effort: always exit 0
    return json.loads(result.stdout)


class TestTidyWorkdir(unittest.TestCase):
    def test_normal_completion_removes_junk(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd)
            report = _run(wd)

            self.assertFalse(report["skipped"], report)
            # 4 side-cars + 1 stray .py + 2 .tmp (top-level + nested) = 7
            self.assertEqual(report["counts"]["side_car_html"], 4)
            self.assertEqual(report["counts"]["stray_py"], 1)
            self.assertEqual(report["counts"]["tmp_files"], 2)

    def test_master_dashboard_and_keeplist_survive(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd)
            _run(wd)

            for keep in (
                "memo-test.docx",
                "memo-test.md",
                "state.json",
                "events.jsonl",
                "plan.md",
                "changelog.md",
                "live-progress.html",  # master preserved
            ):
                self.assertTrue((wd / keep).exists(), f"{keep} should survive")

    def test_side_cars_and_stray_py_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd)
            _run(wd)

            for gone in (
                "live-progress-tmp.html",
                "live-progress-logic-start.html",
                "live-progress-clarity-done.html",
                "live-progress-cr-done.html",
                "_update_state.py",
                "live-progress.html.tmp",
            ):
                self.assertFalse((wd / gone).exists(), f"{gone} should be deleted")

    def test_subdir_contents_preserved_except_tmp(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd)
            _run(wd)

            # Subdir files survive...
            self.assertTrue((wd / "drafts" / "v1.md").exists())
            self.assertTrue((wd / "widgets" / "phase12-final-dashboard.html").exists())
            # ...including a .py inside a subdir (top-level rule only)...
            self.assertTrue((wd / "research" / "helper.py").exists())
            # ...but a nested *.tmp is swept (recursive rule).
            self.assertFalse((wd / "reviews" / "scratch.tmp").exists())

    def test_dry_run_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd)
            report = _run(wd, "--dry-run")

            self.assertTrue(report["dry_run"])
            self.assertEqual(len(report["removed"]), 7)
            # Everything still on disk.
            self.assertTrue((wd / "_update_state.py").exists())
            self.assertTrue((wd / "live-progress-cr-done.html").exists())
            self.assertTrue((wd / "reviews" / "scratch.tmp").exists())

    def test_skip_on_failed_phase(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd, current_phase="failed")
            report = _run(wd)

            self.assertTrue(report["skipped"])
            self.assertIn("failed", report["reason"])
            self.assertTrue((wd / "_update_state.py").exists())  # untouched

    def test_skip_on_cancelled_phase(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd, current_phase="cancelled_by_user")
            report = _run(wd)
            self.assertTrue(report["skipped"])
            self.assertTrue((wd / "live-progress-cr-done.html").exists())

    def test_skip_on_fallback_status(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd, final_status="fallback_research_summary_delivered")
            report = _run(wd)
            self.assertTrue(report["skipped"])
            self.assertIn("fallback", report["reason"])

    def test_skip_on_unfinished_run(self):
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            _seed_workdir(wd, final_status="")
            report = _run(wd)
            self.assertTrue(report["skipped"])
            self.assertIn("not finished", report["reason"])

    def test_missing_workdir_is_best_effort(self):
        report = _run(Path(tempfile.gettempdir()) / "memoforge-nonexistent-xyz")
        self.assertTrue(report["skipped"])
        self.assertIn("not found", report["reason"])


if __name__ == "__main__":
    unittest.main()
