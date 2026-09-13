"""Finite, analytically justified discovery waypoint sets for CUMCM B Q3/Q4.

These functions prescribe measurement locations, not a route or a stopping rule.
Every unresolved channel needs its own completed coverage record.  In particular,
Q4 waypoints outside the source arena must not be projected back into the arena.
"""

from __future__ import annotations

import math

Point = tuple[float, float]

ARENA_RADIUS = 1800.0
MIN_RADIO_RADIUS = 1000.0
OMNI_COVER_RADIUS = 900.0
DEFAULT_SPACING = 990.0


def omni_waypoints(ring_radius: float | None = None) -> list[Point]:
    """Return origin plus six ring points; the legacy radius certifies 900 m.

    The 1200-m contracted ring instead has exact cover radius given by
    ring_cover_radius, still below the guaranteed 1000-m reception distance.
    No unspecified source-position prior is used by this geometric guarantee.
    """
    ring_radius = OMNI_COVER_RADIUS * math.sqrt(3.0) if ring_radius is None else float(ring_radius)
    if not math.isfinite(ring_radius) or not 1200.0 <= ring_radius <= OMNI_COVER_RADIUS * math.sqrt(3.0):
        raise ValueError("Supported ring radius is [1200, 900*sqrt(3)] m")
    return [(0.0, 0.0)] + [
        (
            ring_radius * math.cos(k * math.pi / 3.0),
            ring_radius * math.sin(k * math.pi / 3.0),
        )
        for k in range(6)
    ]


def ring_cover_radius(ring_radius: float) -> float:
    """Exact covering radius of origin plus six equally spaced ring points."""
    omni_waypoints(ring_radius)
    return max(ring_radius / math.sqrt(3.0),
               math.sqrt(ARENA_RADIUS**2 + ring_radius**2
                         - math.sqrt(3.0) * ARENA_RADIUS * ring_radius))


def directional_waypoints(spacing: float = DEFAULT_SPACING) -> list[Point]:
    """Return a finite triangular lattice with a full source-domain guard.

    For a source g inside the arena, the elementary triangle containing g has
    vertices within spacing of g and norm <= ARENA_RADIUS + spacing.
    If g is a lattice vertex, all six nearest neighbours satisfy that same
    norm bound, so every emission direction has a nonzero forward neighbour.
    No such six-neighbour claim is made for vertices outside the source arena.
    Support 900 <= spacing <= 999; ordering is origin then row and column.
    """
    spacing = float(spacing)
    if not math.isfinite(spacing) or not 900.0 <= spacing <= MIN_RADIO_RADIUS - 1.0:
        raise ValueError("spacing must be finite and in [900, 999] m")

    # With a=(s,0), b=(s/2,s*sqrt(3)/2), the squared norm of i*a+j*b
    # is s*s*(i*i+i*j+j*j).  Compare the radial cutoff using integers, so
    # floating-point rounding cannot accidentally remove a boundary vertex.
    numerator, denominator = spacing.as_integer_ratio()
    guard_numerator = 1800 * denominator + numerator
    numerator_squared = numerator * numerator
    guard_squared = guard_numerator * guard_numerator
    # q=i*i+i*j+j*j >= 3*i*i/4 and >= 3*j*j/4.  The simpler bound
    # |i|,|j| <= ceil(2*(1800+s)/s) safely contains the radial selection.
    bound = (2 * guard_numerator + numerator - 1) // numerator
    row_height = spacing * math.sqrt(3.0) / 2.0
    points: list[Point] = [(0.0, 0.0)]
    for j in range(-bound, bound + 1):
        for i in range(-bound, bound + 1):
            if i == 0 and j == 0:
                continue
            norm_squared_units = i * i + i * j + j * j
            if norm_squared_units * numerator_squared <= guard_squared:
                points.append((spacing * (i + j / 2.0), row_height * j))
    return points


