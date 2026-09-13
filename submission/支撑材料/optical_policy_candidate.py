"""Deterministic, whole-region optical-cover candidate for convex polygons.

The existing geometry.optical_cover remains the explicit fallback/control.
Only public feasible-region vertices are used. No actions or state are mutated.
"""

from __future__ import annotations

from fractions import Fraction
from math import ceil, dist, hypot, isfinite, sqrt, ulp

from submission.支撑材料.geometry import _farthest_pair, optical_cover

Point = tuple[float, float]
_ExactPoint = tuple[Fraction, Fraction]


def _cycle_length(points: list[Point]) -> float:
    return sum(dist(points[i - 1], point) for i, point in enumerate(points))


def _strip_bounds(
    vertices: list[_ExactPoint],
    edges: list[tuple[Fraction, Fraction, Fraction, Fraction]],
    left: Fraction,
    right: Fraction,
) -> tuple[Fraction, Fraction] | None:
    """Exact transverse extrema of polygon intersected with a closed slab."""
    values = [y for x, y in vertices if left <= x <= right]
    # Edge tuple: left endpoint x/y, right endpoint x, exact dy/dx.
    # Vertical edges need no intersections: their endpoints are already above.
    for x, y, end, slope in edges:
        if x <= left <= end:
            values.append(y + (left - x) * slope)
        if x <= right <= end:
            values.append(y + (right - x) * slope)
    if not values:
        return None
    return min(values), max(values)


def _certified_center(
    left: Fraction,
    right: Fraction,
    bottom: Fraction,
    top: Fraction,
    origin: _ExactPoint,
    axis: _ExactPoint,
    radius_squared: Fraction,
) -> Point | None:
    """Certify the actual returned float center against four exact corners."""
    ox, oy = origin
    ux, uy = axis
    x, y = (left + right) / 2, (bottom + top) / 2
    center = (float(ox + x * ux - y * uy), float(oy + x * uy + y * ux))
    if not all(isfinite(value) for value in center):
        return None
    cx, cy = Fraction(center[0]), Fraction(center[1])
    for x in (left, right):
        for y in (bottom, top):
            dx = ox + x * ux - y * uy - cx
            dy = oy + x * uy + y * ux - cy
            if dx * dx + dy * dy > radius_squared:
                return None
    return center


def certified_optical_cover(poly: list[Point], radius: float = 19.9) -> list[Point]:
    """Cover the entire convex region using certified, locally trimmed slabs.

    Accepts either winding, repeated vertices, points and line segments. Empty
    input raises ValueError (the legacy planner also treats it as infeasible).
    Output centers may lie outside the polygon/arena, as with optical_cover.

    Every new cell has an exact rational four-corner disk certificate for the
    returned float center. Any unsuccessful candidate is discarded in full;
    the existing cover is the safe fallback. Selection never increases cover
    count or cyclic travel relative to that control, but entry travel depends
    on the caller's position and is not covered by that comparison.
    """
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Optical covering radius must be finite and positive")
    if not poly:
        raise ValueError("An infeasible region has no optical cover")
    if any(not (isfinite(x) and isfinite(y)) for x, y in poly):
        raise ValueError("Geometry requires finite coordinates")

    control = optical_cover(poly, radius)
    if len(control) <= 1:
        return control
    origin_float, end, diameter = _farthest_pair(poly)
    if not isfinite(diameter) or diameter == 0:
        return control
    ux = (end[0] - origin_float[0]) / diameter
    uy = (end[1] - origin_float[1]) / diameter
    norm = hypot(ux, uy)
    if not isfinite(norm) or norm == 0:
        return control
    axis = Fraction(ux / norm), Fraction(uy / norm)
    origin = Fraction(origin_float[0]), Fraction(origin_float[1])
    norm_squared = axis[0] ** 2 + axis[1] ** 2
    metric_scale = sqrt(float(norm_squared))
    # Treat the float axis as exact, not as an exactly unit vector. This exact
    # inverse and the corner check remove reliance on rounded orthogonality.
    vertices = []
    for px, py in poly:
        dx, dy = Fraction(px) - origin[0], Fraction(py) - origin[1]
        vertices.append(
            ((dx * axis[0] + dy * axis[1]) / norm_squared,
             (-dx * axis[1] + dy * axis[0]) / norm_squared)
        )
    edges = []
    for index, a in enumerate(vertices):
        b = vertices[index - 1]
        if a[0] == b[0]:
            continue
        if a[0] > b[0]:
            a, b = b, a
        edges.append((a[0], a[1], b[0], (b[1] - a[1]) / (b[0] - a[0])))
    xmin = min(x for x, _ in vertices)
    xmax = max(x for x, _ in vertices)
    span = xmax - xmin
    height = float(max(y for _, y in vertices) - min(y for _, y in vertices))
    scale = max(diameter, *(max(abs(x), abs(y)) for x, y in poly))
    guard = max(1e-9, 64.0 * ulp(max(1.0, scale)))
    safe_radius = radius - 8.0 * guard
    if safe_radius <= 0 or not isfinite(height):
        return control
    local_radius = safe_radius / metric_scale
    # Square-ish slabs serve broad regions; elongated slabs serve narrow ones.
    widths = [sqrt(2.0) * local_radius, sqrt(3.0) * local_radius, local_radius]
    if height < 2.0 * local_radius:
        widths.append(2.0 * sqrt((local_radius - height / 2.0)
                                 * (local_radius + height / 2.0)))
    radius_squared = Fraction(radius) ** 2
    control_cycle = _cycle_length(control)
    best = control
    best_cost = 3.0 * len(control) + control_cycle / 5.0
    tried_counts: set[int] = set()
    for width in widths:
        if width <= 0 or not isfinite(width):
            continue
        count = max(1, ceil(span / Fraction(width)))
        if count in tried_counts or count > len(control):
            continue
        tried_counts.add(count)
        slab_width = span / count
        half_width = float(slab_width) / 2.0
        if half_width >= local_radius:
            continue
        capacity = 2.0 * sqrt((local_radius - half_width)
                              * (local_radius + half_width))
        if capacity <= 0 or not isfinite(capacity):
            continue
        candidate: list[Point] = []
        valid = True
        for index in range(count):
            left = xmin + index * slab_width
            right = xmin + (index + 1) * slab_width
            bounds = _strip_bounds(vertices, edges, left, right)
            if bounds is None:
                # For a nonempty convex polygon every slab across its x-span
                # intersects it. Do not silently skip an unexplained hole.
                valid = False
                break
            bottom, top = bounds
            rows = max(1, ceil((top - bottom) / Fraction(capacity)))
            if len(candidate) + rows > len(control):
                valid = False
                break
            step = (top - bottom) / rows
            indices = range(rows) if index % 2 == 0 else range(rows - 1, -1, -1)
            for row in indices:
                point = _certified_center(
                    left, right, bottom + row * step, bottom + (row + 1) * step,
                    origin, axis, radius_squared,
                )
                if point is None:
                    valid = False
                    break
                candidate.append(point)
            if not valid:
                break
        if not valid:
            continue
        cycle = _cycle_length(candidate)
        cost = 3.0 * len(candidate) + cycle / 5.0
        if cycle <= control_cycle and cost < best_cost:
            best, best_cost = candidate, cost
    return best
