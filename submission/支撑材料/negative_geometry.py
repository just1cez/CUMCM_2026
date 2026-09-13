

from __future__ import annotations

from math import cos, isfinite, pi, sin

from submission.支撑材料.geometry import Point, _clip_halfplane, _cross, _padding


def _hull(points: list[Point]) -> list[Point]:
    
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def exclude_omni_disk(
    poly: list[Point], station: Point, radius: float = 1000.0, *, sides: int = 16
) -> list[Point]:
    
    if sides not in (16, 32):
        raise ValueError("sides must be 16 or 32")
    if len(station) != 2 or not all(isfinite(v) for v in station):
        raise ValueError("station must have finite coordinates")
    if not isfinite(radius) or radius <= 0.0:
        raise ValueError("radius must be a positive finite number")
    if not poly:
        return []
    if any(len(p) != 2 or not all(isfinite(v) for v in p) for p in poly):
        raise ValueError("polygon requires finite coordinates")
    scale = max(1.0, radius, *(abs(v) for p in poly for v in p), *map(abs, station))
    if not isfinite(16.0 * scale * scale):
        raise ValueError("Geometry scale exceeds finite half-plane arithmetic")

    
    
    qradius = radius * cos(pi / sides)
    cx, cy = station
    q = [
        (
            cx + qradius * cos(2.0 * pi * i / sides),
            cy + qradius * sin(2.0 * pi * i / sides),
        )
        for i in range(sides)
    ]
    pad = _padding(scale)
    pieces: list[Point] = []

    
    
    for i, a in enumerate(q):
        b = q[(i + 1) % sides]
        ex, ey = b[0] - a[0], b[1] - a[1]
        normal = (ey, -ex)  
        bound = 0.0
        
        if all(
            normal[0] * (x - a[0]) + normal[1] * (y - a[1]) >= -pad for x, y in poly
        ):
            return list(poly)
        part = _clip_halfplane(poly, a, (-normal[0], -normal[1]), -bound, pad)
        pieces.extend(part)
    if not pieces:
        return []
    return _hull(pieces)
