from pathlib import Path
import json, statistics, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from submission.支撑材料.experiments import run_case

old = []
new = []
for seed in range(4100000, 4101000):
    old.append(
        run_case(
            seed,
            4,
            "enhanced",
            coverage_policy="compact25",
            dispatch_policy="guarded",
            scan_policy="useful",
        )
    )
    new.append(
        run_case(
            seed,
            4,
            "refined",
            coverage_policy="fast25",
            dispatch_policy="guarded",
            scan_policy="useful",
        )
    )
d = [a["average_time_s"] - b["average_time_s"] for a, b in zip(old, new)]
summary = {
    "evidence": "local_synthetic_paired_check_not_official",
    "seed_range": [4100000, 4100999],
    "cases": len(d),
    "compact_mean": statistics.mean(r["average_time_s"] for r in old),
    "fast_mean": statistics.mean(r["average_time_s"] for r in new),
    "mean_saved_fast": statistics.mean(d),
    "median_saved_fast": statistics.median(d),
    "approx_95pct_ci": [
        statistics.mean(d) - 1.96 * statistics.stdev(d) / (len(d) ** 0.5),
        statistics.mean(d) + 1.96 * statistics.stdev(d) / (len(d) ** 0.5),
    ],
    "faster_cases": sum(x > 0 for x in d),
    "compact_all_clear": sum(r["fraction_cleared"] == 1 for r in old),
    "fast_all_clear": sum(r["fraction_cleared"] == 1 for r in new),
    "compact_mean_distance": statistics.mean(r["distance_m"] for r in old),
    "fast_mean_distance": statistics.mean(r["distance_m"] for r in new),
    "compact_mean_measures": statistics.mean(r["measures"] for r in old),
    "fast_mean_measures": statistics.mean(r["measures"] for r in new),
    "compact_mean_failures": statistics.mean(r["failed_clears"] for r in old),
    "fast_mean_failures": statistics.mean(r["failed_clears"] for r in new),
}
print(json.dumps(summary, indent=2))
for row in old:
    row["configuration"] = "compact25"
for row in new:
    row["configuration"] = "fast25"
summary["total_runs"] = len(old) + len(new)
summary["runs"] = old + new
Path("results/fast_vs_compact_410.json").write_text(
    json.dumps(summary, indent=2) + "\n"
)