def coverage_certificate() -> dict:
    """Return analytic constants/counts, not a sampled or experimental result.

    Counts describe the default 990 m lattice.  Norm shells are exact integer
    values of i*i+i*j+j*j; their multiplicities can be checked independently.
    No simulator actions, numerical coverage sampling, or routing occur here.
    """
    return {
        "certificate_kind": "analytic_geometric_cover",
        "arena_radius_m": ARENA_RADIUS,
        "minimum_radio_radius_m": MIN_RADIO_RADIUS,
        "channels": 20,
        "omni_legacy": {
            "waypoint_count": 7,
            "ring_radius_m": OMNI_COVER_RADIUS * math.sqrt(3.0),
            "cover_radius_m": OMNI_COVER_RADIUS,
            "radio_slack_m": MIN_RADIO_RADIUS - OMNI_COVER_RADIUS,
            "proof": (
                "r<=900 is covered by the origin. For 900<=r<=1800, "
                "choose a ring center with angular gap <=pi/6. Then "
                "distance^2<=r^2-2700*r+2430000<=810000 by convexity "
                "and equality of the two endpoint values."
            ),
        },
        "omni_enhanced": {
            "waypoint_count": 7,
            "ring_radius_m": 1200.0,
            "cover_radius_m": ring_cover_radius(1200.0),
            "radio_slack_m": MIN_RADIO_RADIUS - ring_cover_radius(1200.0),
            "proof": "Exact envelope formula ring_cover_radius(1200); no point or channel obligation is removed.",
        },
        "omni": {
            "waypoint_count": 7,
            "ring_radius_m": OMNI_COVER_RADIUS * math.sqrt(3.0),
            "cover_radius_m": OMNI_COVER_RADIUS,
            "radio_slack_m": MIN_RADIO_RADIUS - OMNI_COVER_RADIUS,
            "proof": "Legacy 900m certificate; enhanced 1200m certificate is in omni_enhanced.",
        },
        "directional": {
            "spacing_m": DEFAULT_SPACING,
            "basis_m": [
                [DEFAULT_SPACING, 0.0],
                [DEFAULT_SPACING / 2.0, DEFAULT_SPACING * math.sqrt(3.0) / 2.0],
            ],
            "selection_radius_m": ARENA_RADIUS + DEFAULT_SPACING,
            "maximum_source_vertex_distance_m": DEFAULT_SPACING,
            "radio_slack_m": MIN_RADIO_RADIUS - DEFAULT_SPACING,
            "waypoint_count": 31,
            "inside_or_on_arena_count": 13,
            "outside_arena_count": 18,
            "norm_squared_units_counts": {0: 1, 1: 6, 3: 6, 4: 6, 7: 12},
            "maximum_waypoint_radius_m": DEFAULT_SPACING * math.sqrt(7.0),
            "closed_halfplane_required": True,
            "boundary_guard_required": True,
            "proof": (
                "An elementary triangular-lattice triangle containing g has "
                "three vertices within spacing of g. Their norms are at most "
                "1800+spacing, hence all are selected. Write "
                "g=sum(lambda_i*v_i), lambda_i>=0, sum(lambda_i)=1. "
                "For any emission normal n, sum(lambda_i*n dot (v_i-g))=0, "
                "so at least one vertex is in the closed emission halfplane. "
                "If g is a lattice vertex inside the source arena, all six "
                "nearest neighbors have norm <=1800+spacing and are selected; "
                "one makes angle <=pi/6 with any emission normal."
            ),
            "count_proof": (
                "At spacing 990 the cutoff is i^2+i*j+j^2<=961/121. "
                "The possible shells are 0,1,3,4,7 with multiplicities "
                "1,6,6,6,12. The arena cutoff is 400/121, leaving shells "
                "0,1,3 inside and shells 4,7 outside."
            ),
        },
        "termination": (
            "For each of 20 channels, retain either a confirmed successful "
            "clear or a complete all-no_signal covering scan for that channel. "
            "A detected but uncleared channel remains unresolved. With at "
            "most one source per channel, all 20 certificates imply no "
            "remaining source. Independently, 16 distinct confirmed clears "
            "reach the stated global upper bound. Fewer clears alone do not."
        ),
        "no_signal": {
            "q3": "Excludes every source at distance <=1000 from that detector.",
            "q4": (
                "Does not exclude that disk: a source may emit away from the "
                "detector. Only the completed per-channel halfplane cover "
                "excludes every source position and orientation."
            ),
        },
        "assumptions": [
            "Sources are stationary, persist until cleared, and use distinct channels.",
            "Directional emission is a closed 180-degree halfplane with fixed orientation.",
            "Reception reaches at least 1000 m throughout the emission halfplane.",
            "All designated measurements actually complete on the indicated channel.",
            "Near-source responses count as detections, not as no_signal.",
            "Robot coordinates outside the radius-1800 source arena are permitted.",
            "Geometric proofs use exact real coordinates; default float coordinates have 10 m range slack.",
        ],
    }
