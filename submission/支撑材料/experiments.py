

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.planner import Planner


def run_case(
    seed,
    problem,
    strategy,
    scenario="random",
    error_mode="smooth",
    probe_scale=0.22,
    spacing=990.0,
    loss_recovery=True,
    anchor_policy=None,
    ring_radius=None,
    probe_policy="fixed",
    coverage_policy=None,
    optical_policy="rectangle",
    dispatch_policy=None,
    scan_policy=None,
):
    env = LocalSimulator(seed, problem, error_mode, scenario)
    planner = Planner(
        env,
        problem,
        strategy,
        spacing=spacing,
        probe_scale=probe_scale,
        loss_recovery=loss_recovery,
        anchor_policy=anchor_policy,
        ring_radius=ring_radius,
        probe_policy=probe_policy,
        coverage_policy=coverage_policy,
        optical_policy=optical_policy,
        dispatch_policy=dispatch_policy,
        scan_policy=scan_policy,
    )
    p = planner.run()
    assert p["certificate_complete"] is True
    s = env.summary()
    
    position, radio, total = (0.0, 0.0), 1, 0.0
    successes = set()
    for event in env.log:
        request, response = event["request"], event["response"]
        if not response["accepted"]:
            continue
        path = request["path"]
        if path in ("/measure", "/clear"):
            q = (request["position"]["x"], request["position"]["y"])
            total += round(math.dist(position, q) / 5, 6)
            position = q
            if path == "/measure":
                total += 5 + int(radio != request["channel"])
                radio = request["channel"]
            else:
                success = response["clear_result"] == "success"
                total += 5 if success else 3
                if success:
                    assert request["channel"] not in successes
                    successes.add(request["channel"])
        assert abs(total - response["virtual_time_s"]) < 2e-6
    assert len(successes) == s["n_cleared"] == p["n_cleared"]
    assert s["n_sources"] == s["n_cleared"], (seed, problem, scenario, error_mode, s)
    return {
        **s,
        "strategy": strategy,
        "visited_anchors": p["visited_anchors"],
        "optical_fallbacks": p["optical_fallbacks"],
        "probe_scale": p["probe_scale"],
        "loss_recovery_requested": loss_recovery,
        "loss_recovery": p["loss_recovery"],
        "anchor_policy": p["anchor_policy"],
        "ring_radius_m": p["ring_radius_m"],
        "spacing_m": spacing,
        "certificate_complete": p["certificate_complete"],
        "timing_independently_verified": True,
        "coverage_policy": p["coverage_policy"],
        "optical_policy": p["optical_policy"],
        "dispatch_policy": p["dispatch_policy"],
        "scan_policy": p["scan_policy"],
    }


def aggregate(rows):
    values = sorted(row["average_time_s"] for row in rows)
    return {
        "cases": len(rows),
        "all_cleared_cases": sum(r["fraction_cleared"] == 1 for r in rows),
        "mean_average_time_s": statistics.mean(values),
        "median_average_time_s": statistics.median(values),
        "p90_average_time_s": values[math.ceil(0.9 * len(values)) - 1],
        "worst_average_time_s": values[-1],
        "mean_total_time_s": statistics.mean(r["virtual_time_s"] for r in rows),
        "mean_distance_m": statistics.mean(r["distance_m"] for r in rows),
        "mean_measures": statistics.mean(r["measures"] for r in rows),
        "mean_failed_clears": statistics.mean(r["failed_clears"] for r in rows),
        "max_real_duration_s": max(r["real_duration_s"] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("results/experiments.json"))
    args = parser.parse_args()
    if args.cases < 2:
        parser.error("At least two paired cases required")
    rows, grouped, paired, stress, sensitivity = [], {}, {}, {}, {}
    for problem in (3, 4):
        strategy_rows = {}
        for strategy in ("baseline", "batched", "integrated"):
            current = [
                run_case(600000 + k, problem, strategy) for k in range(args.cases)
            ]
            rows.extend(current)
            strategy_rows[strategy] = current
            grouped[f"Q{problem}_{strategy}"] = aggregate(current)
        differences = [
            a["average_time_s"] - b["average_time_s"]
            for a, b in zip(strategy_rows["baseline"], strategy_rows["integrated"])
        ]
        delta = statistics.mean(differences)
        standard_error = statistics.stdev(differences) / math.sqrt(len(differences))
        paired[f"Q{problem}"] = {
            "mean_saved_s_per_source": delta,
            "approx_95pct_ci_s": [
                delta - 1.96 * standard_error,
                delta + 1.96 * standard_error,
            ],
            "mean_time_reduction_pct": 100
            * delta
            / grouped[f"Q{problem}_baseline"]["mean_average_time_s"],
            "faster_cases": sum(d > 0 for d in differences),
            "paired_cases": len(differences),
        }
        share_differences = [
            a["average_time_s"] - b["average_time_s"]
            for a, b in zip(strategy_rows["batched"], strategy_rows["integrated"])
        ]
        paired[f"Q{problem}_sharing_ablation"] = {
            "mean_saved_s_per_source": statistics.mean(share_differences),
            "faster_cases": sum(d > 0 for d in share_differences),
            "paired_cases": len(share_differences),
        }
        for scenario in ("minimum_radius", "outward_boundary", "clustered"):
            for mode in ("smooth", "extreme", "iid_location"):
                current = [
                    run_case(700000 + k, problem, "integrated", scenario, mode)
                    for k in range(20)
                ]
                rows.extend(current)
                stress[f"Q{problem}_{scenario}_{mode}"] = aggregate(current)
        
        for scale in (0.12, 0.22, 0.40):
            current = [
                run_case(800000 + k, problem, "integrated", probe_scale=scale)
                for k in range(30)
            ]
            rows.extend(current)
            sensitivity[f"Q{problem}_probe_{scale}"] = aggregate(current)
    for spacing in (900.0, 950.0, 990.0):
        current = [
            run_case(900000 + k, 4, "integrated", spacing=spacing) for k in range(30)
        ]
        rows.extend(current)
        sensitivity[f"Q4_spacing_{spacing}"] = aggregate(current)
    recovery_ablation = {}
    for scenario in ("random", "minimum_radius", "outward_boundary", "clustered"):
        for enabled in (False, True):
            current = [
                run_case(610000 + k, 4, "integrated", scenario, loss_recovery=enabled)
                for k in range(100)
            ]
            rows.extend(current)
            recovery_ablation[f"{scenario}_recovery_{enabled}"] = aggregate(current)
    result = {
        "evidence": "local_synthetic_not_official",
        "assumptions": "See environment.py module docstring",
        "paired_random_cases_per_problem": args.cases,
        "total_runs": len(rows),
        "summary": grouped,
        "paired_comparison": paired,
        "stress": stress,
        "sensitivity": sensitivity,
        "recovery_ablation": recovery_ablation,
        "runs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "runs"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
