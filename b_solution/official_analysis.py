

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from submission.支撑材料.geometry import enclosing_circle
from submission.支撑材料.planner import Planner

ROOT = Path(__file__).resolve().parent
DEFAULT_HANDOFF = ROOT.parent / "ai_optimization_handoff_20260912"


def load_actions(path):
    events = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    requests = {}
    replies = {}
    actions = []
    accepted_ids = set()
    in_flight = None
    repeated = transport_errors = rejected = 0
    for event in events:
        kind = event["event"]
        rid = event.get("request_id")
        assert kind in ("request", "response", "accepted", "transport_error"), (
            "Unknown event kind"
        )
        assert event["path"] in ("/enter", "/measure", "/clear", "/exit"), (
            "Unknown action path"
        )
        if kind == "request":
            assert event["body"]["robot_id"] == "TEAM_REDACTED", "Unredacted identifier"
            assert event["body"]["request_id"] == rid, "Request identity mismatch"
            signature = (event["path"], event["body"])
            if rid in requests:
                assert requests[rid] == signature, "Idempotency content mismatch"
                repeated += 1
            requests[rid] = signature
            assert in_flight is None or in_flight == rid, "Concurrent logical actions"
            in_flight = rid
        elif kind == "response":
            assert in_flight == rid
            assert event["path"] == requests[rid][0], "Response path mismatch"
            body = json.loads(event["body_utf8"])
            if event["http_status"] != 200 or body["accepted"] is not True:
                rejected += 1
            else:
                if rid in replies:
                    assert replies[rid] == body, (
                        "Same action returned inconsistent accepted responses"
                    )
                replies[rid] = body
            in_flight = None
        elif kind == "transport_error":
            assert in_flight == rid and event["path"] == requests[rid][0], (
                "Unmatched transport error"
            )
            transport_errors += 1
        elif kind == "accepted":
            assert in_flight is None, "Accepted record precedes complete response"
            assert rid in replies
            assert rid not in accepted_ids, "Duplicate accepted-action record"
            accepted_ids.add(rid)
            route, body = requests[rid]
            assert route == event["path"]
            actions.append(
                {
                    "path": route,
                    "body": body,
                    "response": replies[rid],
                    "request_id": rid,
                    "client_accepted": event,
                }
            )
    assert (
        in_flight is None
        and actions[0]["path"] == "/enter"
        and actions[-1]["path"] == "/exit"
    )
    return actions, {
        "jsonl_records": len(events),
        "retries": repeated,
        "transport_errors": transport_errors,
        "rejected_responses": rejected,
    }


class TraceDivergence(RuntimeError):
    pass


class StrictReplay:
    def __init__(self, actions):
        self.actions = actions
        self.index = 0
        self.maximum_coordinate_difference_m = 0.0

    def act(self, path, position=None, channel=None):
        if self.index == len(self.actions):
            raise TraceDivergence("Policy requested an action after recorded exit")
        item = self.actions[self.index]
        body = item["body"]
        error = 0.0
        if position is not None and "position" in body:
            error = math.dist(position, (body["position"]["x"], body["position"]["y"]))
        if (
            path != item["path"]
            or channel != body.get("channel")
            or (position is None) != ("position" not in body)
            or error > 1e-5
        ):
            raise TraceDivergence(
                f"Unobserved action at index {self.index}: {path}/{channel}; coordinate difference {error:.6g}m"
            )
        self.maximum_coordinate_difference_m = max(
            self.maximum_coordinate_difference_m, error
        )
        self.index += 1
        return dict(item["response"])


class PhaseReplayPlanner(Planner):
    def __init__(self, env, problem):
        super().__init__(env, problem, probe_scale=0.22)
        self.phase = "entry_exit"
        self.phase_records = []

    def action(self, path, point=None, channel=None):
        track = self.tracks.get(channel)
        before = enclosing_circle(track.polygon)[1] if track else None
        old_pos = self.position
        response = super().action(path, point, channel)
        self.phase_records.append(
            {
                "phase": self.phase,
                "known_before": track is not None,
                "radius_before_m": before,
                "movement_m": 0.0 if point is None else math.dist(old_pos, point),
            }
        )
        return response

    def _within(self, name, method, *args):
        previous = self.phase
        self.phase = name
        try:
            return method(*args)
        finally:
            self.phase = previous

    def scan_anchor(self, index):
        return self._within("anchor", super().scan_anchor, index)

    def localize(self, channel):
        return self._within("localize", super().localize, channel)

    def share_current_stop(self):
        return self._within("shared_stop", super().share_current_stop)

    def optical_finish(self, channel):
        return self._within("optical_fallback", super().optical_finish, channel)


