

from __future__ import annotations

import itertools
import json
import math
import random
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from submission.支撑材料.coverage import coverage_certificate, directional_waypoints, omni_waypoints
from submission.支撑材料.geometry import (
    clip_bearing,
    diameter,
    enclosing_circle,
    initial_polygon,
    optical_cover,
)


def contains(poly, p, tolerance=1e-6):
    if not poly:
        return False
    area = sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(poly, poly[1:] + poly[:1]))
    sign = 1 if area >= 0 else -1
    return all(
        sign * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
        >= -tolerance
        for a, b in zip(poly, poly[1:] + poly[:1])
    )


def reference_circle(points):
    
    candidates = [(p, 0.0) for p in points]
    for a, b in itertools.combinations(points, 2):
        c = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        candidates.append((c, math.dist(a, b) / 2))
    for a, b, c in itertools.combinations(points, 3):
        ab, ac = np.asarray(b) - a, np.asarray(c) - a
        matrix = 2 * np.array([ab, ac])
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        offset = np.linalg.solve(matrix, np.array([ab @ ab, ac @ ac]))
        center = np.asarray(a) + offset
        candidates.append((tuple(center), math.dist(center, a)))
    feasible = [
        (c, r)
        for c, r in candidates
        if all(math.dist(c, p) <= r + 1e-7 for p in points)
    ]
    return min(feasible, key=lambda item: item[1])


