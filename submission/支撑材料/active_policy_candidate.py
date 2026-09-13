"""Unexecuted research candidate: observation-only, bounded active probing.

No action or belief update occurs here. ``None`` means use the unchanged
localizer/optical cover; a selected point is NOT a clearing certificate.
"""

from __future__ import annotations

from math import acos, cos, dist, hypot, isfinite, nextafter, pi, radians, sin

from submission.支撑材料.geometry import (
    BEARING_ERROR_DEG,
    MAX_RADIO_RADIUS,
    Point,
    _clip_halfplane,
    _padding,
    enclosing_circle,
)
from submission.支撑材料.second_point import safe_candidates


def _bearing_bound(polygon, point, radius, bins, error_deg):
    """Upper-bound every positive-bearing posterior using overlapping wedges.

    Each angular bin is enlarged by the measurement error; unlike clip_bearing,
    the scoring relaxation has NO projected range cap. A bounding-box circle
    encloses each relaxed polygon. The original MEC is also an enclosing disk.
    """
    half_bin = 180.0 / bins
    width = radians(error_deg + half_bin)
    scale = max(
        MAX_RADIO_RADIUS,
        abs(point[0]),
        abs(point[1]),
        *(max(abs(x), abs(y)) for x, y in polygon),
    )
    # A padded narrow wedge is a translated exact wedge. Its apex shift is
    # epsilon/sin(alpha); this larger pad also covers that displacement.
    padding = 4.0 * _padding(scale) / sin(radians(error_deg))
    worst, nonempty = 0.0, 0
    for index in range(bins):
        angle = 2.0 * pi * index / bins
        low, high = angle - width, angle + width
        outer = _clip_halfplane(
            polygon, point, (sin(low), -cos(low)), 0.0, padding
        )
        outer = _clip_halfplane(
            outer, point, (-sin(high), cos(high)), 0.0, padding
        )
        if not outer:
            continue
        nonempty += 1
        xmin = min(p[0] for p in outer)
        xmax = max(p[0] for p in outer)
        ymin = min(p[1] for p in outer)
        ymax = max(p[1] for p in outer)
        box_radius = nextafter(
            0.5 * hypot(xmax - xmin, ymax - ymin) + padding, float("inf")
        )
        worst = max(worst, min(radius, box_radius))
    # An unexpected empty partition must not look like perfect information.
    return (worst if nonempty else radius), nonempty


def _loss_risk(samples, readings, point, problem):
    """Geometric risk index, NOT an identified no-signal probability."""
    total = 0.0
    station = readings[-1][0]
    for source in samples:
        query_distance = dist(point, source)
        # A positive station implies range >= its distance, even in Q4.
        lower_range = max(1000.0, *(dist(s, source) for s, _ in readings))
        if query_distance > lower_range:
            total += 1.0
            continue
        if problem == 3:
            continue
        old_distance = dist(station, source)
        if old_distance <= 1e-9 or query_distance <= 1e-9:
            # Direction is undefined here; do not manufacture guaranteed signal.
            total += 1.0
            continue
        cosine = sum(
            (station[i] - source[i]) * (point[i] - source[i]) for i in (0, 1)
        ) / (old_distance * query_distance)
        total += acos(max(-1.0, min(1.0, cosine))) / pi
    return total / len(samples)


