"""Coverage guard for skills/memo/PHASE-MACHINE.md.

Run from the plugin root:
    python3 -m unittest scripts.tests.test_phase_machine_coverage

Ensures the control-flow cheat-sheet stays in 1:1 sync with the canonical
phase enumeration (scripts/validate_state.py PHASES_ORDERED): every non-legacy
phase has exactly one cheat-sheet row, and the two invariants the cheat-sheet
exists to re-inject (PARALLEL dispatch + re-read-at-each-boundary) are present.
If a future change adds a phase to the state machine but forgets the cheat-sheet
row, this test fails.
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CHEATSHEET = PLUGIN_ROOT / "skills" / "memo" / "PHASE-MACHINE.md"
VALIDATOR = PLUGIN_ROOT / "scripts" / "validate_state.py"
SKILL = PLUGIN_ROOT / "skills" / "memo" / "SKILL.md"
PHASES_DIR = PLUGIN_ROOT / "skills" / "memo" / "references" / "phases"

# Legacy phases that intentionally have no cheat-sheet row.
LEGACY_PHASES = {"heartbeat_pending"}


def load_phases_ordered() -> list[str]:
    spec = importlib.util.spec_from_file_location("validate_state", VALIDATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.PHASES_ORDERED)


class TestPhaseMachineCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(CHEATSHEET.is_file(), "PHASE-MACHINE.md must exist")
        self.text = CHEATSHEET.read_text(encoding="utf-8")
        self.phases = load_phases_ordered()

    def test_every_phase_has_exactly_one_row(self) -> None:
        for phase in self.phases:
            if phase in LEGACY_PHASES:
                # Legacy phase must NOT appear as a row.
                self.assertNotIn(f"| `{phase}` |", self.text,
                                 f"legacy phase {phase} should not have a cheat-sheet row")
                continue
            count = self.text.count(f"| `{phase}` |")
            self.assertEqual(count, 1,
                             f"phase '{phase}' should have exactly 1 cheat-sheet row, found {count}")

    def test_no_unknown_phase_rows(self) -> None:
        # Every `phase` cell in the row table must be a known phase (catches typos).
        # "current_phase" is the table-header cell, not a phase row.
        known = set(self.phases) | {"research_sufficiency_followup_pending", "current_phase"}
        rows = re.findall(r"^\| `([a-z_]+)` \|", self.text, flags=re.MULTILINE)
        for cell in rows:
            self.assertIn(cell, known, f"cheat-sheet row references unknown phase '{cell}'")

    def test_key_invariants_present(self) -> None:
        # The two instructions the 2026-05-28 run lost must be in the file.
        self.assertIn("PARALLEL", self.text, "parallel-dispatch reminder missing")
        self.assertRegex(self.text, r"(?i)re-read.{0,40}(every|each).{0,20}phase boundary")
        self.assertIn("ONE message", self.text, "single-message dispatch rule missing")


class TestRouterPhaseFiles(unittest.TestCase):
    """B1b drift guard: SKILL.md router ↔ references/phases/ files stay in sync."""

    def setUp(self) -> None:
        self.assertTrue(SKILL.is_file(), "SKILL.md must exist")
        self.assertTrue(PHASES_DIR.is_dir(), "references/phases/ must exist after B1b")
        self.skill_text = SKILL.read_text(encoding="utf-8")
        # Match both full-path (`references/phases/phase-1.md`) and the bare
        # parenthetical shorthand (`phase-2b.md`) the router uses for secondary files.
        self.referenced = set(re.findall(r"(phase-[\w]+)\.md", self.skill_text))
        self.on_disk = {p.stem for p in PHASES_DIR.glob("phase-*.md")}

    def test_router_stays_thin(self) -> None:
        # The whole point of B1b: SKILL.md is a router, not the full spec.
        n = len(self.skill_text.splitlines())
        self.assertLess(n, 250, f"SKILL.md router should be thin (<250 lines), is {n}")

    def test_router_references_exist_on_disk(self) -> None:
        self.assertTrue(self.referenced, "router must reference phase files")
        missing = self.referenced - self.on_disk
        self.assertFalse(missing, f"router references missing phase files: {sorted(missing)}")

    def test_no_orphan_phase_files(self) -> None:
        orphans = self.on_disk - self.referenced
        self.assertFalse(orphans, f"phase files not referenced by the router: {sorted(orphans)}")


if __name__ == "__main__":
    unittest.main()
