import json
import statistics
from pathlib import Path

from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.planner import Planner

rows, summary = [], {}
for scenario in ("random", "minimum_radius", "outward_boundary", "clustered"):
    for enabled in (False, True):
        name = "recovery" if enabled else "two_flanks"
        group = []
        for seed in range(500000, 500100):
            env = LocalSimulator(seed, 4, "smooth", scenario)
            result = Planner(env, 4, strategy="integrated", loss_recovery=enabled).run()
            actual = env.summary()
            assert actual["fraction_cleared"] == 1
            group.append(actual)
            rows.append({**actual, "policy": name})
        summary[f"{scenario}_{name}"] = {
            "runs": len(group),
            "mean_average_time_s": statistics.mean(r["average_time_s"] for r in group),
            "mean_failed_clears": statistics.mean(r["failed_clears"] for r in group),
            "worst_virtual_time_s": max(r["virtual_time_s"] for r in group),
        }
result = {
    "evidence": "synthetic_development_comparison_not_final_holdout",
    "summary": summary,
    "runs": rows,
}
Path("results/recovery_development.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(summary, indent=2))
