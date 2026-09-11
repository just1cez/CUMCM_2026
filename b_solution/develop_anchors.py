"""Development-only anchor geometry and rolling route screen, no official calls."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from environment import LocalSimulator
from planner import Planner


def case(seed, problem, route, ring_radius=None):
    env = LocalSimulator(seed, problem=problem)
    policy = Planner(env, problem=problem, strategy="integrated", anchor_policy=route,
                     ring_radius=ring_radius)
    result = policy.run()
    actual = env.summary()
    assert result['certificate_complete'] and actual['fraction_cleared'] == 1
    return actual


def main():
    results = {}
    for problem in (3, 4):
        configs = [('nearest', None), ('rolling', None)]
        if problem == 3:
            configs += [('nearest', 1200.), ('rolling', 1200.)]
        baseline = None
        for route, radius in configs:
            rows = [case(1000000+k, problem, route, radius) for k in range(150)]
            if baseline is None:
                baseline = rows
            differences = [a['average_time_s']-b['average_time_s'] for a,b in zip(baseline,rows)]
            results[f'Q{problem}_{route}_{radius}'] = {
                'cases':len(rows), 'mean_s_per_source':statistics.mean(r['average_time_s'] for r in rows),
                'mean_distance_m':statistics.mean(r['distance_m'] for r in rows),
                'mean_measures':statistics.mean(r['measures'] for r in rows),
                'mean_saved_s_per_source':statistics.mean(differences),
                'faster_cases':sum(d>0 for d in differences), 'all_cleared':True,
                'runs':rows}
    Path('results/anchor_development.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({k:{f:v for f,v in row.items() if f!='runs'} for k,row in results.items()},indent=2))


if __name__ == '__main__':
    main()
