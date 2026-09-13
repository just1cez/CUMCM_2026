
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from submission.支撑材料.coverage import ring_cover_radius
from submission.支撑材料.experiments import run_case

CANDIDATES = (1200.0, 1250.0, 1300.0, 1350.0, 1400.0,
              1450.0, 1500.0, 1550.0)
DEV_SEEDS = range(1000000, 1000150)
HELD_OUT_SEEDS = range(2300000, 2300500)


def summarize(rows):
    values = sorted(row["average_time_s"] for row in rows)
    return {
        "cases": len(rows),
        "all_cleared_cases": sum(row["fraction_cleared"] == 1 for row in rows),
        "mean_average_time_s": statistics.mean(values),
        "median_average_time_s": statistics.median(values),
        "p90_average_time_s": values[math.ceil(0.9 * len(values)) - 1],
        "mean_distance_m": statistics.mean(row["distance_m"] for row in rows),
        "mean_measures": statistics.mean(row["measures"] for row in rows),
    }


def run_radius(radius, seeds):
    cover = ring_cover_radius(radius)
    if cover > 1000.0:
        raise ValueError(f"unsafe candidate radius {radius}: cover={cover}")
    rows = []
    for seed in seeds:
        row = run_case(seed, 3, "enhanced", ring_radius=radius,
                       anchor_policy="nearest")
        row.pop("real_duration_s")  
        rows.append(row)
    return rows


def paired_summary(control, candidate):
    assert [row["seed"] for row in control] == [row["seed"] for row in candidate]
    deltas = [a["average_time_s"] - b["average_time_s"]
              for a, b in zip(control, candidate, strict=True)]
    mean = statistics.mean(deltas)
    standard_error = statistics.stdev(deltas) / math.sqrt(len(deltas))
    return {
        "cases": len(deltas),
        "mean_saved_s_per_source": mean,
        "approx_95pct_ci_s": [mean - 1.96 * standard_error,
                               mean + 1.96 * standard_error],
        "faster_candidate_cases": sum(delta > 0 for delta in deltas),
        "all_control_cleared_cases": sum(row["fraction_cleared"] == 1 for row in control),
        "all_candidate_cleared_cases": sum(row["fraction_cleared"] == 1 for row in candidate),
        "deltas_s_per_source": deltas,
    }


def main():
    development = {}
    for radius in CANDIDATES:
        rows = run_radius(radius, DEV_SEEDS)
        development[str(radius)] = {
            "ring_radius_m": radius,
            "exact_cover_radius_m": ring_cover_radius(radius),
            "summary": summarize(rows),
            "runs": rows,
        }
    ordered = sorted(development,
                     key=lambda key: development[key]["summary"]["mean_average_time_s"])
    winner, runner_up = ordered[0], ordered[1]
    held_out = {}
    held_out_rows = {}
    for radius in sorted({1200.0, float(winner), float(runner_up)}):
        rows = run_radius(radius, HELD_OUT_SEEDS)
        held_out_rows[str(radius)] = rows
        held_out[str(radius)] = {
            "ring_radius_m": radius,
            "exact_cover_radius_m": ring_cover_radius(radius),
            "summary": summarize(rows),
            "runs": rows,
        }
    control = "1200.0" if winner != "1200.0" else runner_up
    comparison = paired_summary(held_out_rows[control], held_out_rows[winner])
    comparison.update({"control_ring_radius_m": float(control),
                       "candidate_ring_radius_m": float(winner),
                       "control_role": "incumbent" if control == "1200.0" else "development_runner_up"})
    result = {
        "evidence": "held_out_local_synthetic_not_official",
        "selection": "Eight radii compared on existing development seeds; fresh confirmation seeds replace exploratory reuse of 1100000..1100499. No retuning after confirmation.",
        "total_runs": len(CANDIDATES) * len(DEV_SEEDS) + len(held_out_rows) * len(HELD_OUT_SEEDS),
        "candidate_radii_m": list(CANDIDATES),
        "development_seed_range": [DEV_SEEDS.start, DEV_SEEDS.stop - 1],
        "held_out_seed_range": [HELD_OUT_SEEDS.start, HELD_OUT_SEEDS.stop - 1],
        "development": development,
        "development_winner_m": float(winner),
        "development_runner_up_m": float(runner_up),
        "held_out": held_out,
        "held_out_comparison": comparison,
    }
    Path("results/ring_sweep.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "total_runs": result["total_runs"],
        "development_winner_m": float(winner),
        "development_runner_up_m": float(runner_up),
        "held_out_seed_range": result["held_out_seed_range"],
        "held_out": {key: value["summary"] for key, value in held_out.items()},
        "comparison": {key: value for key, value in comparison.items()
                       if key != "deltas_s_per_source"},
    }, indent=2))


if __name__ == "__main__":
    main()
