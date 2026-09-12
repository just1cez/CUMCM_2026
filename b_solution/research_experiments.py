"""Frozen holdout/ablation/robustness study; all observations are synthetic.

Development uses 3100000..3100149 only. No choice is made from this file's
holdout results: refined defaults are frozen before its first execution.
"""
from __future__ import annotations

import json
from pathlib import Path

from experiments import aggregate, run_case
from refinement_study import paired

CONFIGS = {
    3: {
        "control": ("enhanced", {}),
        "joint_all": ("enhanced", {"dispatch_policy": "center"}),
        "refined": ("refined", {}),
    },
    4: {
        "control": ("enhanced", {}),
        "polar_only": ("enhanced", {"coverage_policy": "compact25"}),
        "joint_all": ("enhanced", {"coverage_policy": "compact25", "dispatch_policy": "guarded"}),
        "refined": ("refined", {}),
    },
}


def group(problem, name, seeds, scenario="random", mode="smooth", **override):
    strategy, config = CONFIGS[problem][name]
    result = []
    for seed in seeds:
        row = run_case(seed, problem, strategy, scenario, mode, **(config | override))
        row["configuration"] = name
        result.append(row)
    return result


def main():
    rows, summary, comparisons, stress, sensitivity = [], {}, {}, {}, {}
    for problem in (3, 4):
        current = {}
        for name in CONFIGS[problem]:
            current[name] = group(problem, name, range(4100000,4101000))
            rows.extend(current[name])
            summary[f"Q{problem}_{name}"] = aggregate(current[name])
        comparisons[f"Q{problem}"] = paired(current["control"],current["refined"])
        order=list(current)
        comparisons[f"Q{problem}_incremental"] = {
            f"{a}_to_{b}":paired(current[a],current[b]) for a,b in zip(order,order[1:])}
        print(f"holdout Q{problem}",json.dumps(comparisons[f"Q{problem}"]),flush=True)
        scenarios=[(scenario,mode,range(4200000,4200050))
                   for scenario in ("minimum_radius","outward_boundary","clustered")
                   for mode in ("smooth","extreme","iid_location")]
        scenarios.extend(("random",mode,range(4210000,4210200)) for mode in ("extreme","iid_location"))
        for scenario,mode,seeds in scenarios:
            control=group(problem,"control",seeds,scenario,mode)
            refined=group(problem,"refined",seeds,scenario,mode)
            rows.extend(control);rows.extend(refined)
            key=f"Q{problem}_{scenario}_{mode}"
            stress[key]={"control":aggregate(control),"refined":aggregate(refined),"paired":paired(control,refined)}
            print(key,json.dumps(stress[key]["paired"]),flush=True)
        for scale in (.12,.22,.4):
            selected=group(problem,"refined",range(4300000,4300050),probe_scale=scale)
            rows.extend(selected)
            sensitivity[f"Q{problem}_probe_{scale}"]=aggregate(selected)
    result={"evidence":"frozen_held_out_local_synthetic_not_official",
            "selection":"Q3 center/unknown, Q4 compact25/guarded/useful frozen using development 3100000..3100149 only; rectangle optical cover retained",
            "development_seed_range":[3100000,3100149],"main_seed_range":[4100000,4100999],
            "stress_seed_range":[4200000,4200049],"alternate_error_seed_range":[4210000,4210199],
            "sensitivity_seed_range":[4300000,4300049],"main_cases_per_problem":1000,
            "configs":CONFIGS,"total_runs":len(rows),"summary":summary,"comparison":comparisons,
            "stress":stress,"sensitivity":sensitivity,"runs":rows}
    Path("results/research_experiments.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"total_runs":len(rows),"summary":summary,"comparison":comparisons},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
