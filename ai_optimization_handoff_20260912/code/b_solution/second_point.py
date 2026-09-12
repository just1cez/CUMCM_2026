"""Q2 robust reception lens and explicitly sampled min-max geometry scoring."""

from __future__ import annotations

import json
import math
from pathlib import Path

from geometry import clip_bearing, enclosing_circle, initial_polygon


def safe_candidates(station=(0.0, 0.0), bearing_deg=0.0, alpha_deg=1.005):
    alpha, angle = math.radians(alpha_deg), math.radians(bearing_deg)
    u, n = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    choices = []
    for t in (125.0, 250.0, 375.0, 500.0, 625.0, 750.0, 875.0):
        bound = min(
            math.sqrt(1000**2 - t * t),
            math.sqrt(1000**2 - (t - 1000 * math.cos(alpha)) ** 2)
            - 1000 * math.sin(alpha),
        )
        for proportion in (0.25, 0.5, 0.75):
            for sign in (-1, 1):
                b = sign * proportion * bound
                point = (
                    station[0] + t * u[0] + b * n[0],
                    station[1] + t * u[1] + b * n[1],
                )
                choices.append({"point": point, "t_m": t, "b_m": b})
    return choices


def example():
    """Normalized illustrative station/readout, not a supplied official case.

    Safe reception follows the analytic lens theorem; sampled ranking does not
    certify continuous worst-case optimality. No prior distribution is assumed.
    """
    first = clip_bearing(initial_polygon(), (0.0, 0.0), 0.0)
    source_samples = [
        (r * math.cos(math.radians(phi)), r * math.sin(math.radians(phi)))
        for r in range(25, 1501, 25)
        for phi in (-1.0, 0.0, 1.0)
    ]
    output = []
    choices = safe_candidates() + [{"point": (750.0, 0.0), "t_m": 750.0, "b_m": 0.0}]
    for candidate in choices:
        q = candidate["point"]
        worst_radius = 0.0
        for source in source_samples:
            assert math.dist(q, source) <= max(1000, math.dist((0, 0), source)) + 1e-7
            if math.dist(q, source) <= 5:
                radius = 5.0
            else:
                truth = math.degrees(math.atan2(source[1] - q[1], source[0] - q[0]))
                radius = 0.0
                for error in (-1.0, 0.0, 1.0):
                    reading = round((truth + error) % 360, 2) % 360
                    poly = clip_bearing(first, q, reading)
                    radius = max(radius, enclosing_circle(poly)[1])
            worst_radius = max(worst_radius, radius)
        output.append(
            {
                **candidate,
                "sampled_worst_mec_radius_m": worst_radius,
                "first_move_and_measure_s": math.hypot(*q) / 5 + 5,
            }
        )
    best = min(
        output,
        key=lambda row: (
            row["sampled_worst_mec_radius_m"],
            row["first_move_and_measure_s"],
        ),
    )
    result = {
        "evidence": "illustrative_Q2_grid_score_not_global_optimum",
        "first_station": [0, 0],
        "first_reading_deg": 0,
        "source_samples": len(source_samples),
        "second_error_values_deg": [-1, 0, 1],
        "best_sampled_geometry": best,
        "collinear_control": output[-1],
        "candidates": output,
    }
    Path("results").mkdir(exist_ok=True)
    Path("results/second_point_example.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "candidates"}, indent=2))


if __name__ == "__main__":
    example()