def analyze_run(root, row):
    actions, wire = load_actions(root / row["private_requests"])
    observed = json.loads((root / row["observed_result"]).read_text(encoding="utf-8"))
    labels = json.loads((root / row["simulator_result"]).read_text(encoding="utf-8"))
    problem = int(row["problem"])
    assert problem == observed["problem"] == labels["problem_no"]
    assert labels["case_code"] == row["case_code"]
    assert str(labels["practice_run_no"]) == row["practice_run_no"]
    assert labels["jammer_count"] == int(row["source_count"])
    assert (
        labels["directional_jammer_count"] + labels["omnidirectional_jammer_count"]
        == labels["jammer_count"]
    )
    assert labels["directional_jammer_count"] == int(row["directional_count"])
    assert labels["omnidirectional_jammer_count"] == int(row["omni_count"])
    assert observed["certificate_complete"] is True
    assert row["certificate_complete"].lower() == "true"
    assert observed["strategy"] == "refined"
    assert observed["coverage_policy"] == ("ring" if problem == 3 else "compact25")
    if "probe_scale" in observed:
        assert observed["probe_scale"] == 0.22
    replay = StrictReplay(actions)
    policy = PhaseReplayPlanner(replay, problem)
    try:
        result = policy.run()
        assert replay.index == len(actions)
        replay_status = {
            "matched": True,
            "matched_actions": replay.index,
            "maximum_coordinate_difference_m": replay.maximum_coordinate_difference_m,
        }
        assert result["certificate_complete"] is True
        phases = policy.phase_records
    except TraceDivergence as exc:
        replay_status = {
            "matched": False,
            "matched_actions": replay.index,
            "reason": str(exc),
        }
        phases = []
    
    position = (0.0, 0.0)
    radio = 1
    clock_us = 0
    movement_us = 0
    distance = 0.0
    switches = 0
    counts = Counter()
    outcomes = Counter()
    cleared = set()
    known = set()
    first_positive = {}
    negative_after_positive = 0
    max_residual = 0.0
    by_phase = {}
    for i, item in enumerate(actions):
        path, request, response = item["path"], item["body"], item["response"]
        counts[path] += 1
        move = 0.0
        operation = switch = 0
        ch = request.get("channel")
        if path in ("/measure", "/clear"):
            p = (request["position"]["x"], request["position"]["y"])
            move = math.dist(position, p)
            distance += move
            position = p
            movement_us += round(move / 5 * 1_000_000)
            clock_us += round(move / 5 * 1_000_000)
            if path == "/measure":
                switch = int(ch != radio)
                radio = ch
                switches += switch
                operation = 5
                outcome = response["measure_result"]
                assert outcome in ("direction", "near", "no_signal")
                if outcome in ("direction", "near"):
                    known.add(ch)
                    first_positive.setdefault(ch, i)
                elif ch in known and ch not in cleared:
                    negative_after_positive += 1
            else:
                outcome = response["clear_result"]
                assert outcome in ("success", "no_target_in_range")
                operation = 5 if outcome == "success" else 3
                if outcome == "success":
                    assert ch not in cleared
                    cleared.add(ch)
            outcomes[outcome] += 1
            clock_us += (operation + switch) * 1_000_000
        assert math.isclose(move, item["client_accepted"]["distance_m"], abs_tol=1e-7)
        assert switch == item["client_accepted"]["switch_time_s"]
        residual = abs(clock_us / 1_000_000 - float(response["virtual_time_s"]))
        max_residual = max(max_residual, residual)
        assert residual < 3e-6, (problem, row["round"], i, residual)
        if phases:
            name = phases[i]["phase"]
            cost = by_phase.setdefault(
                name,
                {
                    "actions": 0,
                    "distance_m": 0.0,
                    "measures": 0,
                    "known_measures": 0,
                    "time_s": 0.0,
                },
            )
            cost["actions"] += 1
            cost["distance_m"] += move
            cost["measures"] += path == "/measure"
            cost["known_measures"] += path == "/measure" and phases[i]["known_before"]
            cost["time_s"] += (
                round(move / 5 * 1_000_000) / 1_000_000 + operation + switch
            )
    assert (
        len(cleared)
        == observed["n_cleared"]
        == labels["jammer_count"]
        == int(row["cleared"])
    )
    assert set(observed["cleared_channels"]) == cleared
    T = float(actions[-1]["response"]["virtual_time_s"])
    K = len(cleared)
    assert abs(T - float(row["virtual_time_s"])) < 3e-6
    assert math.isclose(T, float(observed["virtual_time_s"]), rel_tol=0.0, abs_tol=3e-6)
    assert math.isclose(T / K, observed["average_time_s"], abs_tol=1e-6)
    assert math.isclose(T / K, float(row["average_time_s"]), abs_tol=1e-6)
    return {
        "problem": problem,
        "round": int(row["round"]),
        "case_code": row["case_code"],
        "source_count": labels["jammer_count"],
        "omni_count": labels["omnidirectional_jammer_count"],
        "directional_count": labels["directional_jammer_count"],
        "n_cleared": K,
        "virtual_time_s": T,
        "average_time_s": T / K,
        "certificate_complete": observed["certificate_complete"],
        "controller_strategy": observed["strategy"],
        "replay_probe_scale": 0.22,
        "coverage_policy": observed["coverage_policy"],
        "termination": observed["termination"],
        "visited_anchors": observed["visited_anchors"],
        "total_anchors": observed["total_anchors"],
        "measures": counts["/measure"],
        "switches": switches,
        "distance_m": distance,
        "clear_attempts": counts["/clear"],
        "clear_failures": outcomes["no_target_in_range"],
        "optical_fallbacks": observed["optical_fallbacks"],
        "move_time_s": movement_us / 1_000_000,
        "measure_time_s": 5 * counts["/measure"],
        "switch_time_s": switches,
        "failed_clear_time_s": 3 * outcomes["no_target_in_range"],
        "successful_clear_time_s": 5 * K,
        "accounted_virtual_time_s": clock_us / 1_000_000,
        "maximum_step_residual_s": max_residual,
        "outcomes": dict(outcomes),
        "no_signal_after_positive": negative_after_positive,
        "first_positive_action_index": first_positive,
        "phase_costs": by_phase,
        "http_enter_to_exit_s": (
            actions[-1]["response"]["real_timestamp_ms"]
            - actions[0]["response"]["real_timestamp_ms"]
        )
        / 1000,
        "controller_wall_s": observed["local_wall_duration_s"],
        "manifest_timestamp_delta_s": float(row["timestamp_delta_s"]),
        "strict_baseline_replay": replay_status,
        **wire,
    }


