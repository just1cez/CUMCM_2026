"""Boundary/invariant checks for field policy; synthetic and analytic evidence."""

from __future__ import annotations
import json
import math
from pathlib import Path
import random

from field_policy import FieldPlanner
from geometry import _cross, clip_bearing, enclosing_circle, initial_polygon
from negative_geometry import exclude_omni_disk
from planner import Track
from route_portfolio import _control_route, _cost, _improve, choose_portfolio_task
from joint_dispatch_candidate import choose_task
from verify_terminal import DeadlineAdapter


def contains(poly, p, tolerance=2e-6):
    if not poly:
        return False
    if len(poly) == 1:
        return math.dist(poly[0], p) <= tolerance
    if len(poly) == 2:
        a, b = poly
        return abs(math.dist(a, p) + math.dist(b, p) - math.dist(a, b)) <= tolerance
    return all(
        _cross(poly[i], poly[(i + 1) % len(poly)], p)
        >= -tolerance * max(1, math.dist(poly[i], poly[(i + 1) % len(poly)]))
        for i in range(len(poly))
    )


def negative_checks():
    rng = random.Random(6311000)
    count = 0
    largest_cut = 0.0
    for sides in (16, 32):
        for index in range(500):
            phi = rng.uniform(0, math.tau)
            r = 1800 * math.sqrt(rng.random())
            source = (r * math.cos(phi), r * math.sin(phi))
            theta = rng.uniform(0, math.tau)
            distance = rng.uniform(6, 1500)
            station = (
                source[0] - distance * math.cos(theta),
                source[1] - distance * math.sin(theta),
            )
            poly = clip_bearing(
                initial_polygon(),
                station,
                (math.degrees(theta) + rng.uniform(-1, 1)) % 360,
            )
            for j in range(3):
                a = rng.uniform(0, math.tau)
                gap = 1000 + 1e-8 if index % 3 == 0 else rng.uniform(1000, 2500)
                negative = (
                    source[0] + gap * math.cos(a),
                    source[1] + gap * math.sin(a),
                )
                before = poly.copy()
                poly = exclude_omni_disk(poly, negative, sides=sides)
                assert before and poly and contains(poly, source), (
                    sides,
                    index,
                    source,
                    negative,
                )
                assert all(contains(before, v) for v in poly)
                largest_cut = max(
                    largest_cut, enclosing_circle(before)[1] - enclosing_circle(poly)[1]
                )
                count += 1
        assert exclude_omni_disk([(1000.0, 0.0)], (0.0, 0.0), sides=sides) == [
            (1000.0, 0.0)
        ]
        assert exclude_omni_disk([(0.0, 0.0)], (0.0, 0.0), sides=sides) == []
        segment = [(-1200.0, 0.0), (1200.0, 0.0)]
        assert exclude_omni_disk(segment, (0.0, 0.0), sides=sides) == segment
        for shift in ((2e6, -2e6), (0.0, 0.0)):
            p = [
                (shift[0] + 1200, shift[1] - 5),
                (shift[0] + 1400, shift[1] - 5),
                (shift[0] + 1400, shift[1] + 5),
            ]
            assert exclude_omni_disk(p, shift, sides=sides) == p
    try:
        exclude_omni_disk([(0.0, 0.0)], (1e308, 1e308), radius=1e308)
    except ValueError:
        pass
    else:
        raise AssertionError("Unrepresentable half-plane arithmetic must be rejected")
    return {
        "true_source_containment_cases": count,
        "boundary_and_degenerate_cases": 10,
        "maximum_observed_radius_cut_m": largest_cut,
        "scope": "sampling complements finite inscribed-polygon exclusion proof",
    }


def route_checks():
    rng = random.Random(6312000)
    cases = 0
    for n in (1, 2, 3, 7, 25, 41, 51):
        for iteration in range(10):
            pts = [
                (rng.uniform(-2500, 2500), rng.uniform(-2500, 2500)) for _ in range(n)
            ]
            pos = (rng.uniform(-1000, 1000), rng.uniform(-1000, 1000))
            penalty = [rng.uniform(0, 750) for _ in pts]
            origin = [math.dist(pos, p) for p in pts]
            edges = [[math.dist(a, b) for b in pts] for a in pts]
            control = _control_route(origin, edges, penalty)
            improved, cost = _improve(control, origin, edges, penalty)
            assert sorted(improved) == list(range(n)) and cost <= _cost(
                control, origin, edges, penalty
            )
            targets = {i: (p, penalty[i]) for i, p in enumerate(pts)}
            assert choose_task(pos, {}, targets, choice="guarded") == (
                "target",
                control[0],
            )
            assert choose_portfolio_task(pos, {}, targets)[1] in targets
            cases += 1
    # Exact two-task optimum is useful because an open tail has no return edge.
    for positions in (
        ((1.0, 0.0), (2.0, 0.0)),
        ((-1.0, 0.0), (2.0, 0.0)),
        ((0.0, 0.0), (0.0, 0.0)),
    ):
        for risk in (0.0, 1.0, 2.0):
            targets = {i: (point, float(i * 4)) for i, point in enumerate(positions)}
            selected = choose_portfolio_task((0.0, 0.0), {}, targets, risk)
            costs = {
                i: math.dist((0, 0), positions[i])
                + math.dist(*positions)
                + risk * targets[i][1]
                for i in range(2)
            }
            assert costs[selected[1]] == min(costs.values())
    return {
        "random_route_cases": cases,
        "exact_two_task_cases": 9,
        "control_never_worsened": True,
    }


def clearing_checks():
    rng = random.Random(6313000)
    count = 0
    saved = 0.0
    for _ in range(200):
        env = DeadlineAdapter(max_virtual=360000)
        policy = FieldPlanner(env, 3, approach_clear=True)
        policy.action("/enter")
        c = (rng.uniform(-1500, 1500), rng.uniform(-1500, 1500))
        radius = rng.uniform(0.01, 19.8)
        poly = [
            (
                c[0] + radius * math.cos(k * math.pi / 3),
                c[1] + radius * math.sin(k * math.pi / 3),
            )
            for k in range(6)
        ]
        policy.tracks[1] = Track(polygon=poly)
        policy.channel_state[1] = "detected"
        original = list(poly)
        before = math.dist(policy.position, c)
        assert policy.clear(1, c, guaranteed=True)
        assert all(math.dist(v, policy.position) <= 19.9 for v in original)
        assert math.dist((0, 0), policy.position) <= before + 1e-7
        saved += policy.clear_access_saved_m
        count += 1
    for p in (3, 4):
        env = DeadlineAdapter(remaining=1, max_virtual=360000)
        result = FieldPlanner(env, p).run()
        assert not result["certificate_complete"] and "/exit" not in env.paths
    return {
        "clearing_regions": count,
        "shortened_approach_total_m": saved,
        "real_deadline_cases": 2,
    }


def main():
    result = {
        "evidence": "local_field_geometry_and_behavior_verification_not_official",
        "negative_geometry": negative_checks(),
        "routes": route_checks(),
        "clearing": clearing_checks(),
    }
    Path("results/field_verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
