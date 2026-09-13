

from __future__ import annotations

from decimal import Decimal, localcontext
from math import ceil, cos, hypot, isfinite, nextafter, pi, radians, sin, sqrt, ulp
from random import Random

Point = tuple[float, float]
Circle = tuple[Point, float]
ARENA_RADIUS = 1800.0
MAX_RADIO_RADIUS = 1500.0
BEARING_ERROR_DEG = 1.005


def _check_points(points: list[Point]) -> None:
    if any(not (isfinite(x) and isfinite(y)) for x, y in points):
        raise ValueError("Geometry requires finite coordinates")


def _padding(scale: float) -> float:
    return max(1e-9, 64.0 * ulp(max(1.0, scale)))


def initial_polygon(sides: int = 180) -> list[Point]:
    
    if isinstance(sides, bool) or not isinstance(sides, int) or sides < 3:
        raise ValueError("sides must be an integer at least three")
    radius = (ARENA_RADIUS + _padding(ARENA_RADIUS)) / cos(pi / sides)
    return [
        (radius * cos(2 * pi * i / sides), radius * sin(2 * pi * i / sides))
        for i in range(sides)
    ]


def _clip_halfplane(
    poly: list[Point], origin: Point, normal: Point, bound: float, padding: float
) -> list[Point]:
    
    if not poly:
        return []
    nx, ny = normal
    ox, oy = origin
    limit = bound + padding
    result: list[Point] = []
    previous = poly[-1]
    dp = nx * (previous[0] - ox) + ny * (previous[1] - oy) - limit
    for current in poly:
        dc = nx * (current[0] - ox) + ny * (current[1] - oy) - limit
        if (dp <= 0.0) != (dc <= 0.0):
            
            
            if abs(dp) <= abs(dc):
                t = dp / (dp - dc)
                crossing = (
                    previous[0] + t * (current[0] - previous[0]),
                    previous[1] + t * (current[1] - previous[1]),
                )
            else:
                t = dc / (dc - dp)
                crossing = (
                    current[0] + t * (previous[0] - current[0]),
                    current[1] + t * (previous[1] - current[1]),
                )
            if not result or crossing != result[-1]:
                result.append(crossing)
        if dc <= 0.0 and (not result or current != result[-1]):
            result.append(current)
        previous, dp = current, dc
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def clip_bearing(
    poly: list[Point],
    point: Point,
    bearing_deg: float,
    error_deg: float = BEARING_ERROR_DEG,
) -> list[Point]:
    
    _check_points(poly)
    _check_points([point])
    if not isfinite(bearing_deg) or not isfinite(error_deg) or not 0 <= error_deg < 90:
        raise ValueError("Use finite bearing and 0 <= error_deg < 90")
    if not poly:
        return []
    theta = radians(bearing_deg % 360.0)
    error = radians(error_deg)
    low, high = theta - error, theta + error
    scale = max(
        MAX_RADIO_RADIUS,
        abs(point[0]),
        abs(point[1]),
        *(max(abs(x), abs(y)) for x, y in poly),
    )
    padding = _padding(scale)
    
    result = _clip_halfplane(poly, point, (sin(low), -cos(low)), 0.0, padding)
    result = _clip_halfplane(result, point, (-sin(high), cos(high)), 0.0, padding)
    result = _clip_halfplane(result, point, (-cos(theta), -sin(theta)), 0.0, padding)
    return _clip_halfplane(
        result, point, (cos(theta), sin(theta)), MAX_RADIO_RADIUS, padding
    )


def _farthest_pair(poly: list[Point]) -> tuple[Point, Point, float]:
    first = second = poly[0]
    distance = 0.0
    for i, a in enumerate(poly):
        for j in range(i):
            b = poly[j]
            candidate = hypot(a[0] - b[0], a[1] - b[1])
            if candidate > distance:
                first, second, distance = a, b, candidate
    return first, second, distance


def diameter(poly: list[Point]) -> float:
    
    _check_points(poly)
    if not poly:
        raise ValueError("An infeasible region has no localization diameter")
    return _farthest_pair(poly)[2]


def _pair_circle(a: Point, b: Point) -> Circle:
    center = (a[0] + (b[0] - a[0]) / 2, a[1] + (b[1] - a[1]) / 2)
    return center, max(hypot(center[0] - p[0], center[1] - p[1]) for p in (a, b))


def _cross(a: Point, b: Point, c: Point) -> float:
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    determinant = bx * cy - by * cx
    scale = max(abs(bx), abs(by), abs(cx), abs(cy))
    if abs(determinant) > 64 * ulp(max(1.0, scale * scale)):
        return determinant
    with localcontext() as context:
        context.prec = 80
        ax, ay = Decimal(a[0]), Decimal(a[1])
        return float(
            (Decimal(b[0]) - ax) * (Decimal(c[1]) - ay)
            - (Decimal(b[1]) - ay) * (Decimal(c[0]) - ax)
        )