def analyze(root):
    with (root / "manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 20 and {(int(r["problem"]), int(r["round"])) for r in rows} == {
        (p, n) for p in (3, 4) for n in range(1, 11)
    }
    assert len({r["case_code"] for r in rows}) == 20
    inputs = {"manifest.csv"}
    for row in rows:
        inputs.update(
            row[key]
            for key in ("private_requests", "observed_result", "simulator_result")
        )
    runs = [analyze_run(root, row) for row in rows]
    summary = {}
    for p in (3, 4):
        group = [r for r in runs if r["problem"] == p]
        T = sum(r["virtual_time_s"] for r in group)
        K = sum(r["n_cleared"] for r in group)
        summary[str(p)] = {
            "runs": len(group),
            "source_total": sum(r["source_count"] for r in group),
            "cleared_total": K,
            "all_cleared": sum(r["n_cleared"] == r["source_count"] for r in group),
            "mean_virtual_time_s": T / len(group),
            "weighted_s_per_source": T / K,
            "mean_per_source_s": statistics.mean(r["average_time_s"] for r in group),
            "median_per_source_s": statistics.median(
                r["average_time_s"] for r in group
            ),
            "cost_fractions": {
                key: sum(r[key] for r in group) / T
                for key in (
                    "move_time_s",
                    "measure_time_s",
                    "switch_time_s",
                    "failed_clear_time_s",
                    "successful_clear_time_s",
                )
            },
        }
        for key in (
            "distance_m",
            "measures",
            "switches",
            "clear_failures",
            "optical_fallbacks",
            "http_enter_to_exit_s",
            "controller_wall_s",
        ):
            summary[str(p)]["mean_" + key] = statistics.mean(r[key] for r in group)
    return {
        "evidence": "official_simulator_practice_observations_from_user_supplied_logs",
        "official_practice": True,
        "formal_test": False,
        "offline_analysis_only": True,
        "hidden_truth_used_online": False,
        "run_count": 20,
        "input_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in sorted(inputs)
        },
        "summary": summary,
        "runs": runs,
        "limits": [
            "Practice counts/types are post-exit labels, not policy inputs.",
            "Strict replay supplies only observed responses and fails at the first unobserved request; it does not predict improved-policy results.",
            "Phase attribution is emitted only when the complete baseline action sequence matches, up to stated coordinate roundoff.",
            "manifest_timestamp_delta_s has no established runtime meaning. HTTP timestamp difference is an auxiliary runtime check, not a GUI formal score.",
            "No encrypted formal-test logs were supplied.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results/official_practice_analysis.json"
    )
    args = parser.parse_args()
    result = analyze(args.handoff)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "summary": result["summary"],
                "strict_replay": [r["strict_baseline_replay"] for r in result["runs"]],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
