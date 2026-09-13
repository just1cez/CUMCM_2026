"""Paired comparison for the interval-scored adaptive probe candidate."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.planner import Planner


def run(seed, problem, probe_policy):
    env = LocalSimulator(seed, problem=problem, scenario="random", error_mode="smooth")
    planner = Planner(env, problem=problem, strategy="integrated", probe_policy=probe_policy)
    planner.run()
    summary = env.summary()
    assert summary["fraction_cleared"] == 1
    return {**summary, "adaptive_probes": planner.adaptive_probes}


def aggregate(rows):
    delta = [a["average_time_s"] - b["average_time_s"] for a, b in rows]
    return {
        "cases": len(rows),
        "fixed_all_cleared": sum(a["fraction_cleared"] == 1 for a, _ in rows),
        "adaptive_all_cleared": sum(b["fraction_cleared"] == 1 for _, b in rows),
        "fixed_mean_s_per_source": statistics.mean(a["average_time_s"] for a, _ in rows),
        "adaptive_mean_s_per_source": statistics.mean(b["average_time_s"] for _, b in rows),
        "mean_saved_s_per_source": statistics.mean(delta),
        "median_saved_s_per_source": statistics.median(delta),
        "faster_cases": sum(d > 0 for d in delta),
        "fixed_mean_failed_clears": statistics.mean(a["failed_clears"] for a, _ in rows),
        "adaptive_mean_failed_clears": statistics.mean(b["failed_clears"] for _, b in rows),
        "mean_adaptive_probes": statistics.mean(b["adaptive_probes"] for _, b in rows),
    }


def main():
    summary = {}
    records = []
    for problem in (3, 4):
        pairs = [(run(960000 + k, problem, "fixed"), run(960000 + k, problem, "adaptive")) for k in range(200)]
        summary[f"Q{problem}"] = aggregate(pairs)
        records.extend({"problem": problem, "seed": 960000 + k, "fixed": fixed, "adaptive": adaptive}
                       for k, (fixed, adaptive) in enumerate(pairs))
    result = {"evidence": "local_synthetic_adaptive_candidate_not_official", "seed_range": [960000, 960199], "summary": summary, "runs": records}
    Path("results/adaptive_candidate_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"evidence": result["evidence"], "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
