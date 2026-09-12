"""Coverage-certified search; consumes observations only, never simulator truth."""

from dataclasses import dataclass, field
from math import dist, hypot
from time import monotonic

from active_policy_candidate import choose_probe
from client import AmbiguousActionError, DeadlineExceeded
from coverage import directional_waypoints, omni_waypoints
from geometry import clip_bearing, enclosing_circle, initial_polygon, optical_cover
from route_policy_candidate import optimize_waypoints
from joint_dispatch_candidate import choose_task
from optical_policy_candidate import certified_optical_cover
from polar_coverage_candidate import polar_waypoints


class SessionTerminated(RuntimeError):
    """The simulator closed after an accepted action reached its limit."""


class InconsistentObservations(RuntimeError):
    """The specified bounded-error model no longer contains a possible source."""


@dataclass
class Track:
    polygon: list = field(default_factory=initial_polygon)
    readings: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    failures: list = field(default_factory=list)


class Planner:
    """Baseline clears detections immediately; integrated batches and shares stops.

    Sampling and route heuristics affect time only. Completeness comes from the
    waypoint certificate and the conservative, finite optical-cover fallback.
    """

    def __init__(
        self,
        environment,
        problem=3,
        strategy="refined",
        spacing=990.0,
        probe_scale=0.22,
        max_probes=6,
        loss_recovery=True,
        anchor_policy=None,
        probe_policy="fixed",
        ring_radius=None,
        coverage_policy=None,
        optical_policy="rectangle",
        dispatch_policy=None,
        scan_policy=None,
    ):
        if problem not in (3, 4) or strategy not in (
            "baseline",
            "batched",
            "integrated",
            "enhanced",
            "refined",
        ):
            raise ValueError("Unsupported problem or strategy")
        if anchor_policy is None:
            anchor_policy = "rolling" if strategy in ("enhanced", "refined") and problem == 4 else "nearest"
        if ring_radius is None and strategy in ("enhanced", "refined") and problem == 3:
            ring_radius = 1200.0
        if coverage_policy is None:
            coverage_policy = "compact25" if strategy == "refined" and problem == 4 else "lattice"
        if dispatch_policy is None:
            dispatch_policy = ("center" if problem == 3 else "guarded") if strategy == "refined" else "separate"
        if scan_policy is None:
            scan_policy = ("unknown" if problem == 3 else "useful") if strategy == "refined" else "all"
        if anchor_policy not in ("nearest", "two_opt", "rolling"):
            raise ValueError("Unsupported anchor policy")
        if probe_policy not in ("fixed", "adaptive"):
            raise ValueError("Unsupported probe policy")
        if not 900 <= spacing <= 999:
            raise ValueError("Directional lattice spacing must be in [900, 999] m")
        if not 0 < probe_scale <= 1 or max_probes < 1:
            raise ValueError("Invalid localization policy parameters")
        if coverage_policy not in ("lattice", "seed25", "compact25"):
            raise ValueError("Unsupported discovery coverage policy")
        if optical_policy not in ("rectangle", "slabs"):
            raise ValueError("Unsupported optical covering policy")
        if dispatch_policy not in ("separate", "center", "guarded"):
            raise ValueError("Unsupported task dispatch policy")
        if scan_policy not in ("all", "unknown", "useful"):
            raise ValueError("Unsupported known-channel scan policy")
        self.scan_policy = scan_policy
        self.coverage_policy = coverage_policy if problem == 4 else "ring"
        self.optical_policy = optical_policy
        self.dispatch_policy = dispatch_policy
        self.environment = environment
        self.problem = problem
        self.strategy = strategy
        self.waypoints = (
            omni_waypoints(ring_radius) if problem == 3 else
            directional_waypoints(spacing) if coverage_policy == "lattice" else
            polar_waypoints(coverage_policy)
        )
        self.anchor_policy = anchor_policy
        self.anchor_order = optimize_waypoints(self.waypoints) if anchor_policy == "two_opt" else []
        self.anchor_rank = {index: rank for rank, index in enumerate(self.anchor_order)}
        self.pending = set(range(len(self.waypoints)))
        self.visited = []
        self.tracks = {}
        self.cleared = set()
        self.scan_records = {ch: set() for ch in range(1, 21)}
        self.position = (0.0, 0.0)
        self.radio_channel = 1
        self.virtual_time = 0.0
        self.deadline = float("inf")
        self.max_virtual_duration = float("inf")
        self.terminal_reason = None
        self.observation_points = {ch: [] for ch in range(1, 21)}
        self.channel_state = {ch: "unresolved" for ch in range(1, 21)}
        self.probe_scale = probe_scale
        self.max_probes = max_probes
        self.loss_recovery = bool(loss_recovery) and problem == 4
        self.fallbacks = 0
        self.probe_policy = probe_policy
        self.adaptive_probes = 0
        self.termination = None

    def action(self, path, point=None, channel=None):
        if self.terminal_reason is not None:
            raise SessionTerminated(self.terminal_reason)
        if monotonic() >= self.deadline - 2.0 and path != "/exit":
            raise TimeoutError("Insufficient real time: completeness not certified")
        response = self.environment.act(path, position=point, channel=channel)
        if response.get("accepted") is not True:
            raise RuntimeError("Rejected action; cached state was not advanced")
        self.virtual_time = float(response["virtual_time_s"])
        if path == "/enter":
            self.max_virtual_duration = float(response.get("max_virtual_duration_s", float("inf")))
        if point is not None:
            self.position = tuple(point)
        if path == "/measure":
            self.radio_channel = channel
        if path in ("/measure", "/clear") and self.virtual_time >= self.max_virtual_duration:
            self.terminal_reason = "virtual_timeout"
        return response

    def clear(self, channel, point, guaranteed=False):
        result = self.action("/clear", point, channel)["clear_result"]
        if result == "success":
            self.cleared.add(channel)
            self.channel_state[channel] = "cleared"
            self.tracks.pop(channel, None)
            return True
        if result != "no_target_in_range":
            raise RuntimeError(f"Unknown clear result: {result}")
        if guaranteed:
            raise InconsistentObservations("Certified radius-20 clearing failed")
        if channel in self.tracks:
            self.tracks[channel].failures.append(tuple(point))
        return False

    def measure(self, channel, point):
        result = self.action("/measure", point, channel)
        status = result["measure_result"]
        self.observation_points[channel].append(tuple(point))
        track = self.tracks.get(channel)
        if track is None and status == "direction":
            track = Track(observations=self.observation_points[channel])
            self.tracks[channel] = track
        if track is not None:
            track.observations = self.observation_points[channel]
        if status == "near":
            self.channel_state[channel] = "detected"
            if self.terminal_reason is None:
                self.clear(channel, point, guaranteed=True)
        elif status == "direction":
            self.channel_state[channel] = "detected"
            track.polygon = clip_bearing(track.polygon, point, result["svd_deg"])
            if not track.polygon:
                raise InconsistentObservations(
                    f"Empty feasible region on channel {channel}"
                )
            track.readings.append((tuple(point), float(result["svd_deg"])))
        elif status != "no_signal":
            raise RuntimeError(f"Unknown measure result: {status}")
        # No-signal observations are not convex halfplanes. In Q4 in particular,
        # deleting a 1000-m disk would silently exclude real sources.
        return status

    def scan_anchor(self, index):
        point = self.waypoints[index]
        channels = [ch for ch in range(1, 21) if ch not in self.cleared]
        channels.sort(key=lambda ch: (ch != self.radio_channel, ch))
        for channel in channels:
            if channel in self.cleared:
                continue
            if channel in self.tracks:
                if self.scan_policy == "unknown":
                    continue
                if self.scan_policy == "useful":
                    center, radius = enclosing_circle(self.tracks[channel].polygon)
                    if radius <= 19.9 or dist(point, center) - radius > 1500:
                        continue
            self.measure(channel, point)
            self.scan_records[channel].add(index)
            if len(self.cleared) == 16:
                self.termination = "known_count_upper_bound_16"
                break
            if self.terminal_reason is not None:
                break
            if self.strategy == "baseline" and channel in self.tracks:
                self.localize(channel)
            if len(self.cleared) == 16:
                self.termination = "known_count_upper_bound_16"
                break
            if self.terminal_reason is not None:
                break
        self.pending.discard(index)
        if index not in self.visited:
            self.visited.append(index)

    def optical_finish(self, channel):
        self.fallbacks += 1
        covering = certified_optical_cover if self.optical_policy == "slabs" else optical_cover
        cover = covering(self.tracks[channel].polygon, radius=19.9)
        if not cover:
            raise InconsistentObservations("An empty region cannot certify clearing")
        start = min(range(len(cover)), key=lambda k: dist(self.position, cover[k]))
        # Rotate the certified snake to the nearest cell. At most one long
        # wraparound jump; the remaining edges are adjacent rectangle cells.
        order = cover[start:] + cover[:start]
        for point in order:
            if self.clear(channel, point):
                return
            if self.terminal_reason is not None:
                return
        raise InconsistentObservations("Exhausted a certified optical cover without clearing")

    def localize(self, channel):
        losses = 0
        failed_probe = None
        for probe_index in range(self.max_probes):
            if channel in self.cleared or self.terminal_reason is not None:
                return
            track = self.tracks[channel]
            center, radius = enclosing_circle(track.polygon)
            if max(dist(self.position, p) for p in track.polygon) <= 19.9:
                self.clear(channel, self.position, guaranteed=True)
                return
            if radius <= 19.9:
                self.clear(channel, center, guaranteed=True)
                return
            # When the remaining uncertainty is small, a 3-s failed optical
            # attempt can cost less than travelling to take another bearing.
            if radius <= 38 and center not in track.failures:
                if self.clear(channel, center):
                    return
                if self.terminal_reason is not None:
                    return
                self.optical_finish(channel)
                return
            previous = track.readings[-1][0]
            dx, dy = center[0] - previous[0], center[1] - previous[1]
            length = hypot(dx, dy)
            if length < 1e-8:
                self.optical_finish(channel)
                return
            unit, normal = (dx / length, dy / length), (-dy / length, dx / length)
            if failed_probe is not None and self.loss_recovery:
                vector = (failed_probe[0] - previous[0], failed_probe[1] - previous[1])
                axial = vector[0] * unit[0] + vector[1] * unit[1]
                lateral = vector[0] * normal[0] + vector[1] * normal[1]
                point = (
                    previous[0] + 0.5 * (axial * unit[0] - lateral * normal[0]),
                    previous[1] + 0.5 * (axial * unit[1] - lateral * normal[1]),
                )
                if any(point == p for p in track.observations) or point in track.failures:
                    self.optical_finish(channel)
                    return
            else:
                point = None
                if self.probe_policy == "adaptive":
                    point = choose_probe(
                        track.polygon,
                        track.readings,
                        self.position,
                        self.problem,
                        probes_remaining=self.max_probes - probe_index,
                        rejected_points=track.failures + track.observations,
                        probe_scale=self.probe_scale,
                    )
                    if point is not None:
                        self.adaptive_probes += 1
                if point is None:
                    offset = min(120.0, max(25.0, self.probe_scale * radius))
                    candidates = [
                        (
                            center[0] + sign * offset * normal[0],
                            center[1] + sign * offset * normal[1],
                        )
                        for sign in (-1, 1)
                    ]
                    fresh = [
                        p
                        for p in candidates
                        if p not in track.observations
                        and all(p != s for s in track.failures)
                    ]
                    if not fresh:
                        self.optical_finish(channel)
                        return
                    point = min(fresh, key=lambda p: dist(self.position, p))
            status = self.measure(channel, point)
            if channel in self.cleared or self.terminal_reason is not None:
                return
            if status == "no_signal":
                losses += 1
                if self.clear(channel, point):
                    return
                if self.terminal_reason is not None:
                    return
                failed_probe = point
                if losses >= 2 and not self.loss_recovery:
                    self.optical_finish(channel)
                    return
            else:
                failed_probe = None
        if channel not in self.cleared and self.terminal_reason is None:
            self.optical_finish(channel)

    def share_current_stop(self):
        """Fuse an extra bearing for known sources at an already reached stop."""
        if self.strategy not in ("integrated", "enhanced", "refined") or self.terminal_reason is not None or len(self.cleared) == 16:
            return
        for channel in list(self.tracks):
            if channel in self.cleared:
                continue
            track = self.tracks[channel]
            center, radius = enclosing_circle(track.polygon)
            if radius <= 19.9:
                continue
            if any(self.position == p for p in track.observations):
                continue
            if dist(self.position, center) - radius > 1500:
                continue
            self.measure(channel, self.position)
            if self.terminal_reason is not None:
                return

    def next_anchor(self):
        if self.anchor_policy == "two_opt":
            return min(self.pending, key=lambda i: self.anchor_rank[i])
        if self.anchor_policy == "rolling":
            indices = sorted(self.pending)
            order = optimize_waypoints([self.waypoints[i] for i in indices], self.position)
            return indices[order[0]]
        return min(self.pending, key=lambda i: (dist(self.position, self.waypoints[i]), i))
    def _result(self):
        complete = len(self.cleared) == 16
        if not complete:
            for channel in range(1, 21):
                if channel in self.cleared:
                    self.channel_state[channel] = "cleared"
                elif (self.channel_state[channel] != "detected"
                      and len(self.scan_records[channel]) == len(self.waypoints)):
                    self.channel_state[channel] = "absent-certified"
                else:
                    complete = False
                    break
            else:
                complete = True
        if self.terminal_reason is not None:
            self.termination = ("complete_after_" if complete else "incomplete_") + self.terminal_reason
        return {
            "problem": self.problem,
            "strategy": self.strategy,
            "cleared_channels": sorted(self.cleared),
            "n_cleared": len(self.cleared),
            "virtual_time_s": self.virtual_time,
            "average_time_s": self.virtual_time / len(self.cleared)
            if self.cleared else None,
            "probe_policy": self.probe_policy,
            "anchor_policy": self.anchor_policy,
            "ring_radius_m": hypot(*self.waypoints[1]) if self.problem == 3 else None,
            "loss_recovery": self.loss_recovery,
            "adaptive_probes": self.adaptive_probes,
            "channel_certificates": dict(self.channel_state),
            "certificate_complete": complete,
            "terminal_reason": self.terminal_reason,
            "visited_anchors": len(self.visited),
            "total_anchors": len(self.waypoints),
            "optical_fallbacks": self.fallbacks,
            "termination": self.termination,
            "coverage_policy": self.coverage_policy,
            "optical_policy": self.optical_policy,
            "dispatch_policy": self.dispatch_policy,
            "scan_policy": self.scan_policy,
        }

    def run(self):
        try:
            return self._run_body()
        except (TimeoutError, ConnectionError, AmbiguousActionError,
                DeadlineExceeded, SessionTerminated) as exc:
            self.terminal_reason = self.terminal_reason or type(exc).__name__
            self.termination = self.termination or "incomplete_" + type(exc).__name__
            return self._result()

    def _run_body(self):
        entry_started = monotonic()
        entered = self.action("/enter")
        self.deadline = entry_started + entered["remaining_real_duration_s"]
        self.scan_anchor(0)
        while (self.pending or self.tracks) and self.terminal_reason is None:
            if len(self.cleared) == 16:
                self.termination = "known_count_upper_bound_16"
                break
            if self.strategy == "baseline":
                if self.tracks:
                    self.localize(next(iter(self.tracks)))
                elif self.pending:
                    self.scan_anchor(self.next_anchor())
                continue
            if self.dispatch_policy != "separate":
                kind, index = choose_task(
                    self.position,
                    {i: self.waypoints[i] for i in sorted(self.pending)},
                    {ch: enclosing_circle(track.polygon) for ch, track in self.tracks.items()},
                    choice=self.dispatch_policy,
                )
                if kind == "target":
                    self.localize(index)
                    self.share_current_stop()
                else:
                    self.scan_anchor(index)
                continue
            targets = [
                (dist(self.position, enclosing_circle(t.polygon)[0]), ch)
                for ch, t in self.tracks.items()
            ]
            anchors = [
                (
                    dist(self.position, self.waypoints[i])
                    + 30.0 * (20 - len(self.cleared)),
                    i,
                )
                for i in ([self.next_anchor()] if self.pending and self.anchor_policy == "rolling" else self.pending)
            ]
            # Convert a full scan to equivalent travel metres (6 s * 5 m/s).
            # This is a myopic time heuristic, not a global-optimality claim.
            if targets and (not anchors or min(targets)[0] <= min(anchors)[0]):
                self.localize(min(targets)[1])
                self.share_current_stop()
            else:
                self.scan_anchor(self.next_anchor())
        if self.termination is None:
            if self.terminal_reason is None:
                for channel in range(1, 21):
                    if channel in self.cleared:
                        self.channel_state[channel] = "cleared"
                    elif (self.channel_state[channel] != "detected"
                          and len(self.scan_records[channel]) == len(self.waypoints)):
                        self.channel_state[channel] = "absent-certified"
                    else:
                        raise RuntimeError("Incomplete per-channel discovery coverage")
                self.termination = "all_channels_cleared_or_coverage_certified_absent"
            else:
                current = self._result()
                if current["certificate_complete"]:
                    self.termination = "complete_after_" + self.terminal_reason
                else:
                    self.termination = "incomplete_" + self.terminal_reason
        if self.terminal_reason is None:
            self.action("/exit")
        return self._result()
