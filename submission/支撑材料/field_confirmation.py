

from __future__ import annotations
import json
from pathlib import Path
from submission.支撑材料.field_study import run_field, pair_stats, summarize

CONFIGS = {
    3: {
        "control": None,
        "route_only": {"premeasure": False, "portfolio": True},
        "route_info": {"premeasure": True, "negative_updates": True, "portfolio": True},
        "field": {
            "premeasure": True,
            "negative_updates": True,
            "portfolio": True,
            "approach_clear": True,
        },
    },
    4: {"control": None, "field": {"premeasure": True, "portfolio": True}},
}


def group(problem, name, seeds, scenario="random", mode="smooth"):
    rows = [
        run_field(seed, problem, CONFIGS[problem][name], scenario, mode)
        for seed in seeds
    ]
    for row in rows:
        row["configuration"] = name
    return rows


def main():
    records = []
    summary = {}
    comparisons = {}
    stress = {}
    for p in (3, 4):
        groups = {}
        for name in CONFIGS[p]:
            groups[name] = group(p, name, range(7100000, 7101000))
            records.extend(groups[name])
            summary[f"Q{p}_{name}"] = summarize(groups[name])
        comparisons[f"Q{p}"] = pair_stats(groups["control"], groups["field"])
        comparisons[f"Q{p}_ablation"] = {
            f"{a}_to_{b}": pair_stats(groups[a], groups[b])
            for a, b in zip(groups, list(groups)[1:])
        }
        print(f"Q{p}", json.dumps(comparisons[f"Q{p}"]), flush=True)
        cases = [
            (s, m, range(7200000, 7200050))
            for s in ("minimum_radius", "outward_boundary", "clustered")
            for m in ("smooth", "extreme", "iid_location")
        ]
        cases += [
            ("random", m, range(7210000, 7210200)) for m in ("extreme", "iid_location")
        ]
        for s, m, seeds in cases:
            a = group(p, "control", seeds, s, m)
            b = group(p, "field", seeds, s, m)
            records.extend(a)
            records.extend(b)
            key = f"Q{p}_{s}_{m}"
            stress[key] = {
                "control": summarize(a),
                "field": summarize(b),
                "paired": pair_stats(a, b),
            }
            print(key, json.dumps(stress[key]["paired"]), flush=True)
    result = {
        "evidence": "fresh_local_paired_confirmation_not_official_counterfactual",
        "selection": "Selected using official-observation bottlenecks and development seeds6100000..6100149 only. Refined probe=.22 control is unchanged. No retuning after this study.",
        "main_seed_range": [7100000, 7100999],
        "stress_seed_range": [7200000, 7200049],
        "alternate_error_seed_range": [7210000, 7210199],
        "development_seed_range": [6100000, 6100149],
        "main_runs": 6000,
        "stress_runs": 1800,
        "alternate_error_runs": 1600,
        "total_runs": len(records),
        "configs": CONFIGS,
        "summary": summary,
        "comparison": comparisons,
        "stress": stress,
        "runs": records,
    }
    assert len(records) == 9400
    Path("results/field_confirmation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({"total_runs": len(records), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
