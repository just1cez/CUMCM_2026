

from __future__ import annotations

from math import dist, fsum, isfinite

Point = tuple[float, float]
Task = tuple[str, int]


def _cost(
    route: list[int],
    origin: list[float],
    edges: list[list[float]],
    penalty: list[float],
) -> float:
    try:
        value = fsum(
            (
                origin[route[0]],
                penalty[route[0]],
                *(edges[a][b] for a, b in zip(route, route[1:])),
            )
        )
    except OverflowError as error:
        raise ValueError("route proxy must be finite") from error
    if not isfinite(value):
        raise ValueError("route proxy must be finite")
    return value


def _insertion_delta(
    route: list[int],
    node: int,
    gap: int,
    origin: list[float],
    edges: list[list[float]],
    penalty: list[float],
) -> float:
    if gap == 0:
        return (
            origin[node]
            + edges[node][route[0]]
            - origin[route[0]]
            + penalty[node]
            - penalty[route[0]]
        )
    before = route[gap - 1]
    delta = edges[before][node]
    if gap < len(route):
        after = route[gap]
        delta += edges[node][after] - edges[before][after]
    return delta


def _control_route(
    origin: list[float], edges: list[list[float]], penalty: list[float]
) -> list[int]:
    
    n = len(origin)
    first = min(range(n), key=lambda i: (origin[i] + penalty[i], i))
    route = [first]
    remaining = set(range(n))
    remaining.remove(first)
    nearest = [min(origin[i], edges[first][i]) for i in range(n)]
    while remaining:
        node = min(remaining, key=lambda i: (nearest[i], i))
        best_gap = 0
        best_delta = _insertion_delta(route, node, 0, origin, edges, penalty)
        for gap in range(1, len(route) + 1):
            delta = _insertion_delta(route, node, gap, origin, edges, penalty)
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
                old = (
                    origin[route[left]]
                    if left == 0
                    else edges[route[left - 1]][route[left]]
                )
                new = (
                    origin[route[right]]
                    if left == 0
                    else edges[route[left - 1]][route[right]]
                )
                if right + 1 < n:
                    old += edges[route[right]][route[right + 1]]
                    new += edges[route[left]][route[right + 1]]
                if left == 0:
                    old += penalty[route[left]]
                    new += penalty[route[right]]
                if new + 1e-12 * max(1.0, old, new) < old:
                    route[left : right + 1] = reversed(route[left : right + 1])
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    return route


def _cheapest_route(
    origin: list[float], edges: list[list[float]], penalty: list[float]
) -> list[int]:
    
    n = len(origin)
    first = min(range(n), key=lambda i: (origin[i] + penalty[i], i))
    route = [first]
    remaining = set(range(n))
    remaining.remove(first)
    while remaining:
        
        _, node, gap = min(
            (_insertion_delta(route, node, gap, origin, edges, penalty), node, gap)
            for node in remaining
            for gap in range(len(route) + 1)
        )
        route.insert(gap, node)
        remaining.remove(node)
    return route


def _nearest_route(first: int, edges: list[list[float]]) -> list[int]:
    remaining = set(range(len(edges)))
    remaining.remove(first)
    route = [first]
    while remaining:
        node = min(remaining, key=lambda i: (edges[route[-1]][i], i))
        route.append(node)
        remaining.remove(node)
    return route


