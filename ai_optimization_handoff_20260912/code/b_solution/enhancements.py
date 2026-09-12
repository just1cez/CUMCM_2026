"""Frozen held-out comparison of accepted geometric/rolling enhancements."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from coverage import ring_cover_radius
from experiments import aggregate, run_case


def paired_summary(control, enhanced):
    assert [r['seed'] for r in control] == [r['seed'] for r in enhanced]
    differences = [a['average_time_s']-b['average_time_s'] for a,b in zip(control, enhanced)]
    average = statistics.mean(differences)
    stderr = statistics.stdev(differences)/math.sqrt(len(differences))
    return {'cases':len(differences), 'mean_saved_s_per_source':average,
            'mean_reduction_pct':100*average/statistics.mean(r['average_time_s'] for r in control),
            'approx_95pct_ci_s':[average-1.96*stderr, average+1.96*stderr],
            'faster_cases':sum(d>0 for d in differences),
            'mean_distance_saved_m':statistics.mean(a['distance_m']-b['distance_m'] for a,b in zip(control,enhanced))}


def main():
    rows, summary, comparison, stress = [], {}, {}, {}
    for problem in (3,4):
        paired = []
        for policy in ('integrated','enhanced'):
            group = [run_case(1100000+k,problem,policy) for k in range(500)]
            rows.extend(group)
            summary[f'Q{problem}_{policy}'] = aggregate(group)
            paired.append(group)
        comparison[f'Q{problem}'] = paired_summary(*paired)
        for scenario in ('minimum_radius','outward_boundary','clustered'):
            for mode in ('smooth','extreme','iid_location'):
                groups = []
                for policy in ('integrated','enhanced'):
                    group = [run_case(1110000+k,problem,policy,scenario,mode) for k in range(30)]
                    rows.extend(group)
                    groups.append(group)
                key = f'Q{problem}_{scenario}_{mode}'
                stress[key] = {'integrated':aggregate(groups[0]), 'enhanced':aggregate(groups[1]),
                               'paired':paired_summary(*groups)}
    result = {'evidence':'held_out_local_synthetic_not_official',
              'selection':'Only development seeds1000000..1000149 used; final seeds excluded from choice',
              'main_seed_range':[1100000,1100499], 'stress_seed_range':[1110000,1110029],
              'total_runs':len(rows), 'summary':summary, 'comparison':comparison, 'stress':stress,
              'contracted_ring':{'radius_m':1200., 'exact_cover_radius_m':ring_cover_radius(1200.),
                                 'radio_margin_m':1000-ring_cover_radius(1200.)}, 'runs':rows}
    Path('results/enhancement_experiments.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('runs','stress')},indent=2))


if __name__ == '__main__':
    main()
