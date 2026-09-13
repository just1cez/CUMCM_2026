
from __future__ import annotations

import json
import statistics
from pathlib import Path

from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.planner import Planner


def run(seed, problem, anchor_policy):
    env = LocalSimulator(seed, problem=problem, scenario="random", error_mode="smooth")
    planner = Planner(env, problem=problem, strategy="integrated", anchor_policy=anchor_policy)
    planner.run()
    result = env.summary()
    assert result["fraction_cleared"] == 1
    return result


def main():
    output = {}
    records = []
    for problem in (3, 4):
        pairs = [(run(950000 + k, problem, "nearest"), run(950000 + k, problem, "two_opt")) for k in range(200)]
        records.extend({"problem":problem, "seed":950000+k,
                        "nearest":a, "two_opt":b} for k,(a,b) in enumerate(pairs))
        deltas = [a["average_time_s"] - b["average_time_s"] for a, b in pairs]
        output[f"Q{problem}"] = {
            "cases": len(pairs),
            "all_nearest_cleared": sum(a["fraction_cleared"] == 1 for a, _ in pairs),
            "all_two_opt_cleared": sum(b["fraction_cleared"] == 1 for _, b in pairs),
            "nearest_mean_s_per_source": statistics.mean(a["average_time_s"] for a, _ in pairs),
            "two_opt_mean_s_per_source": statistics.mean(b["average_time_s"] for _, b in pairs),
            "mean_saved_s_per_source": statistics.mean(deltas),
            "median_saved_s_per_source": statistics.median(deltas),
            "faster_cases": sum(d > 0 for d in deltas),
            "mean_distance_saved_m": statistics.mean(a["distance_m"] - b["distance_m"] for a, b in pairs),
        }
    result = {"evidence": "local_synthetic_route_candidate_not_official", "seed_range": [950000, 950199], "summary": output, "runs":records}
    Path("results/route_candidate_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
