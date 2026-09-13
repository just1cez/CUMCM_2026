

from __future__ import annotations

import math

Point = tuple[float, float]


def _parameters(variant: str) -> tuple[float, float, float, float, float]:
    if variant == "seed25":
        return 990.0, 1865.0, 1.0, 0.25, 990.0
    if variant == "compact25":
        return 940.0, 1870.0, 5.0, 1.0, 993.0
    if variant == "fast25":
        return 928.0, 1865.0, 1.0, 0.75, 998.25
    raise ValueError("variant must be 'seed25', 'compact25' or 'fast25'")


def polar_waypoints(variant: str = "seed25") -> list[Point]:
    
    inner, outer, _, _, _ = _parameters(variant)
    points: list[Point] = [(0.0, 0.0)]
    for radius, phase in ((inner, 0.0), (outer, math.pi / 12.0)):
        for k in range(12):
            angle = k * math.pi / 6.0 + phase
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def polar_certificate(variant: str = "seed25") -> dict:
    
    inner, outer, shift, error, edge_bound = _parameters(variant)
    sine = (math.sqrt(6.0) - math.sqrt(2.0)) / 4.0
    cosine = (math.sqrt(6.0) + math.sqrt(2.0)) / 4.0
    inner_chord = 2.0 * inner * sine
    outer_chord = 2.0 * outer * sine
    cross_edge = math.sqrt(inner**2 + outer**2 - 2.0 * inner * outer * cosine)
    triangles: list[tuple[int, int, int]] = []
    for k in range(12):
        i = 1 + k
        j = 1 + (k + 1) % 12
        o = 13 + k
        p = 13 + (k + 1) % 12
        triangles.extend(((0, i, j), (i, o, j), (j, o, p)))
    edges = sorted({tuple(sorted((triangle[k], triangle[(k + 1) % 3])))
                    for triangle in triangles for k in range(3)})
    route = list(range(13)) + list(range(24, 12, -1))
    return {
        "variant": variant,
        "evidence": "analytic finite triangulation; not an experiment",
        "source_radius_m": 1800.0,
        "minimum_radio_radius_m": 1000.0,
        "point_count": 25,
        "inside_source_disk_count": 13,
        "outside_source_disk_count": 12,
        "origin_index": 0,
        "inner_indices": list(range(1, 13)),
        "outer_indices": list(range(13, 25)),
        "inner_radius_m": inner,
        "outer_radius_m": outer,
        "outer_phase_degrees": 15.0,
        "points": polar_waypoints(variant),
        "triangles_ccw": triangles,
        "edges": edges,
        "boundary_ccw": list(range(13, 25)),
        "triangle_count": 36,
        "edge_count": 60,
        "closed_form": {
            "cos_15": "(sqrt(6)+sqrt(2))/4",
            "sin_15": "(sqrt(6)-sqrt(2))/4",
            "outer_apothem": "b*cos(pi/12)",
            "inner_chord": "2*a*sin(pi/12)",
            "outer_chord": "2*b*sin(pi/12)",
            "cross_edge": "sqrt(a*a+b*b-2*a*b*cos(pi/12))",
            "maximum_edge": "max(a,inner_chord,outer_chord,cross_edge)",
        },
        "analytic_values_m": {
            "outer_apothem": outer * cosine,
            "inner_chord": inner_chord,
            "outer_chord": outer_chord,
            "cross_edge": cross_edge,
            "maximum_edge": max(inner, inner_chord, outer_chord, cross_edge),
        },
        "rational_trig_bounds": {
            "cos_15_lower": (9659, 10000),
            "sin_15_lower": (1, 4),
            "sin_15_upper": (259, 1000),
        },
        "robust_certificate": {
            "shift_m": shift,
            "per_waypoint_euclidean_error_bound_m": error,
            "triangle_diameter_upper_bound_m": edge_bound,
            "guard_disk_radius_m": 1800.0 + shift,
            "ideal_forward_projection_lower_bound_m": shift,
            "perturbed_forward_projection_lower_bound_m": shift - error,
            "perturbed_detection_distance_upper_bound_m": edge_bound + shift + error,
            "proof": "h=g+shift*n lies in the outer polygon; a triangle containing h has a vertex v with n.(v-g)>=shift and |v-g|<=diameter+shift",
        },
        "explicit_open_scan_route": {
            "indices": route,
            "length_formula": "a+22*(a+b)*sin(pi/12)+cross_edge",
            "analytic_length_m": inner + 11.0 * (inner_chord + outer_chord) + cross_edge,
            "returns_to_origin": False,
            "is_optimal": False,
        },
        "baseline_comparison": {
            "unchanged_baseline": "enhanced Q4: s=990, 31 triangular-lattice points",
            "baseline_waypoint_count": 31,
            "candidate_waypoint_count": 25,
            "baseline_full_20_channel_measurement_obligations": 620,
            "candidate_full_20_channel_measurement_obligations": 500,
            "claimed_total_runtime_gain": None,
        },
        "smaller_candidate": {
            "accepted": False,
            "reason": "No fewer-point construction is certified here; the notes exclude equal two-ring sizes <=11 and 12 regular outer vertices with <=11 inner vertices of radius <=1000 under the diameter-triangulation certificate.",
            "global_minimality_claim": False,
        },
    }
