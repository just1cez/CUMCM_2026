
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from submission.支撑材料.experiments import aggregate, run_case



CONFIGS = {
    "control": {},
    "optical": {"optical_policy": "slabs"},
    "joint_center": {"dispatch_policy": "center"},
    "joint_guarded": {"dispatch_policy": "guarded"},
    "polar_seed": {"coverage_policy": "seed25"},
    "polar_compact": {"coverage_policy": "compact25"},
    "polar_joint": {"coverage_policy": "compact25", "dispatch_policy": "center"},
    "polar_guarded": {"coverage_policy": "compact25", "dispatch_policy": "guarded"},
    "combined": {"coverage_policy": "compact25", "optical_policy": "slabs", "dispatch_policy": "center"},
    "joint_unknown": {"dispatch_policy": "center", "scan_policy": "unknown"},
    "joint_useful": {"dispatch_policy": "center", "scan_policy": "useful"},
    "polar_unknown": {"coverage_policy": "compact25", "dispatch_policy": "guarded", "scan_policy": "unknown"},
    "polar_useful": {"coverage_policy": "compact25", "dispatch_policy": "guarded", "scan_policy": "useful"},
}


def paired(control, candidate):
    assert [r["seed"] for r in control] == [r["seed"] for r in candidate]
    values = [a["average_time_s"] - b["average_time_s"] for a, b in zip(control, candidate, strict=True)]
    mean = statistics.mean(values)
    sem = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"mean_saved_s_per_source": mean,
            "reduction_pct": 100 * mean / statistics.mean(r["average_time_s"] for r in control),
            "approx_95pct_ci_s": [mean - 1.96 * sem, mean + 1.96 * sem],
            "faster_cases": sum(value > 0 for value in values), "cases": len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=150)
    parser.add_argument("--seed", type=int, default=3100000)
    parser.add_argument("--output", type=Path, default=Path("results/refinement_development.json"))
    args = parser.parse_args()
    if args.cases < 2:
        parser.error("At least two cases are required")
    rows, summary = [], {}
    for problem in (3, 4):
        names = ("control", "optical", "joint_center", "joint_guarded", "joint_unknown", "joint_useful") if problem == 3 else tuple(name for name in CONFIGS if name not in ("joint_unknown", "joint_useful"))
        control = None
        for name in names:
            group = []
            for seed in range(args.seed, args.seed + args.cases):
                row = run_case(seed, problem, "enhanced", **CONFIGS[name])
                row["configuration"] = name
                group.append(row)
            rows.extend(group)
            if name == "control":
                control = group
            key = f"Q{problem}_{name}"
            summary[key] = {**aggregate(group), **paired(control, group)}
            print(key, json.dumps(summary[key], ensure_ascii=False), flush=True)
    result = {"evidence": "development_only_local_synthetic_not_official",
              "seed_range": [args.seed, args.seed + args.cases - 1],
              "configs": CONFIGS, "total_runs": len(rows), "summary": summary, "runs": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
