"""Finite field-informed development screen; no official counterfactual claims."""

from __future__ import annotations
import argparse
import json
import math
import statistics
from pathlib import Path
from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.field_policy import FieldPlanner
from submission.支撑材料.planner import Planner

CONFIGS = {
    "control": None,
    "premeasure": {"premeasure": True},
    "negative": {"premeasure": False, "negative_updates": True},
    "pre_negative": {"premeasure": True, "negative_updates": True},
    "risk2": {"premeasure": True, "risk_weight": 2.0},
    "risk4": {"premeasure": True, "risk_weight": 4.0},
    "risk8": {"premeasure": True, "risk_weight": 8.0},
    "portfolio": {"premeasure": True, "portfolio": True},
    "portfolio_negative": {
        "premeasure": True,
        "portfolio": True,
        "negative_updates": True,
    },
    "portfolio_risk2": {"premeasure": True, "portfolio": True, "risk_weight": 2.0},
    "portfolio_clear": {"premeasure": True, "portfolio": True, "approach_clear": True},
    "all": {
        "premeasure": True,
        "portfolio": True,
        "negative_updates": True,
        "approach_clear": True,
    },
}


def run_field(seed, problem, config, scenario="random", mode="smooth"):
    env = LocalSimulator(seed, problem, mode, scenario)
    settings = {
        "premeasure": False,
        "negative_updates": False,
        "portfolio": False,
        "approach_clear": False,
    }
    planner = (
        Planner(env, problem, probe_scale=0.22)
        if config is None
        else FieldPlanner(env, problem, **(settings | config))
    )
    result = planner.run()
    actual = env.summary()
    assert (
        result["certificate_complete"] and actual["n_cleared"] == actual["n_sources"]
    ), (seed, problem, result, actual)
    pos = (0.0, 0.0)
    radio = 1
    us = 0
    successes = set()
    for event in env.log:
        request, response = event["request"], event["response"]
        assert response["accepted"]
        if request["path"] in ("/measure", "/clear"):
            p = request["position"]["x"], request["position"]["y"]
            us += round(math.dist(pos, p) / 5 * 1000000)
            pos = p
            if request["path"] == "/measure":
                us += (5 + int(radio != request["channel"])) * 1000000
                radio = request["channel"]
            else:
                success = response["clear_result"] == "success"
                us += (5 if success else 3) * 1000000
                if success:
                    assert request["channel"] not in successes
                    successes.add(request["channel"])
        assert abs(us / 1000000 - response["virtual_time_s"]) < 2e-6
    assert len(successes) == actual["n_sources"]
    return {
        **actual,
        "certificate_complete": True,
        "timing_independently_verified": True,
        "zero_travel_probes": result.get("zero_travel_probes", 0),
        "negative_cuts": result.get("negative_cuts", 0),
    }


def pair_stats(control, candidate):
    assert [r["seed"] for r in control] == [r["seed"] for r in candidate]
    diffs = [
        a["average_time_s"] - b["average_time_s"]
        for a, b in zip(control, candidate, strict=True)
    ]
    mean = statistics.mean(diffs)
    se = statistics.stdev(diffs) / math.sqrt(len(diffs))
    return {
        "mean_saved_s": mean,
        "saving_pct": 100
        * mean
        / statistics.mean(r["average_time_s"] for r in control),
        "approx_95pct_ci": [mean - 1.96 * se, mean + 1.96 * se],
        "faster_cases": sum(d > 0 for d in diffs),
    }


def summarize(group):
    values = sorted(r["average_time_s"] for r in group)
    return {
        "cases": len(group),
        "all_clear": sum(r["fraction_cleared"] == 1 for r in group),
        "mean": statistics.mean(values),
        "p90": values[math.ceil(0.9 * len(values)) - 1],
        "worst": max(values),
        "distance": statistics.mean(r["distance_m"] for r in group),
        "measures": statistics.mean(r["measures"] for r in group),
        "mean_failed_clear_attempts_per_case": statistics.mean(
            r["failed_clears"] for r in group
        ),
        "max_real_s": max(r["real_duration_s"] for r in group),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=150)
    parser.add_argument("--seed", type=int, default=6100000)
    parser.add_argument(
        "--output", type=Path, default=Path("results/field_development.json")
    )
    args = parser.parse_args()
    summaries = {}
    rows = []
    for p in (3, 4):
        names = (
            (
                "control",
                "premeasure",
                "negative",
                "pre_negative",
                "portfolio",
                "portfolio_negative",
                "all",
            )
            if p == 3
            else (
                "control",
                "premeasure",
                "risk2",
                "risk4",
                "risk8",
                "portfolio",
                "portfolio_risk2",
                "portfolio_clear",
            )
        )
        control = None
        for name in names:
            group = [
                run_field(seed, p, CONFIGS[name])
                for seed in range(args.seed, args.seed + args.cases)
            ]
            for row in group:
                row["configuration"] = name
            rows.extend(group)
            if control is None:
                control = group
            summaries[f"Q{p}_{name}"] = {
                **summarize(group),
                **pair_stats(control, group),
            }
            print(f"Q{p}_{name}", json.dumps(summaries[f"Q{p}_{name}"]), flush=True)
    args.output.write_text(
        json.dumps(
            {
                "evidence": "field_informed_local_development_not_official",
                "seed_range": [args.seed, args.seed + args.cases - 1],
                "configs": CONFIGS,
                "summary": summaries,
                "total_runs": len(rows),
                "runs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