def score_probes(
    polygon,
    readings,
    current_position,
    problem,
    *,
    probes_remaining=1,
    rejected_points=(),
    bearing_bins=72,
    error_deg=BEARING_ERROR_DEG,
    probe_scale=0.22,
    movement_weight=0.15,
    loss_weight=1.0,
    include_lens=True,
):
    """Return a deterministic score table; consume only public observations.

    polygon: nonempty ordered convex conservative vertices, as Track.polygon.
    readings: positive (station, svd_deg) pairs for ONE known channel only.
    rejected_points: previous unsuccessful probes/clears; excludes locations,
        never source hypotheses. The caller retains all underlying history.
    probes_remaining: caller-owned remaining bound; this function cannot debit it.

    Legal coordinates are finite and within +/-2,000,000 m per protocol, NOT
    restricted to the radius-1800 source arena. Scores are dimensionless.
    Empty output signals fallback. Malformed/contradictory inputs raise, rather
    than resetting a belief or silently substituting a made-up polygon.
    """
    if problem not in (3, 4):
        raise ValueError("Only Q3 and Q4 localization is supported")
    if not isinstance(probes_remaining, int) or probes_remaining < 0:
        raise ValueError("probes_remaining must be a nonnegative integer")
    if not isinstance(bearing_bins, int) or bearing_bins < 4:
        raise ValueError("bearing_bins must be an integer >= 4")
    if not isfinite(error_deg) or not BEARING_ERROR_DEG <= error_deg < 90:
        raise ValueError("error_deg must include the public rounding allowance")
    if error_deg + 180.0 / bearing_bins >= 90.0:
        raise ValueError("Expanded bearing bins must be narrower than 180 degrees")
    if not isfinite(probe_scale) or not 0 < probe_scale <= 1:
        raise ValueError("probe_scale must lie in (0, 1]")
    if any(not isfinite(w) or w < 0 for w in (movement_weight, loss_weight)):
        raise ValueError("Score weights must be finite and nonnegative")
    poly = [tuple(p) for p in polygon]
    history = [(tuple(s), float(a)) for s, a in readings]
    position = tuple(current_position)
    rejected = [tuple(p) for p in rejected_points]
    points = poly + [position] + rejected + [s for s, _ in history]
    if any(len(p) != 2 or not all(isfinite(v) for v in p) for p in points):
        raise ValueError("All points must contain two finite coordinates")
    if any(not isfinite(a) for _, a in history):
        raise ValueError("Readings must have finite public bearing angles")
    center, radius = enclosing_circle(poly)  # Empty belief must raise.
    if not history or probes_remaining == 0 or radius <= 19.9:
        return []

    station, bearing = history[-1]
    dx, dy = center[0] - station[0], center[1] - station[1]
    length = hypot(dx, dy)
    axis = (dx / length, dy / length) if length > 1e-8 else (
        cos(radians(bearing)), sin(radians(bearing))
    )
    normal = (-axis[1], axis[0])
    offset = min(120.0, max(25.0, probe_scale * radius))
    candidates = [("mec_center", center), ("positive_station", station)]
    for name, direction in (("normal", normal), ("axis", axis)):
        for sign in (-1, 1):
            candidates.append((
                f"mec_{name}_{sign:+d}",
                tuple(center[i] + sign * offset * direction[i] for i in (0, 1)),
            ))
    if include_lens:
        candidates.extend(
            (f"q2_lens_{index}", tuple(row["point"]))
            for index, row in enumerate(safe_candidates(station, bearing, error_deg))
        )

    samples = list(dict.fromkeys(poly + [center]))
    exclusions = [s for s, _ in history] + rejected
    table, seen = [], set()
    for label, point in candidates:
        if point in seen:
            continue
        seen.add(point)
        reason = None
        if any(not isfinite(v) or abs(v) > 2_000_000 for v in point):
            reason = "outside_protocol_coordinates"
        elif any(dist(point, old) <= 0.5 for old in exclusions):
            reason = "previous_observation_or_rejected_location"
        row = {
            "candidate": label,
            "point": point,
            "eligible": reason is None,
            "rejection": reason,
            "score": None,
        }
        if reason is None:
            bound, bins_used = _bearing_bound(
                poly, point, radius, bearing_bins, error_deg
            )
            movement = dist(position, point)
            risk = _loss_risk(samples, history, point, problem)
            row.update({
                "prior_mec_radius_m": radius,
                "positive_bearing_radius_upper_m": bound,
                "movement_m": movement,
                "no_signal_risk_index": risk,
                "radius_term": bound / radius,
                "movement_term": movement_weight * movement / 1000.0,
                "loss_term": loss_weight * risk,
                "worst_including_uninformative_no_signal_m": radius,
                "nonempty_bearing_bins": bins_used,
                "bearing_bins": bearing_bins,
                "error_deg": error_deg,
                "risk_samples": len(samples),
                "score": (
                    bound / radius
                    + movement_weight * movement / 1000.0
                    + loss_weight * risk
                ),
            })
        table.append(row)
    return table


def choose_probe(
    polygon, readings, current_position, problem, **options
) -> Point | None:
    """Choose minimum score, then minimum travel, then generation-order tie.

    The caller MUST debit its existing finite probe budget, apply only actual
    positive bearings via Planner.measure, and retain the original fallback.
    Use score_probes with identical arguments to obtain the full score table.
    """
    table = score_probes(polygon, readings, current_position, problem, **options)
    eligible = [row for row in table if row["eligible"]]
    if not eligible:
        return None
    best = min(eligible, key=lambda row: (row["score"], row["movement_m"]))
    return best["point"]