def _improve(
    route: list[int],
    origin: list[float],
    edges: list[list[float]],
    penalty: list[float],
) -> tuple[list[int], float]:
    
    n = len(route)
    cost = _cost(route, origin, edges, penalty)
    for _ in range(min(n, 12)):
        
        
        best_delta = -1e-12 * max(1.0, cost)
        move: tuple[str, int, int] | None = None
        for left in range(n - 1):
            for right in range(left + 1, n):
                old = (
                    origin[route[left]]
                    if left == 0
                    else edges[route[left - 1]][route[left]]
                )
                new = (
                    origin[route[right]]
                    if left == 0
                    else edges[route[left - 1]][route[right]]
                )
                if right + 1 < n:
                    old += edges[route[right]][route[right + 1]]
                    new += edges[route[left]][route[right + 1]]
                if left == 0:
                    old += penalty[route[left]]
                    new += penalty[route[right]]
                delta = new - old
                if delta < best_delta:
                    best_delta, move = delta, ("reverse", left, right)

        for index, node in enumerate(route):
            if n == 1:
                break
            if index == 0:
                following = route[1]
                removal = (
                    origin[following]
                    + penalty[following]
                    - origin[node]
                    - penalty[node]
                    - edges[node][following]
                )
            else:
                before = route[index - 1]
                removal = -edges[before][node]
                if index + 1 < n:
                    following = route[index + 1]
                    removal += edges[before][following] - edges[node][following]
            
            
            for gap in range(n + 1):
                if gap == index or gap == index + 1:
                    continue
                delta = removal + _insertion_delta(
                    route, node, gap, origin, edges, penalty
                )
                if delta < best_delta:
                    best_delta, move = delta, ("relocate", index, gap)

        if move is None:
            break
        candidate = route.copy()
        kind, left, right = move
        if kind == "reverse":
            candidate[left : right + 1] = reversed(candidate[left : right + 1])
        else:
            node = candidate.pop(left)
            candidate.insert(right if right < left else right - 1, node)
        candidate_cost = _cost(candidate, origin, edges, penalty)
        if not candidate_cost < cost:
            
            break
        route, cost = candidate, candidate_cost
    return route, cost


def choose_portfolio_task(
    position: Point,
    anchors: dict[int, Point],
    targets: dict[int, tuple[Point, float]],
    risk_weight: float = 1.0,
) -> Task:
    
    target_keys = sorted(targets)
    anchor_keys = sorted(anchors)
    tasks: list[Task] = [("target", key) for key in target_keys]
    tasks.extend(("anchor", key) for key in anchor_keys)
    n = len(tasks)
    if not n:
        raise ValueError("cannot dispatch an empty task set")
    coords = [targets[key][0] for key in target_keys]
    coords.extend(anchors[key] for key in anchor_keys)
    radii = [targets[key][1] for key in target_keys]
    radii.extend(0.0 for _ in anchor_keys)
    if any(
        len(point) != 2 or not all(isfinite(x) for x in point)
        for point in [position, *coords]
    ):
        raise ValueError("positions must be finite two-dimensional points")
    if any(not isfinite(radius) or radius < 0 for radius in radii):
        raise ValueError("MEC radii must be finite and nonnegative")
    if not isfinite(risk_weight) or risk_weight < 0:
        raise ValueError("risk_weight must be finite and nonnegative")
    penalty = [risk_weight * radius for radius in radii]
    if any(not isfinite(value) for value in penalty):
        raise ValueError("weighted radii must be finite")
    origin = [dist(position, point) for point in coords]
    edges = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            edges[i][j] = edges[j][i] = dist(coords[i], coords[j])
    if any(not isfinite(value) for value in origin) or any(
        not isfinite(value) for row in edges for value in row
    ):
        raise ValueError("pairwise distances must be finite")
    
    
    try:
        bound = fsum((max(origin), max(penalty), *(max(row) for row in edges)))
    except OverflowError as error:
        raise ValueError("route proxy bound must be finite") from error
    if not isfinite(bound):
        raise ValueError("route proxy bound must be finite")

    control = _control_route(origin, edges, penalty)
    control_cost = _cost(control, origin, edges, penalty)
    best_route, best_cost = control, control_cost
    
    
    starts = sorted(range(n), key=lambda i: (origin[i] + penalty[i], i))[:2]
    seeds = [control, _cheapest_route(origin, edges, penalty)]
    seeds.extend(_nearest_route(first, edges) for first in starts)
    seen: set[tuple[int, ...]] = set()
    for seed in seeds:
        identity = tuple(seed)
        if identity in seen:
            continue
        seen.add(identity)
        route, cost = _improve(seed, origin, edges, penalty)
        if cost < best_cost:
            best_route, best_cost = route, cost
    
    if best_cost > control_cost:
        return tasks[control[0]]
    return tasks[best_route[0]]