def main():
    exact_ray = clip_bearing(
        [(-100.0, 0.0), (100.0, 0.0)], (0.0, 0.0), 0.0, error_deg=0.0
    )
    assert min(p[0] for p in exact_ray) >= -1e-6, (
        "Zero-error bearing retained its backward ray"
    )
    try:
        directional_waypoints(1e-300)
    except ValueError:
        pass
    else:
        raise AssertionError("Extreme lattice refinement was not rejected")
    rng = random.Random(831762)
    max_mec_error = 0.0
    sets = [
        [(0.0, 0.0)],
        [(0.0, 0.0), (36.0, 0.0), (18.0, 18 * math.sqrt(3))],
        [(0.0, 0.0), (1.0, 1e-12), (2.0, 0.0)],
        [(7.0, 5.0), (7.0, 5.0)],
    ]
    sets += [
        [
            (rng.uniform(-2000, 2000), rng.uniform(-2000, 2000))
            for _ in range(rng.randint(2, 9))
        ]
        for _ in range(500)
    ]
    for points in sets:
        actual = enclosing_circle(points)
        expected = reference_circle(points)
        max_mec_error = max(max_mec_error, abs(actual[1] - expected[1]))
        assert abs(actual[1] - expected[1]) < 1e-6, (points, actual, expected)
        assert all(math.dist(actual[0], p) <= actual[1] for p in points)
    triangle = [(0.0, 0.0), (36.0, 0.0), (18.0, 18 * math.sqrt(3))]
    polygon = initial_polygon()
    length = 18 * math.sqrt(3) / math.tan(math.radians(2)) - 18
    stations = []
    for i, (a, b) in enumerate(zip(triangle, triangle[1:] + triangle[:1])):
        unit = ((b[0] - a[0]) / 36, (b[1] - a[1]) / 36)
        s = (a[0] - length * unit[0], a[1] - length * unit[1])
        stations.append(s)
        polygon = clip_bearing(polygon, s, 1 + 120 * i, error_deg=1.0)
    counterexample = {
        "stations": stations,
        "bearings_deg": [1, 121, 241],
        "diameter_m": diameter(polygon),
        "mec_radius_m": enclosing_circle(polygon)[1],
    }
    assert abs(counterexample["diameter_m"] - 36) < 1e-6
    assert counterexample["mec_radius_m"] > 20
    
    containment_trials = 2000
    optical_trials = 0
    for index in range(containment_trials):
        angle = rng.uniform(0, math.tau)
        radius = 1800 if index % 5 == 0 else 1800 * math.sqrt(rng.random())
        source = (radius * math.cos(angle), radius * math.sin(angle))
        poly = initial_polygon()
        for j in range(4):
            r, phi = rng.uniform(6, 1500), rng.uniform(0, math.tau)
            station = (source[0] + r * math.cos(phi), source[1] + r * math.sin(phi))
            error = rng.choice([-1.0, 1.0]) if index % 2 else rng.uniform(-1, 1)
            bearing = round((math.degrees(phi) + 180 + error) % 360, 2) % 360
            poly = clip_bearing(poly, station, bearing)
            assert contains(poly, source), (index, source, poly)
        if index < 200:
            centers = optical_cover(poly)
            for _ in range(20):
                weights = [rng.random() for _ in poly]
                total = sum(weights)
                p = tuple(
                    sum(w * vertex[k] for w, vertex in zip(weights, poly)) / total
                    for k in (0, 1)
                )
                assert min(math.dist(p, c) for c in centers) <= 19.9 + 1e-7
                optical_trials += 1
    omni, directional = omni_waypoints(), directional_waypoints()
    max_omni_distance, min_directional_slack = 0.0, float("inf")
    for i in range(2000):
        angle = rng.uniform(0, math.tau)
        radius = 1800 if i % 2 else 1800 * math.sqrt(rng.random())
        p = (radius * math.cos(angle), radius * math.sin(angle))
        max_omni_distance = max(max_omni_distance, min(math.dist(p, s) for s in omni))
        nearby = [s for s in directional if math.dist(p, s) <= 990 + 1e-7]
        
        points = np.asarray(nearby)
        solved = linprog(
            np.zeros(len(points)),
            A_eq=np.vstack([points.T, np.ones(len(points))]),
            b_eq=np.array([*p, 1.0]),
            bounds=(0, None),
            method="highs",
        )
        assert solved.success, p
        for _ in range(5):
            phi = rng.uniform(0, math.tau)
            seen = [
                math.dist(p, s)
                for s in directional
                if (s[0] - p[0]) * math.cos(phi) + (s[1] - p[1]) * math.sin(phi) >= 0
            ]
            min_directional_slack = min(min_directional_slack, 1000 - min(seen))
    assert max_omni_distance <= 900 + 1e-7 and min_directional_slack >= 0
    
    alpha = math.radians(1.005)
    max_reception_excess = -float("inf")
    for _ in range(10000):
        t = rng.uniform(1, 999)
        bmax = min(
            math.sqrt(1e6 - t * t),
            math.sqrt(1e6 - (t - 1000 * math.cos(alpha)) ** 2) - 1000 * math.sin(alpha),
        )
        b = rng.uniform(-1, 1) * max(0.0, bmax)
        r, phi = rng.uniform(0, 1500), rng.uniform(-alpha, alpha)
        excess = math.dist((t, b), (r * math.cos(phi), r * math.sin(phi))) - max(
            1000, r
        )
        max_reception_excess = max(max_reception_excess, excess)
        assert excess <= 1e-6
    result = {
        "evidence": "independent_numerical_checks_not_a_substitute_for_analytic_proofs",
        "exact_forward_ray_regression": True,
        "unbounded_refinement_rejected": True,
        "mec_reference_cases": len(sets),
        "maximum_mec_radius_error_m": max_mec_error,
        "realizable_counterexample": counterexample,
        "containment_cases": containment_trials,
        "bearings_per_case": 4,
        "optical_interior_samples": optical_trials,
        "coverage_source_samples": 2000,
        "maximum_sampled_omni_distance_m": max_omni_distance,
        "minimum_sampled_directional_radio_slack_m": min_directional_slack,
        "triple_lens_samples": 10000,
        "maximum_sampled_reception_excess_m": max_reception_excess,
        "coverage_certificate": coverage_certificate(),
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/geometry_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    
    
    
    
    station_probe_bound = math.hypot(1501, 120)
    source_probe_bound = 1500 + station_probe_bound
    assert station_probe_bound < 1506 and source_probe_bound < 3006
    max_move = 31 * 5240 + 16 * (7500 + 5 * 6020 + 4520 + 4520 + 7570)
    max_time = max_move / 5 + 1212 * 6 + 3584 * 5
    assert max_time < 100 * 3600 <= 360000
    bound = {
        "evidence": "arithmetic_of_analytic_bound_not_simulation",
        "scope": "enhanced policy: Q3 ring1200, Q4 rolling skeleton, fixed probes, six probes",
        "skeleton_edge_upper_m": 5240,
        "skeleton_move_upper_m": 31 * 5240,
        "positive_source_distance_upper_m": 1500,
        "strip_axial_upper_m": 1501,
        "strip_width_upper_m": 53,
        "station_probe_bound_m": station_probe_bound,
        "source_probe_bound_m": source_probe_bound,
        "local_transition_upper_m": 6020,
        "local_task_entry_upper_m": 7500,
        "optional_center_clear_access_upper_m": 4520,
        "optical_access_upper_m": 4520,
        "optical_cover_centers_upper": 216,
        "optical_snake_length_upper_m": 7570,
        "distance_upper_m": max_move,
        "measure_upper": 1212,
        "clear_attempt_upper": 3584,
        "virtual_time_upper_s": max_time,
        "virtual_time_upper_h": max_time / 3600,
        "proof": "report/bound_proof.tex; no guarantee for real network deadline",
    }
    Path("results/operation_bound.json").write_text(json.dumps(bound, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
