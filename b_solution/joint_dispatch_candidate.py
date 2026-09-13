

from __future__ import annotations

from math import dist, isfinite

Point = tuple[float, float]
Task = tuple[str, int]


def choose_task(
    position: Point,
    anchors: dict[int, Point],
    targets: dict[int, tuple[Point, float]],
    *,
    choice: str = "guarded",
    risk_weight: float = 1.0,
) -> Task:
    
    if choice not in ("center", "guarded"):
        raise ValueError("choice must be 'center' or 'guarded'")
    tasks: list[Task] = [("target", key) for key in sorted(targets)]
    tasks.extend(("anchor", key) for key in sorted(anchors))
    n = len(tasks)
    if not n:
        raise ValueError("cannot dispatch an empty task set")

    coords = [targets[key][0] for key in sorted(targets)]
    coords.extend(anchors[key] for key in sorted(anchors))
    radii = [targets[key][1] for key in sorted(targets)]
    radii.extend(0.0 for _ in anchors)
    if any(len(point) != 2 or not all(isfinite(x) for x in point)
           for point in [position, *coords]):
        raise ValueError("positions must be finite two-dimensional points")
    if any(not isfinite(radius) or radius < 0 for radius in radii):
        raise ValueError("MEC radii must be finite and nonnegative")
    if not isfinite(risk_weight) or risk_weight < 0:
        raise ValueError("risk_weight must be finite and nonnegative")
    penalty = [risk_weight * radius for radius in radii] if choice == "guarded" else [0.0] * n
    origin = [dist(position, point) for point in coords]
    edges = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            edges[i][j] = edges[j][i] = dist(coords[i], coords[j])
    if (any(not isfinite(value) for value in origin)
            or any(not isfinite(value) for row in edges for value in row)):
        raise ValueError("pairwise distances must be finite")

    
    
    first = min(range(n), key=lambda i: (origin[i] + penalty[i], i))
    route = [first]
    remaining = set(range(n))
    remaining.remove(first)
    nearest = [min(origin[i], edges[first][i]) for i in range(n)]
    while remaining:
        node = min(remaining, key=lambda i: (nearest[i], i))
        best_gap = 0
        best_delta = (origin[node] + edges[node][route[0]] - origin[route[0]]
                      + penalty[node] - penalty[route[0]])
        for gap in range(1, len(route) + 1):
            before = route[gap - 1]
            delta = edges[before][node]
            if gap < len(route):
                after = route[gap]
                delta += edges[node][after] - edges[before][after]
            if delta < best_delta:
                best_gap, best_delta = gap, delta
        route.insert(best_gap, node)
        remaining.remove(node)
        for other in remaining:
            nearest[other] = min(nearest[other], edges[node][other])

    
    
    
    
    for _ in range(n):
        changed = False
        for left in range(n - 1):
            for right in range(left + 1, n):
                old = (origin[route[left]] if left == 0
                       else edges[route[left - 1]][route[left]])
                new = (origin[route[right]] if left == 0
                       else edges[route[left - 1]][route[right]])
                if right + 1 < n:
                    old += edges[route[right]][route[right + 1]]
                    new += edges[route[left]][route[right + 1]]
                if left == 0:
                    old += penalty[route[left]]
                    new += penalty[route[right]]
                if new + 1e-12 * max(1.0, old, new) < old:
                    route[left:right + 1] = reversed(route[left:right + 1])
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    return tasks[route[0]]
