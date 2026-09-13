
from __future__ import annotations

import itertools
import json
import math
import random
from pathlib import Path

from submission.支撑材料.active_policy_candidate import score_probes
from submission.支撑材料.coverage import directional_waypoints, omni_waypoints, ring_cover_radius
from submission.支撑材料.geometry import clip_bearing, enclosing_circle, initial_polygon
from submission.支撑材料.route_policy_candidate import optimize_waypoints


def length(points, order, start):
    sequence = [start] + [points[i] for i in order]
    return sum(math.dist(a, b) for a, b in itertools.pairwise(sequence))


def main():
    rng = random.Random(417072)
    route_cases, interval_cases = 0, 0
    for size in (0,1,2,7,31):
        for _ in range(10):
            points = [(rng.uniform(-2500,2500), rng.uniform(-2500,2500)) for _ in range(size)]
            start = (rng.uniform(-1000,1000),rng.uniform(-1000,1000))
            route = optimize_waypoints(points,start)
            assert sorted(route) == list(range(size))
            current, pending, greedy = start, set(range(size)), []
            while pending:
                i = min(pending,key=lambda i:(math.dist(current,points[i]),i))
                greedy.append(i); pending.remove(i); current = points[i]
            assert length(points,route,start) <= length(points,greedy,start)+1e-7
            route_cases += 1
    ring = omni_waypoints(1200.)
    rho = ring_cover_radius(1200.)
    for _ in range(2000):
        r, phi = 1800*math.sqrt(rng.random()), rng.uniform(0,math.tau)
        source = (r*math.cos(phi), r*math.sin(phi))
        assert min(math.dist(source,p) for p in ring) <= rho + 1e-7
    attained = min(math.dist((1800*math.cos(math.pi/6),1800*math.sin(math.pi/6)),p) for p in ring)
    assert abs(attained-rho)<1e-7 and rho<1000
    ring_tours = []
    for d in (1200.0, 1550.0, 900.0 * math.sqrt(3.0)):
        centers = omni_waypoints(d)[1:]
        minimum = min(length(centers, order, (0.0, 0.0))
                      for order in itertools.permutations(range(6)))
        assert abs(minimum - 6 * d) < 1e-7
        ring_tours.append({"radius_m": d, "permutations": 720,
                           "minimum_length_m": minimum, "analytic_length_m": 6 * d})
    vertex_cases = 0
    for spacing in (900.0, 950.0, 990.0, 999.0):
        vertices = directional_waypoints(spacing)
        for source in vertices:
            if math.hypot(*source) > 1800.0 + 1e-8:
                continue
            for k in range(6):
                neighbor = (source[0] + spacing * math.cos(k * math.pi / 3),
                            source[1] + spacing * math.sin(k * math.pi / 3))
                assert min(math.dist(neighbor, v) for v in vertices) < 1e-7
            vertex_cases += 1
    max_violation = -float('inf')
    for bearing in (0., 89., 179., 359.99):
        poly = clip_bearing(initial_polygon(),(0.,0.),bearing)
        table = score_probes(poly,[((0.,0.),bearing)],(0.,0.),3,include_lens=False)
        for row in table:
            if not row['eligible']:
                continue
            for angle in range(0,360,2):
                post = clip_bearing(poly,row['point'],angle)
                if not post:
                    continue
                violation = enclosing_circle(post)[1] - row['positive_bearing_radius_upper_m']
                max_violation = max(max_violation,violation)
                assert violation <= 1e-6
                interval_cases += 1
    result = {'evidence':'numerical_sanity_plus_analytic_geometry_not_official',
              'route_cases':route_cases, 'ring_samples':2000,
              'ring_radius_m':1200.,'exact_ring_cover_radius_m':rho,
              'attained_boundary_radius_m':attained, 'radio_margin_m':1000-rho,
              'ring_tour_exhaustive':ring_tours,
              'source_vertex_six_neighbor_cases':vertex_cases,
              'candidate_posterior_cases':interval_cases,'max_interval_bound_violation_m':max_violation}
    Path('results/refinement_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
