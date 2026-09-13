"""Field-informed candidates; consumes public responses, never practice labels.

Historical Planner(strategy='refined') remains unchanged. Candidate options
are explicit for paired ablation, and only verified configurations are exposed
by the final runner.
"""

from __future__ import annotations

from math import dist, sqrt

from submission.支撑材料.geometry import enclosing_circle
from submission.支撑材料.joint_dispatch_candidate import choose_task
from submission.支撑材料.negative_geometry import exclude_omni_disk
from submission.支撑材料.planner import InconsistentObservations, Planner
from submission.支撑材料.route_portfolio import choose_portfolio_task


class FieldPlanner(Planner):
    def __init__(
        self,
        environment,
        problem=3,
        *,
        premeasure=True,
        negative_updates=True,
        portfolio=True,
        risk_weight=None,
        probe_scale=0.22,
        approach_clear=None,
    ):
        super().__init__(
            environment, problem=problem, strategy="refined", probe_scale=probe_scale
        )
        self.premeasure = premeasure
        self.negative_updates = negative_updates and problem == 3
        self.portfolio = portfolio
        self.approach_clear = problem == 3 if approach_clear is None else approach_clear
        self.risk_weight = (
            (0.0 if problem == 3 else 1.0) if risk_weight is None else risk_weight
        )
        self.negative_stations = {channel: [] for channel in range(1, 21)}
        self.premeasured_channels = set()
        self.zero_travel_probes = 0
        self.negative_cuts = 0
        self.clear_access_saved_m = 0.0

    def measure(self, channel, point):
        status = super().measure(channel, point)
        if not self.negative_updates or channel in self.cleared:
            return status
        if status == "no_signal":
            self.negative_stations[channel].append(tuple(point))
        track = self.tracks.get(channel)
        if track is not None and status in ("direction", "no_signal"):
            # A convex outer approximation remains safe after each disk
            # exclusion, including negatives collected before first detection.
            for station in self.negative_stations[channel]:
                before = track.polygon
                track.polygon = exclude_omni_disk(before, station, sides=16)
                self.negative_cuts += track.polygon != before
                if not track.polygon:
                    raise InconsistentObservations(
                        "Omnidirectional negative readings exclude the entire track"
                    )
        return status

    def localize(self, channel):
        track = self.tracks.get(channel)
        if (
            self.premeasure
            and channel not in self.premeasured_channels
            and track is not None
            and self.terminal_reason is None
        ):
            center, radius = enclosing_circle(track.polygon)
            if (
                radius > 38
                and tuple(self.position) not in track.observations
                and dist(self.position, center) - radius <= 1500
            ):
                self.zero_travel_probes += 1
                self.measure(channel, self.position)
                self.premeasured_channels.add(channel)
                if channel in self.cleared or self.terminal_reason is not None:
                    return
        return super().localize(channel)

    def clear(self, channel, point, guaranteed=False):
        track = self.tracks.get(channel)
        length = dist(self.position, point)
        if (
            self.approach_clear
            and guaranteed
            and track is not None
            and length > 1e-6
            and max(dist(point, p) for p in track.polygon) <= 19.9
        ):
            # Slide toward the robot inside the intersection of all vertex
            # radius-19.9 disks. Each vertex supplies an exact quadratic bound.
            u = (
                (self.position[0] - point[0]) / length,
                (self.position[1] - point[1]) / length,
            )
            shift = length
            for p in track.polygon:
                dx, dy = point[0] - p[0], point[1] - p[1]
                dot = dx * u[0] + dy * u[1]
                discriminant = dot * dot + 19.9**2 - dx * dx - dy * dy
                if discriminant < 0.0:
                    shift = 0.0
                    break
                shift = min(shift, -dot + sqrt(discriminant))
            shift = max(0.0, shift - 1e-6)
            candidate = (point[0] + shift * u[0], point[1] + shift * u[1])
            if max(dist(candidate, p) for p in track.polygon) <= 19.9:
                self.clear_access_saved_m += length - dist(self.position, candidate)
                point = candidate
        return super().clear(channel, point, guaranteed=guaranteed)

    def select_task(self):
        anchors = {i: self.waypoints[i] for i in sorted(self.pending)}
        targets = {
            ch: enclosing_circle(track.polygon) for ch, track in self.tracks.items()
        }
        if self.portfolio:
            return choose_portfolio_task(
                self.position, anchors, targets, risk_weight=self.risk_weight
            )
        return choose_task(
            self.position,
            anchors,
            targets,
            choice="guarded",
            risk_weight=self.risk_weight,
        )

    def _result(self):
        result = super()._result()
        result.update(
            strategy="field",
            premeasure=self.premeasure,
            negative_updates=self.negative_updates,
            portfolio=self.portfolio,
            risk_weight=self.risk_weight,
            zero_travel_probes=self.zero_travel_probes,
            negative_cuts=self.negative_cuts,
            approach_clear=self.approach_clear,
            clear_access_saved_m=self.clear_access_saved_m,
        )
        return result
