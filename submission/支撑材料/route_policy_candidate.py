"""Deterministic routing and task-priority candidates.

These helpers are deliberately separate from :mod:`planner`: they can improve
travel order without changing the certified waypoint set or its discovery
obligations.  No simulator/source-truth state is read here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real


def _point(value: object) -> tuple[float, float] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        return None
    x, y = value
    if not isinstance(x, Real) or not isinstance(y, Real):
        return None
    x, y = float(x), float(y)
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def optimize_waypoints(points: Sequence[object], start: tuple[float, float] = (0.0, 0.0)) -> list[int]:
    """Return a deterministic nearest-neighbour + 2-opt index order.

    Every valid input point occurs exactly once.  Invalid point data, or an
    invalid start, uses the exact identity order as a safe, obligation-
    preserving fallback; it never silently removes or fabricates a waypoint.
    The 2-opt pass only reverses contiguous order segments, so it changes
    travel length but cannot change the waypoint certificate.
    """
    try:
        n = len(points)
    except (TypeError, AttributeError):
        return []
    fallback = list(range(n))
    origin = _point(start)
    if origin is None:
        return fallback
    coords = [_point(p) for p in points]
    if any(p is None for p in coords):
        return fallback
    xy = [p for p in coords if p is not None]
    remaining = set(range(n))
    route: list[int] = []
    current = origin
    while remaining:
        index = min(remaining, key=lambda i: ((xy[i][0] - current[0]) ** 2 + (xy[i][1] - current[1]) ** 2, i))
        route.append(index)
        remaining.remove(index)
        current = xy[index]

    def edge(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # First-improvement, lexicographically scanned, strict 2-opt is stable.
    # Repeat until no improving exchange remains.
    changed = True
    while changed:
        changed = False
        for i in range(-1, n - 2):  # edge from start (i=-1) or route[i]
            a = origin if i == -1 else xy[route[i]]
            ai = i + 1
            for j in range(ai + 1, n):
                b = xy[route[ai]]
                c = xy[route[j]]
                d = xy[route[j + 1]] if j + 1 < n else None
                old = edge(a, b) + (edge(c, d) if d is not None else 0.0)
                new = edge(a, c) + (edge(b, d) if d is not None else 0.0)
                if new + 1e-12 < old:
                    route[ai : j + 1] = reversed(route[ai : j + 1])
                    changed = True
                    break
            if changed:
                break
    return route

