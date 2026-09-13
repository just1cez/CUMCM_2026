"""Q1: actual bearing-halfplane intersection, without an artificial bounding box.

Feasibility and four coordinate LPs distinguish empty/unbounded/bounded sets.
For a bounded set all feasible pairwise boundary intersections are enumerated.
This optional Q1 analysis uses SciPy; the online search policy uses stdlib only.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from submission.支撑材料.geometry import diameter, enclosing_circle


def solve_intersection(stations, bearings_deg, error_deg=1.0):
    if len(stations) != len(bearings_deg) or not 0 <= error_deg < 90:
        raise ValueError("Match stations/readings and use an error in [0,90) degrees")
    if not stations:
        return {"status": "unbounded", "vertices": [], "diameter_m": None}
    rows, rhs = [], []
    alpha = math.radians(error_deg)
    for (x, y), angle in zip(stations, bearings_deg):
        if not all(math.isfinite(value) for value in (x, y, angle)):
            raise ValueError("Finite coordinates and bearings are required")
        theta = math.radians(angle % 360)
        for normal in (
            (math.sin(theta - alpha), -math.cos(theta - alpha)),
            (-math.sin(theta + alpha), math.cos(theta + alpha)),
            (-math.cos(theta), -math.sin(theta)),
        ):
            rows.append(normal)
            rhs.append(normal[0] * x + normal[1] * y)
    a, b = np.asarray(rows), np.asarray(rhs)
    feasible = linprog(
        np.zeros(2), A_ub=a, b_ub=b, bounds=[(None, None)] * 2, method="highs"
    )
    if feasible.status == 2:
        return {"status": "infeasible", "vertices": [], "diameter_m": None}
    if not feasible.success:
        raise RuntimeError(f"Halfplane feasibility LP failed: {feasible.message}")
    for objective in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
        bound = linprog(
            objective, A_ub=a, b_ub=b, bounds=[(None, None)] * 2, method="highs"
        )
        if bound.status == 3:
            return {"status": "unbounded", "vertices": [], "diameter_m": None}
        if not bound.success:
            raise RuntimeError(f"Halfplane boundedness LP failed: {bound.message}")
    vertices = []
    for i, j in itertools.combinations(range(len(a)), 2):
        determinant = a[i, 0] * a[j, 1] - a[i, 1] * a[j, 0]
        if determinant == 0:
            continue
        point = (
            (b[i] * a[j, 1] - a[i, 1] * b[j]) / determinant,
            (a[i, 0] * b[j] - b[i] * a[j, 0]) / determinant,
        )
        if np.max(a @ point - b) <= 1e-7 and all(
            math.dist(point, old) > 1e-7 for old in vertices
        ):
            vertices.append(point)
    if not vertices:
        raise ArithmeticError(
            "Bounded nonempty intersection had no numerical vertex; inspect conditioning"
        )
    center = tuple(np.mean(vertices, axis=0))
    vertices.sort(
        key=lambda point: math.atan2(point[1] - center[1], point[0] - center[0])
    )
    circle = enclosing_circle(vertices)
    return {
        "status": "bounded",
        "vertices": vertices,
        "diameter_m": diameter(vertices),
        "mec_center": circle[0],
        "mec_radius_m": circle[1],
        "max_halfplane_residual_m": max(float(np.max(a @ p - b)) for p in vertices),
    }


def main():
    triangle = [(0.0, 0.0), (36.0, 0.0), (18.0, 18 * math.sqrt(3))]
    length = 18 * math.sqrt(3) / math.tan(math.radians(2)) - 18
    stations = []
    for first, second in zip(triangle, triangle[1:] + triangle[:1]):
        stations.append(
            (
                first[0] - length * (second[0] - first[0]) / 36,
                first[1] - length * (second[1] - first[1]) / 36,
            )
        )
    bounded = solve_intersection(stations, [1, 121, 241])
    unbounded = solve_intersection([(0.0, 0.0)], [0.0])
    infeasible = solve_intersection([(0.0, 0.0), (-10.0, 0.0)], [0.0, 180.0])
    assert bounded["status"] == "bounded" and abs(bounded["diameter_m"] - 36) < 1e-6
    assert unbounded["status"] == "unbounded" and infeasible["status"] == "infeasible"
    result = {
        "evidence": "Q1_direct_halfplane_algorithm_examples",
        "bounded": bounded,
        "unbounded": unbounded,
        "infeasible": infeasible,
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/intersection_verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
