from __future__ import annotations

"""Targeted, synthetic-only correctness audit for field extensions.

This script intentionally does not contact the official service or invoke the
official simulator.  Evidence is limited to deterministic pure geometry and a
small recording environment implementing the public LocalSimulator protocol.
"""
import json
from math import dist, isfinite
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from field_policy import FieldPlanner
from negative_geometry import exclude_omni_disk
from route_portfolio import choose_portfolio_task
from geometry import initial_polygon

OUT = ROOT / "results" / "audit_correctness.json"
def rec(name, evidence, cases, failures, **extra):
    return {"name": name, "evidence_type": evidence, "cases": cases,
            "failures": failures, "hard_gate": not failures,
            "command": "conda run -n py314 python b_solution/audit/correctness_audit.py",
            "seed_range": extra.pop("seed_range", "deterministic pure cases; no RNG"), **extra}


def negative_audit():
    failures = []
    # Exact feasible witness model: all witnesses outside the open disk must
    # remain in the returned convex outer approximation.
    polys = [[(-1800., -1800.), (1800., -1800.), (1800., 1800.), (-1800., 1800.)],
             [(-100., -100.), (100., -100.), (100., 100.), (-100., 100.)],
             [(0., 0.), (100., 0.), (0., 100.)]]
    witnesses = [(1400., 0.), (-1400., 0.), (0., 1400.), (0., -1400.),
                 (1000.0001, 0.), (0., 0.)]
    # point-in-convex-polygon with boundary tolerance, independent from module
    def inside(poly, p):
        signs = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            c = (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
            signs.append(c)
        return all(c >= -1e-7 for c in signs) or all(c <= 1e-7 for c in signs)
    count = 0
    for poly in polys:
        out = exclude_omni_disk(poly, (0., 0.), sides=16)
        for p in witnesses:
            if dist(p, (0., 0.)) > 1000.0 and inside(poly, p):
                count += 1
                if not inside(out, p): failures.append({"poly": poly, "witness": p})
    return rec("q3_negative_source_retention", "synthetic_exact_feasible_geometry", count, failures,
                model="source feasible iff distance(station)>1000; convex outer approximation")


def portfolio_audit():
    anchors = {2: (0., 0.), 7: (100., 0.), 9: (0., 0.)}
    targets = {3: ((100., 0.), 10.), 8: ((0., 0.), 0.)}
    task = choose_portfolio_task((0., 0.), anchors, targets, risk_weight=2.)
    expected = {("anchor", 2), ("anchor", 7), ("anchor", 9), ("target", 3), ("target", 8)}
    # Exercise dictionary order permutations and ties.
    failures = []
    for reverse in (False, True):
        a = dict(reversed(list(anchors.items()))) if reverse else dict(anchors)
        t = dict(reversed(list(targets.items()))) if reverse else dict(targets)
        got = choose_portfolio_task((0., 0.), a, t, risk_weight=2.)
        if got != task: failures.append({"reverse": reverse, "got": got, "expected": task})
    if task not in expected: failures.append({"selected": task, "tasks": sorted(expected)})
    return rec("portfolio_obligation_and_ties", "synthetic_pure_route_proxy", 3, failures,
                selected=task, complete_task_count=len(expected), duplicate_coordinate_keys=True)


def q4_negative_audit():
    # All current field paths disable negative updates for Q4 by construction.
    failures = []
    class E:
        def act(self, path, position=None, channel=None):
            return {"accepted": True, "virtual_time_s": 0., "measure_result": "no_signal"}
    for options in ({}, {"premeasure": False}, {"portfolio": False}, {"negative_updates": True},
                    {"premeasure": True, "portfolio": True, "approach_clear": True}):
        p = FieldPlanner(E(), problem=4, **options)
        if p.negative_updates or p.negative_cuts != 0:
            failures.append(options)
    return rec("q4_negative_cuts", "synthetic_constructor_and_state", 5, failures,
                claim_scope="current FieldPlanner paths only; not official behavior")


def timing_and_state_audit():
    # Public action accounting fixture: rejected action must not mutate planner;
    # accepted actions expose exact increments and one premeasure per localize.
    failures = []
    class E:
        def __init__(self): self.calls = []
        def act(self, path, position=None, channel=None):
            self.calls.append((path, position, channel))
            if path == "/enter": return {"accepted": True, "virtual_time_s": 0., "remaining_real_duration_s": 100., "max_virtual_duration_s": 100.}
            return {"accepted": True, "virtual_time_s": 5., "measure_result": "no_signal", "action_virtual_time_s": 5.}
    e = E(); p = FieldPlanner(e, problem=3, premeasure=False, negative_updates=False, portfolio=False)
    before = (p.position, p.virtual_time, list(p.visited), set(p.pending))
    class Reject(E):
        def act(self, path, position=None, channel=None):
            if path == "/measure": return {"accepted": False, "virtual_time_s": 999.}
            return super().act(path, position, channel)
    r = FieldPlanner(Reject(), problem=3, premeasure=False)
    try: r.action("/measure", (1., 2.), 1)
    except RuntimeError: pass
    if (r.position, r.virtual_time) != ((0., 0.), 0.): failures.append("rejected action advanced state")
    # Spy on the pre-localization hook: exactly one attempt, no hidden second call.
    from planner import Track
    spy = FieldPlanner(E(), problem=3, premeasure=True)
    spy.tracks[1] = Track(polygon=[(-100., -100.), (100., -100.), (100., 100.), (-100., 100.)])
    attempts = []
    def one_measure(channel, point):
        attempts.append((channel, tuple(point))); spy.terminal_reason = "spy_stop"; return "no_signal"
    spy.measure = one_measure
    spy.localize(1)
    if len(attempts) != 1: failures.append({"premeasure_attempts": len(attempts)})
    # Independent virtual-time recomputation from observable LocalSimulator log.
    from environment import LocalSimulator
    env = LocalSimulator(500000, problem=3, scenario="minimum_radius")
    env.act("/enter"); env.act("/measure", (300., 400.), 1); env.act("/measure", (300., 400.), 2); env.act("/exit")
    recomputed = sum(row["action_virtual_time_s"] for row in env.log)
    observed = env.log[-1]["response"]["virtual_time_s"]
    if abs(recomputed - observed) > 2e-6: failures.append({"recomputed": recomputed, "observed": observed})
    return rec("state_rejection_virtual_time_premeasure", "synthetic_public_action_fixture", 5, failures,
                premeasure_calls=len(attempts), independent_virtual_time=True,
                seed_range="500000 (single synthetic LocalSimulator fixture; permitted historical family)",
                initial_state={"position": list(before[0]), "virtual_time": before[1],
                               "visited": list(before[2]), "pending_count": len(before[3])})


def main():
    rows = [negative_audit(), q4_negative_audit(), portfolio_audit(), timing_and_state_audit()]
    payload = {"evidence": "synthetic_targeted_audit_only", "official_behavior_claimed": False,
               "command": "conda run -n py314 python b_solution/audit/correctness_audit.py", "seed_range": None,
               "configuration": {"official_simulator": False, "synthetic_model": "pure geometry + public action fixture"},
               "hard_gate": all(r["hard_gate"] for r in rows), "cases": rows,
               "failing_case_count": sum(len(r["failures"]) for r in rows)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))

if __name__ == "__main__": main()
