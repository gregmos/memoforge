#!/usr/bin/env python3
"""Analyze a finished (or in-flight) memoforge task and report where wall-clock went.

Read-only forensics over a task's `events.jsonl` + `state.json` + output-file
mtimes. NOT wired into the pipeline — run it by hand after a task to turn
"не ясно как так" (1.5h vs 3h on the same prompt) into per-phase numbers.

WHY mtimes, not just events: on long runs the orchestrator stops emitting
`events.jsonl` mid-run (context summarization drops the logging instruction —
see CHANGELOG v1.0.0). The real 2026-05-28 run logged 31 events then went dark
~1h46m before finishing. So per-phase / per-agent timing is reconstructed
PRIMARILY from OS file mtimes (`drafts/`, `reviews/`, `research/`) +
`phase_transition` events + `state.json.iterations[]`; the per-agent
`agent_dispatched`/`agent_returned` events (Tier-1 per events-contract.md) are
used only opportunistically because real runs often omit them entirely.

Headline check — SERIAL reviewer rounds: the spec dispatches reviewers in ONE
message (parallel), but a context-degraded orchestrator dispatches them one at
a time. Serial rounds show reviewer JSONs completing one-after-another in
`reviewer_list` order over many minutes; parallel rounds cluster within one
slowest-reviewer. This tool flags it from the `reviews/v<N>-*.json` mtimes.

Usage:
    python3 scripts/analyze_run.py --workdir <task work_dir>
    python3 scripts/analyze_run.py --workdir <dir> --json
    python3 scripts/analyze_run.py --compare <slow_workdir> <fast_workdir>

Exit codes: 0 = analyzed; 2 = no readable events.jsonl AND no state.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Runtime phases in execution order. Mirrors scripts/validate_state.py
# PHASES_ORDERED (minus the legacy heartbeat_pending alias); kept local so the
# analyzer has no import-path dependency, matching how render_live_progress.py
# defines its own PHASES list.
PHASE_ORDER = [
    "intake_preliminary_research",
    "intake_questions_pending",
    "mode_pick_pending",
    "planning",
    "plan_approval_pending",
    "research",
    "research_sufficiency",
    "research_sufficiency_followup_pending",
    "currency_check",
    "source_pack",
    "source_review_pending",
    "drafting",
    "revision_loop",
    "client_readiness",
    "export",
    "done",
]
PHASE_RANK = {p: i for i, p in enumerate(PHASE_ORDER)}

REVIEWER_KINDS = ["logic", "clarity", "style", "citations", "counterarguments"]

# A reviewer round whose completions span more than this is treated as a
# likely-serial dispatch (parallel rounds cluster within one slowest reviewer).
SERIAL_SPAN_THRESHOLD_S = 360.0  # 6 minutes

# events.jsonl considered "truncated" if it goes silent this long before the
# last filesystem activity in the work dir.
EVENTS_DIED_GAP_S = 600.0  # 10 minutes

# Rework / variance-driver event names (counted for the report).
REWORK_EVENTS = [
    "research_followup_started",
    "research_followup_user_gate_started",
    "client_readiness_polish_started",
    "reviewer_json_retry_started",
    "mcp_ratelimit_fallback",
    "fallback_invoked",
    "visualize_call_failed",
]


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_ts(s: Any) -> Optional[dt.datetime]:
    """Parse an ISO-8601 event timestamp (with trailing Z) to aware UTC."""
    if not isinstance(s, str) or not s:
        return None
    try:
        out = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=dt.timezone.utc)
    return out.astimezone(dt.timezone.utc)


def mtime_utc(path: Path) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    except OSError:
        return None


def load_events(events_path: Path) -> tuple[list[dict], int]:
    """Return (events, malformed_line_count). Tolerates a partial/corrupt log."""
    events: list[dict] = []
    malformed = 0
    try:
        text = events_path.read_text(encoding="utf-8")
    except OSError:
        return events, malformed
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(obj, dict):
            events.append(obj)
        else:
            malformed += 1
    return events, malformed


def load_state(state_path: Path) -> Optional[dict]:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def fmt_dur(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_clock(d: Optional[dt.datetime]) -> str:
    return d.strftime("%H:%M:%SZ") if d else "—"


# --------------------------------------------------------------------------- #
# Core analysis
# --------------------------------------------------------------------------- #
def latest_fs_activity(workdir: Path) -> tuple[Optional[dt.datetime], str]:
    """Newest mtime across the artifacts a run produces. Used to bound the run
    end when events.jsonl died early."""
    best: Optional[dt.datetime] = None
    best_src = ""
    candidates: list[Path] = [
        workdir / "state.json",
    ]
    for sub in ("drafts", "reviews", "research"):
        d = workdir / sub
        if d.is_dir():
            candidates.extend(p for p in d.iterdir() if p.is_file())
    candidates.extend(workdir.glob("memo-*.docx"))
    candidates.extend(workdir.glob("memo-*.md"))
    for p in candidates:
        mt = mtime_utc(p)
        if mt and (best is None or mt > best):
            best, best_src = mt, p.name
    return best, best_src


def phase_timeline_from_events(events: list[dict]) -> list[dict]:
    """Build [{phase, enter_ts, exit_ts, reason_out}] from phase_transition rows.

    The first phase is anchored at task_created. Each transition's `to` becomes
    the active phase until the next transition (or run end)."""
    transitions = [e for e in events if e.get("event") == "phase_transition"]
    transitions.sort(key=lambda e: parse_ts(e.get("ts")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc))

    created = next((e for e in events if e.get("event") == "task_created"), None)
    start_ts = parse_ts(created.get("ts")) if created else (
        parse_ts(events[0].get("ts")) if events else None
    )

    segs: list[dict] = []
    # Seed phase = the `from` of the first transition (or its `to` if no from).
    if transitions:
        first = transitions[0]
        seed_phase = (first.get("data") or {}).get("from") or "intake_preliminary_research"
        segs.append({"phase": seed_phase, "enter_ts": start_ts, "exit_ts": None, "reason_out": None})
    for tr in transitions:
        data = tr.get("data") or {}
        ts = parse_ts(tr.get("ts"))
        to_phase = data.get("to")
        if segs:
            segs[-1]["exit_ts"] = ts
            segs[-1]["reason_out"] = data.get("reason")
        segs.append({"phase": to_phase, "enter_ts": ts, "exit_ts": None, "reason_out": None})
    return segs


def analyze_revision_rounds(workdir: Path, reviewer_list: list[str]) -> list[dict]:
    """Reconstruct each revision iteration from draft + review mtimes and flag
    serial reviewer rounds. Independent of events (which usually died by here)."""
    reviews = workdir / "reviews"
    drafts = workdir / "drafts"
    rounds: list[dict] = []
    if not reviews.is_dir():
        return rounds

    for n in range(1, 9):  # generous upper bound; stop when no artifacts found
        draft_mt = mtime_utc(drafts / f"v{n}.md")
        rev_files: list[tuple[str, dt.datetime]] = []
        for kind in (reviewer_list or REVIEWER_KINDS):
            mt = mtime_utc(reviews / f"v{n}-{kind}.json")
            if mt:
                rev_files.append((kind, mt))
        mediator_mt = mtime_utc(reviews / f"v{n}-mediator.md")
        if not rev_files and mediator_mt is None and draft_mt is None:
            break  # no iteration N — done
        if not rev_files:
            rounds.append({"iteration": n, "draft_done": draft_mt,
                           "reviewers": [], "mediator_done": mediator_mt,
                           "serial": None})
            continue

        rev_files.sort(key=lambda t: t[1])
        completions = [t[1] for t in rev_files]
        span = (completions[-1] - completions[0]).total_seconds()
        order = [t[0] for t in rev_files]
        list_order = [k for k in (reviewer_list or REVIEWER_KINDS) if k in order]
        monotonic_in_list_order = order == list_order

        # Under a serial back-to-back assumption anchored at the draft-done
        # time, estimate per-reviewer durations and the parallel wall-clock.
        anchor = draft_mt if draft_mt and draft_mt <= completions[0] else None
        per_reviewer: list[tuple[str, float]] = []
        prev = anchor
        for kind, mt in rev_files:
            if prev is not None:
                per_reviewer.append((kind, (mt - prev).total_seconds()))
            prev = mt
        serial_wall = (completions[-1] - anchor).total_seconds() if anchor else span
        parallel_est = max((d for _, d in per_reviewer), default=None) if per_reviewer else None

        likely_serial = (
            len(rev_files) >= 3
            and serial_wall > SERIAL_SPAN_THRESHOLD_S
            and monotonic_in_list_order
        )
        rounds.append({
            "iteration": n,
            "draft_done": draft_mt,
            "reviewers": rev_files,
            "order": order,
            "monotonic_in_list_order": monotonic_in_list_order,
            "span_s": span,
            "serial_wall_s": serial_wall,
            "parallel_est_s": parallel_est,
            "savings_est_s": (serial_wall - parallel_est) if parallel_est is not None else None,
            "mediator_done": mediator_mt,
            "serial": likely_serial,
        })
    return rounds


def analyze(workdir: Path) -> dict:
    events_path = workdir / "events.jsonl"
    events, malformed = load_events(events_path)
    state = load_state(workdir / "state.json")

    metrics: dict[str, Any] = {
        "workdir": str(workdir),
        "task_id": (state or {}).get("task_id"),
        "mode": (state or {}).get("mode"),
        "final_status": (state or {}).get("final_status"),
        "n_events": len(events),
        "malformed_event_lines": malformed,
        "warnings": [],
    }

    ev_ts = [parse_ts(e.get("ts")) for e in events]
    ev_ts = [t for t in ev_ts if t]
    first_ts = min(ev_ts) if ev_ts else None
    last_event_ts = max(ev_ts) if ev_ts else None
    fs_last, fs_src = latest_fs_activity(workdir)

    run_start = first_ts or parse_ts((state or {}).get("created_at"))
    run_end = max([t for t in (last_event_ts, fs_last) if t], default=None)
    metrics["run_start"] = run_start.isoformat() if run_start else None
    metrics["run_end"] = run_end.isoformat() if run_end else None
    metrics["run_end_source"] = fs_src if (fs_last and (not last_event_ts or fs_last > last_event_ts)) else "last_event"
    metrics["total_s"] = (run_end - run_start).total_seconds() if (run_start and run_end) else None

    # events-died detection
    metrics["last_event_ts"] = last_event_ts.isoformat() if last_event_ts else None
    if last_event_ts and fs_last and (fs_last - last_event_ts).total_seconds() > EVENTS_DIED_GAP_S:
        gap = (fs_last - last_event_ts).total_seconds()
        metrics["events_truncated"] = True
        metrics["events_dark_s"] = gap
        last_phase = None
        for e in reversed(events):
            if e.get("event") == "phase_transition":
                last_phase = (e.get("data") or {}).get("to")
                break
        metrics["events_died_at_phase"] = last_phase
        metrics["warnings"].append(
            f"events.jsonl went dark at {fmt_clock(last_event_ts)} "
            f"(phase '{last_phase}') — run continued {fmt_dur(gap)} more; "
            f"second half reconstructed from file mtimes."
        )
    else:
        metrics["events_truncated"] = False

    # per-phase durations from events
    segs = phase_timeline_from_events(events)
    phase_durs: list[dict] = []
    for s in segs:
        end = s["exit_ts"]
        dur = (end - s["enter_ts"]).total_seconds() if (end and s["enter_ts"]) else None
        phase_durs.append({
            "phase": s["phase"],
            "enter": s["enter_ts"].isoformat() if s["enter_ts"] else None,
            "dur_s": dur,
            "reason_out": s["reason_out"],
        })
    metrics["phase_durations_event_derived"] = phase_durs

    # revision-loop reconstruction (mtime-based; survives dead events)
    reviewer_list = ((state or {}).get("config") or {}).get("reviewer_list") or REVIEWER_KINDS
    metrics["reviewer_list"] = reviewer_list
    metrics["revision_rounds"] = analyze_revision_rounds(workdir, reviewer_list)
    metrics["serial_round_count"] = sum(1 for r in metrics["revision_rounds"] if r.get("serial"))

    # iteration score trend (from state) — flag regressions
    iters = (state or {}).get("iterations") or []
    trend = [{"iteration": it.get("iteration"), "aggregate_score": it.get("aggregate_score"),
              "verdict": it.get("verdict"), "blocking_count": it.get("blocking_count")}
             for it in iters]
    metrics["score_trend"] = trend
    regressions = [
        trend[i]["iteration"]
        for i in range(1, len(trend))
        if isinstance(trend[i]["aggregate_score"], (int, float))
        and isinstance(trend[i - 1]["aggregate_score"], (int, float))
        and trend[i]["aggregate_score"] <= trend[i - 1]["aggregate_score"]
    ]
    metrics["score_regressions_at_iter"] = regressions
    if regressions:
        metrics["warnings"].append(
            f"revision score did not improve at iteration(s) {regressions} "
            f"— candidate for convergence-based early exit (plan C1)."
        )

    # rework / gate counters
    counts: dict[str, int] = {}
    for e in events:
        name = e.get("event")
        if name in REWORK_EVENTS:
            counts[name] = counts.get(name, 0) + 1
    metrics["rework_events"] = counts

    # duplicate gate detection
    gate_announced: dict[str, int] = {}
    for e in events:
        if e.get("event") == "gate_announced":
            g = (e.get("data") or {}).get("gate_name", "?")
            gate_announced[g] = gate_announced.get(g, 0) + 1
    dupes = {g: c for g, c in gate_announced.items() if c > 1}
    metrics["duplicate_gates"] = dupes
    if dupes:
        metrics["warnings"].append(f"duplicate gate_announced: {dupes} (orchestrator re-fired a transition).")

    # user-gate wait (gate_announced/…_gate_started → gate_answered, by gate_name)
    gate_wait_s = 0.0
    pending: dict[str, dt.datetime] = {}
    for e in sorted(events, key=lambda x: parse_ts(x.get("ts")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)):
        name = e.get("event")
        ts = parse_ts(e.get("ts"))
        g = (e.get("data") or {}).get("gate_name")
        if not ts:
            continue
        if name in ("gate_announced", "research_followup_user_gate_started") and g:
            pending[g] = ts
        elif name == "gate_answered" and g and g in pending:
            gate_wait_s += (ts - pending.pop(g)).total_seconds()
    metrics["user_gate_wait_s"] = gate_wait_s if gate_wait_s else None

    if not events and state is None:
        metrics["warnings"].append("no readable events.jsonl and no state.json — nothing to analyze.")
    return metrics


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def build_report(m: dict) -> str:
    L: list[str] = []
    L.append(f"=== memoforge run analysis: {m.get('task_id') or m['workdir']} ===")
    L.append(f"mode={m.get('mode')}  final_status={m.get('final_status')}  "
             f"events={m['n_events']}"
             + (f" (+{m['malformed_event_lines']} malformed)" if m['malformed_event_lines'] else ""))
    L.append(f"TOTAL wall-clock: {fmt_dur(m.get('total_s'))}   "
             f"({fmt_clock(parse_ts(m.get('run_start')))} → {fmt_clock(parse_ts(m.get('run_end')))}, "
             f"end via {m.get('run_end_source')})")

    if m.get("events_truncated"):
        L.append("")
        L.append(f"⚠ EVENTS TRUNCATED: log went dark at {fmt_clock(parse_ts(m.get('last_event_ts')))} "
                 f"(phase '{m.get('events_died_at_phase')}'); +{fmt_dur(m.get('events_dark_s'))} reconstructed from mtimes.")

    # phase durations
    L.append("")
    L.append("-- phase durations (event-derived) --")
    for p in m.get("phase_durations_event_derived", []):
        reason = f"  →{p['reason_out']}" if p.get("reason_out") else ""
        L.append(f"  {p['phase']:<38} {fmt_dur(p.get('dur_s')):>8}{reason}")

    # revision rounds + serial flag
    rounds = m.get("revision_rounds", [])
    if rounds:
        L.append("")
        L.append("-- revision loop (mtime-reconstructed) --")
        for r in rounds:
            if not r.get("reviewers"):
                L.append(f"  iter {r['iteration']}: (no reviewer JSONs found)")
                continue
            tag = "SERIAL" if r.get("serial") else "ok"
            line = (f"  iter {r['iteration']}: {len(r['reviewers'])} reviewers, "
                    f"span {fmt_dur(r.get('span_s'))} [{tag}]")
            L.append(line)
            L.append(f"      order: {' → '.join(r.get('order', []))}"
                     f"{'  (matches reviewer_list order)' if r.get('monotonic_in_list_order') else ''}")
            if r.get("serial"):
                L.append(f"      serial wall ≈ {fmt_dur(r.get('serial_wall_s'))}; "
                         f"if parallel ≈ {fmt_dur(r.get('parallel_est_s'))} "
                         f"→ ~{fmt_dur(r.get('savings_est_s'))} recoverable")
        if m.get("serial_round_count"):
            L.append(f"  ** {m['serial_round_count']} serial round(s) detected — "
                     f"reviewers did NOT run in parallel (plan B1 target). **")

    # score trend
    trend = m.get("score_trend", [])
    if trend:
        L.append("")
        L.append("-- revision score trend --")
        cells = [f"v{t['iteration']}={t['aggregate_score']}({t['verdict']},{t['blocking_count']}blk)"
                 for t in trend]
        L.append("  " + "  ".join(cells))
        if m.get("score_regressions_at_iter"):
            L.append(f"  ⚠ no improvement at iter {m['score_regressions_at_iter']} — wasted iteration(s).")

    # rework + gates + user wait
    if m.get("rework_events"):
        L.append("")
        L.append("-- rework / variance drivers --")
        for k, v in m["rework_events"].items():
            L.append(f"  {k}: {v}")
    if m.get("duplicate_gates"):
        L.append(f"  ⚠ duplicate gates: {m['duplicate_gates']}")
    if m.get("user_gate_wait_s"):
        L.append(f"  user-gate wait (human, not compute): {fmt_dur(m['user_gate_wait_s'])}")

    if m.get("warnings"):
        L.append("")
        L.append("-- notes --")
        for w in m["warnings"]:
            L.append(f"  • {w}")
    return "\n".join(L)


def build_compare(a: dict, b: dict) -> str:
    L: list[str] = []
    L.append("=== compare ===")
    def row(label: str, va: Any, vb: Any) -> str:
        return f"  {label:<26} {str(va):<22} {str(vb)}"
    L.append(row("", a.get("task_id") or "A", b.get("task_id") or "B"))
    L.append(row("total wall-clock", fmt_dur(a.get("total_s")), fmt_dur(b.get("total_s"))))
    L.append(row("mode", a.get("mode"), b.get("mode")))
    L.append(row("final_status", a.get("final_status"), b.get("final_status")))
    L.append(row("revision iterations", len(a.get("score_trend", [])), len(b.get("score_trend", []))))
    L.append(row("serial reviewer rounds", a.get("serial_round_count"), b.get("serial_round_count")))
    L.append(row("events truncated", a.get("events_truncated"), b.get("events_truncated")))
    L.append(row("score regressions", a.get("score_regressions_at_iter"), b.get("score_regressions_at_iter")))
    L.append(row("user-gate wait", fmt_dur(a.get("user_gate_wait_s")), fmt_dur(b.get("user_gate_wait_s"))))
    return "\n".join(L)


def main() -> int:
    # The report uses Unicode (→ ⚠ ≈ •); Windows consoles default to cp1252
    # and would crash on write. Force UTF-8 where the runtime allows it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Analyze a memoforge task run (read-only).")
    ap.add_argument("--workdir", help="Task working directory (contains events.jsonl + state.json)")
    ap.add_argument("--events", help="Path to an events.jsonl directly (uses its parent as workdir)")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"),
                    help="Two work dirs to compare side-by-side (e.g. slow vs fast)")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = ap.parse_args()

    if args.compare:
        a = analyze(Path(args.compare[0]))
        b = analyze(Path(args.compare[1]))
        if args.json:
            sys.stdout.write(json.dumps({"a": a, "b": b}, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(build_compare(a, b) + "\n")
        return 0

    if args.events:
        workdir = Path(args.events).resolve().parent
    elif args.workdir:
        workdir = Path(args.workdir)
    else:
        ap.error("provide --workdir, --events, or --compare")
        return 2

    if not (workdir / "events.jsonl").exists() and not (workdir / "state.json").exists():
        sys.stderr.write(f"analyze_run: no events.jsonl or state.json under {workdir}\n")
        return 2

    m = analyze(workdir)
    if args.json:
        sys.stdout.write(json.dumps(m, indent=2, default=str) + "\n")
    else:
        sys.stdout.write(build_report(m) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