def _circumcircle(a: Point, b: Point, c: Point) -> Circle | None:
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    determinant = bx * cy - by * cx
    scale = max(abs(bx), abs(by), abs(cx), abs(cy))
    if abs(determinant) <= 64 * ulp(max(1.0, scale * scale)):
        
        
        with localcontext() as context:
            context.prec = 80
            axd, ayd = Decimal(a[0]), Decimal(a[1])
            bxd, byd = Decimal(b[0]) - axd, Decimal(b[1]) - ayd
            cxd, cyd = Decimal(c[0]) - axd, Decimal(c[1]) - ayd
            det = 2 * (bxd * cyd - byd * cxd)
            if not det:
                return None
            bb, cc = bxd * bxd + byd * byd, cxd * cxd + cyd * cyd
            center = (
                float(axd + (cyd * bb - byd * cc) / det),
                float(ayd + (bxd * cc - cxd * bb) / det),
            )
    else:
        bb, cc = bx * bx + by * by, cx * cx + cy * cy
        center = (
            a[0] + (cy * bb - by * cc) / (2 * determinant),
            a[1] + (bx * cc - cx * bb) / (2 * determinant),
        )
    return center, max(hypot(center[0] - p[0], center[1] - p[1]) for p in (a, b, c))


def _contains(circle: Circle, point: Point) -> bool:
    center, radius = circle
    return hypot(point[0] - center[0], point[1] - center[1]) <= nextafter(
        radius, float("inf")
    )


def _two_boundary_circle(points: list[Point], end: int, a: Point, b: Point) -> Circle:
    base = _pair_circle(a, b)
    left: Circle | None = None
    right: Circle | None = None
    left_cross = right_cross = 0.0
    for i in range(end):
        p = points[i]
        if _contains(base, p):
            continue
        side = _cross(a, b, p)
        candidate = _circumcircle(a, b, p)
        if candidate is None:
            continue
        center_side = _cross(a, b, candidate[0])
        if side > 0 and (left is None or center_side > left_cross):
            left, left_cross = candidate, center_side
        elif side < 0 and (right is None or center_side < right_cross):
            right, right_cross = candidate, center_side
    if left is None:
        return base if right is None else right
    if right is None:
        return left
    return left if left[1] <= right[1] else right


def enclosing_circle(poly: list[Point]) -> Circle:
    
    _check_points(poly)
    if not poly:
        raise ValueError("An infeasible region has no enclosing-circle center")
    points = list(dict.fromkeys(poly))
    Random(0).shuffle(points)
    circle: Circle | None = None
    for i, p in enumerate(points):
        if circle is not None and _contains(circle, p):
            continue
        circle = (p, 0.0)
        for j in range(i):
            q = points[j]
            if _contains(circle, q):
                continue
            if circle[1] == 0.0:
                circle = _pair_circle(p, q)
            else:
                circle = _two_boundary_circle(points, j + 1, p, q)
    assert circle is not None
    center = circle[0]
    radius = max(hypot(p[0] - center[0], p[1] - center[1]) for p in points)
    if radius == 0.0:
        return center, 0.0
    scale = max(radius, abs(center[0]), abs(center[1]))
    return center, nextafter(radius + _padding(scale), float("inf"))


def optical_cover(poly: list[Point], radius: float = 19.9) -> list[Point]:
    
    _check_points(poly)
    if not isfinite(radius) or radius <= 0:
        raise ValueError("Optical covering radius must be finite and positive")
    if not poly:
        return []
    center, enclosing_radius = enclosing_circle(poly)
    if enclosing_radius <= radius:
        return [center]
    a, b, distance = _farthest_pair(poly)
    if distance == 0.0:
        return [a]
    ux, uy = (b[0] - a[0]) / distance, (b[1] - a[1]) / distance
    
    norm = hypot(ux, uy)
    ux, uy = ux / norm, uy / norm
    projected = [
        ((x - a[0]) * ux + (y - a[1]) * uy, -(x - a[0]) * uy + (y - a[1]) * ux)
        for x, y in poly
    ]
    scale = max(distance, *(max(abs(x), abs(y)) for x, y in poly))
    guard = _padding(scale)
    safe_radius = radius - 8 * guard
    if safe_radius <= 0:
        raise ValueError(
            "Radius is below floating-point resolution at these coordinates"
        )
    xmin, xmax = (
        min(p[0] for p in projected) - guard,
        max(p[0] for p in projected) + guard,
    )
    ymin, ymax = (
        min(p[1] for p in projected) - guard,
        max(p[1] for p in projected) + guard,
    )
    side = sqrt(2.0) * safe_radius
    nx = max(1, ceil((xmax - xmin) / side))
    ny = max(1, ceil((ymax - ymin) / side))
    dx, dy = (xmax - xmin) / nx, (ymax - ymin) / ny
    centers: list[Point] = []
    for j in range(ny):
        y = ymin + (j + 0.5) * dy
        indices = range(nx) if j % 2 == 0 else range(nx - 1, -1, -1)
        for i in indices:
            x = xmin + (i + 0.5) * dx
            centers.append((a[0] + x * ux - y * uy, a[1] + x * uy + y * ux))
    return centers
