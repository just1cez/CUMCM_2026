
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import submission.支撑材料.coverage as coverage

R = coverage.ARENA_RADIUS
Q = coverage.MIN_RADIO_RADIUS
S = coverage.DEFAULT_SPACING
EPS_CANDIDATES = (1.0,)


DIRS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))

def xy(ij: tuple[int, int]) -> tuple[float, float]:
    i, j = ij
    return (S * (i + j / 2.0), S * math.sqrt(3.0) * j / 2.0)

def norm(p: tuple[float, float]) -> float:
    return math.hypot(*p)

def sub(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] - b[0], a[1] - b[1])

def dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]

def add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])

def scale(c: float, a: tuple[float, float]) -> tuple[float, float]:
    return (c * a[0], c * a[1])


def actual_lattice() -> dict[tuple[int, int], tuple[float, float]]:
    pts = coverage.directional_waypoints(S)
    axial: dict[tuple[int, int], tuple[float, float]] = {}
    for p in pts:
        
        
        j = round(p[1] / (S * math.sqrt(3.0) / 2.0))
        i = round(p[0] / S - j / 2.0)
        ij = (i, j)
        assert math.dist(p, xy(ij)) < 1e-8
        axial[ij] = p
    assert len(axial) == 31
    return axial

def witness_for(vij: tuple[int, int], points: dict[tuple[int, int], tuple[float, float]]) -> dict:
    v = points[vij]
    candidates = []
    for k in range(6):
        d1, d2 = DIRS[k], DIRS[(k + 1) % 6]
        uij = (vij[0] + d1[0], vij[1] + d1[1])
        wij = (vij[0] + d2[0], vij[1] + d2[1])
        if uij not in points or wij not in points:
            continue
        m = scale(0.5, add(points[uij], points[wij]))
        nvec = sub(v, m)
        h = norm(nvec)
        n = scale(1.0 / h, nvec)
        for eps in EPS_CANDIDATES:
            g = add(m, scale(eps, n))
            if norm(g) >= R:
                continue
            rows = []
            for ij, p in points.items():
                distance = norm(sub(p, g))
                forward = dot(sub(p, g), n)
                rows.append((ij, distance, forward))
            reachable = [row for row in rows if row[1] <= Q + 1e-8 and row[2] >= -1e-8]
            if len(reachable) == 1 and reachable[0][0] == vij:
                candidates.append((eps, m, n, g, rows, uij, wij))
                break
    assert candidates, f"no elementary witness for {vij}"
    eps, m, n, g, rows, uij, wij = min(candidates, key=lambda z: (z[0], z[1]))
    target_distance = norm(sub(v, g))
    second = min(norm(sub(p, g)) for ij, p in points.items() if ij != vij)
    reachable = sorted((dist, ij) for ij, dist, fw in rows if dist <= Q + 1e-8 and fw >= -1e-8)
    assert reachable[0][1] == vij and len(reachable) == 1
    return {"solevertex": list(vij), "target": list(vij), "edge_neighbors": [list(uij), list(wij)],
            "midpoint": list(m), "epsilon": eps, "source": list(g), "n": list(n),
            "normal": list(n), "source_radius": norm(g),
            "target_distance": target_distance, "second_detector_distance": second,
            "reachable": [[list(ij), dist] for dist, ij in reachable],
            "min_other_forward": min(fw for ij, dist, fw in rows if ij != vij),
            "midpoint_to_nearest_other_positive": min(norm(sub(p, m)) for ij, p in points.items()
                                                       if ij not in (uij, wij, vij) and dot(sub(p, m), n) > 1e-8)}

def main() -> None:
    points = actual_lattice()
    witnesses = [witness_for(ij, points) for ij in sorted(points)]
    for w in witnesses:
        assert w["source_radius"] < R and w["target_distance"] <= Q
        assert len(w["reachable"]) == 1
        assert w["second_detector_distance"] > 5.0
    optimal_d = math.hypot(R, Q)
    half_angle = math.atan(Q / R)
    attained_angle = math.acos(R / optimal_d)
    assert abs(attained_angle - half_angle) < 1e-12
    for i in range(1001):
        d = R + i * Q / 1000
        cos_limit = max(R / d, (d*d + R*R - Q*Q) / (2*d*R))
        assert math.acos(min(1.0, cos_limit)) <= half_angle + 1e-12
    result = {"parameters": {"arena_radius": R, "receive_radius": Q,
                              "spacing": S, "point_count": len(points)},
              "q3_boundary_angle_lower_bound": {"q": 900.0, "minimum_points": 7,
                  "half_angle_radians": math.asin(900.0 / R),
                  "reason": "six arcs have total angular capacity 2*pi only at equality; equality ring misses origin"},
              "q1000_static_seven_irreducible": {"minimum_fixed_subset": 7,
                  "boundary_arc_capacity_of_five": 10.0 * math.asin(Q / R),
                  "origin_to_ring": 900.0 * math.sqrt(3.0)},
              "q4_global_outer_boundary_lower_bound": {"minimum_outer_detectors": 7,
                  "half_angle_radians": math.atan(Q / R),
                  "optimal_detector_radius": optimal_d,
                  "attained_half_angle_radians": attained_angle,
                  "checked_detector_radii": 1001,
                  "statement": "lower bound for arbitrary placements at an outward boundary source; not a 31-point global optimum claim"},
              "witnesses": witnesses}
    out = ROOT / "results" / "coverage_limits.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
