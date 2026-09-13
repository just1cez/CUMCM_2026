
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "b_solution"))
from submission.支撑材料.environment import LocalSimulator  
from submission.支撑材料.planner import Planner  
from submission.支撑材料.geometry import enclosing_circle  
from submission.支撑材料.route_policy_candidate import optimize_waypoints  

SEEDS = range(8201000, 8201040)  


class BoundedOrderPlanner(Planner):
    
    def next_anchor(self):
        indices = sorted(self.pending)
        if len(indices) <= 6 and indices:
            order = optimize_waypoints([self.waypoints[i] for i in indices], self.position)
            return indices[order[0]]
        return super().next_anchor()

    def select_task(self):
        kind, index = super().select_task()
        return (kind, self.next_anchor()) if kind == "anchor" else (kind, index)


class RollingTwoPlanner(Planner):
    
    def next_anchor(self):
        indices = sorted(self.pending)
        if not indices:
            return super().next_anchor()
        
        nearest = sorted(indices, key=lambda i: (math.dist(self.position, self.waypoints[i]), i))[:2]
        order = optimize_waypoints([self.waypoints[i] for i in nearest], self.position)
        return nearest[order[0]]

    def select_task(self):
        kind, index = super().select_task()
        return (kind, self.next_anchor()) if kind == "anchor" else (kind, index)


class DualScorePlanner(Planner):
    
    uncertainty_weight = 0.25

    def select_task(self):
        anchors = {i: self.waypoints[i] for i in sorted(self.pending)}
        targets = {ch: enclosing_circle(track.polygon) for ch, track in self.tracks.items()}
        
        
        options = [(math.dist(self.position, p) + 120.0, "anchor", i)
                   for i, p in anchors.items()]
        options += [(math.dist(self.position, c) + self.uncertainty_weight * r,
                     "target", ch) for ch, (c, r) in targets.items()]
        if not options:
            return "anchor", self.next_anchor()
        _, kind, ident = min(options, key=lambda x: (x[0], x[1], x[2]))
        return kind, ident

CANDIDATES = {
    "control_refined": lambda env, p: Planner(env, problem=p, strategy="refined"),
    "A_bounded_order": lambda env, p: BoundedOrderPlanner(env, problem=p, strategy="refined"),
    "B_rolling_two": lambda env, p: RollingTwoPlanner(env, problem=p, strategy="refined"),
    "C_dual_score": lambda env, p: DualScorePlanner(env, problem=p, strategy="refined"),
}


def run_one(seed, problem, name):
    env = LocalSimulator(seed, problem=problem, scenario="random", error_mode="smooth")
    planner = CANDIDATES[name](env, problem)
    result = planner.run()
    actual = env.summary()
    row = {"seed": seed, "problem": problem, "candidate": name,
           "evidence": "local_synthetic_not_official", "scenario": "random",
           "error_mode": "smooth", "result": result, "summary": actual}
    row["decomposition"] = {k: actual.get(k) for k in (
        "virtual_time_s", "average_time_s", "distance_m", "measures", "switches",
        "clear_attempts", "failed_clears", "n_sources", "n_cleared", "fraction_cleared",
        "real_duration_s")}
    row["certificate"] = {"certificate_complete": result.get("certificate_complete"),
                          "termination": result.get("termination"),
                          "terminal_reason": result.get("terminal_reason")}
    return row


def pct(values, q):
    vals = sorted(values)
    return vals[min(len(vals) - 1, max(0, math.ceil(q * len(vals)) - 1))]


def paired(control, candidate):
    deltas = [a["summary"]["average_time_s"] - b["summary"]["average_time_s"]
              for a, b in zip(control, candidate)]
    mean = statistics.mean(deltas)
    se = statistics.stdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1 else 0.0
    return {"paired_cases": len(deltas), "mean_saved_T_per_N_s": mean,
            "approx_95pct_ci_s": [mean - 1.96 * se, mean + 1.96 * se],
            "p90_saved_s": pct(deltas, .90), "worst_saved_s": min(deltas),
            "faster_cases": sum(d > 0 for d in deltas),
            "all_pairs_certificate_complete": all(
                a["result"]["certificate_complete"] and b["result"]["certificate_complete"]
                for a, b in zip(control, candidate)),
            "failure_counts": {"control": sum(not r["result"]["certificate_complete"] for r in control),
                               "candidate": sum(not r["result"]["certificate_complete"] for r in candidate)}}


def main():
    runs, summary = [], {}
    for problem in (3, 4):
        groups = {name: [run_one(seed, problem, name) for seed in SEEDS] for name in CANDIDATES}
        for rows in groups.values(): runs.extend(rows)
        summary[f"Q{problem}"] = {}
        for name, rows in groups.items():
            times = [r["summary"]["average_time_s"] for r in rows]
            summary[f"Q{problem}"][name] = {"cases": len(rows), "mean_T_per_N_s": statistics.mean(times),
                "p90_T_per_N_s": pct(times, .90), "worst_T_per_N_s": max(times),
                "all_cleared": sum(r["summary"]["fraction_cleared"] == 1 for r in rows),
                "certificate_failures": sum(not r["result"]["certificate_complete"] for r in rows),
                "failed_clear_attempts": sum(r["summary"]["failed_clears"] for r in rows)}
        summary[f"Q{problem}"]["paired_vs_control"] = {
            name: paired(groups["control_refined"], rows)
            for name, rows in groups.items() if name != "control_refined"}
    out = {"evidence": "local_synthetic_not_official", "diagnostic": True,
           "seed_range": [SEEDS.start, SEEDS.stop - 1], "seeds_per_problem": len(SEEDS),
           "configuration": {"error_mode": "smooth", "scenario": "random", "strategy": "refined",
             "A": "bounded reorder only when <=6 pending anchors",
             "B": "rolling optimize over nearest two pending anchors",
             "C": "travel + 0.25*enclosing-radius fixed dual score",
             "dependencies_excluded": ["route_portfolio", "negative_geometry", "premeasure"]},
           "hard_gate": {"status": "diagnostic_only", "verified": False,
             "rule": "No candidate is verified; paired CI/p90/worst and certificate gates are reported."},
           "summary": summary, "runs": runs}
    path = ROOT / "b_solution/results/audit_alternatives.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(path), "evidence": out["evidence"], "seed_range": out["seed_range"], "summary": summary}, ensure_ascii=False))

if __name__ == "__main__":
    main()
