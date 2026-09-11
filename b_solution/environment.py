"""Synthetic, not official, CUMCM 2026 B environment (standard library only).

Generation assumptions are deliberately explicit, not claims about official data:
* random: N is discrete uniform on 10..16; N distinct channels sampled uniformly
  without replacement; positions iid uniform in the radius-1800 disk (sqrt(U)
  radial law); radio radii iid uniform [1000,1500]; orientations uniform [0,2*pi).
  Q3 is all omni. Q4 chooses a uniform count in 1..N-1 and a uniform subset
  of directional sources, guaranteeing both types.
* minimum_radius: random geometry, but every radio radius is exactly 1000.
* outward_boundary: 16 equally spaced sources on the arena boundary, a seeded
  common rotation, all radii 1000. Q4 has 15 outward-facing directional sources
  and one omni, so inward-only search is deliberately inadequate.
* clustered: 16 sources uniform in a 35m disk around a seeded center at radius
  1650; all radio radii 1000, with the random mixed-type rule for Q4.

Errors are deterministic functions of (seed, channel, exact coordinate): smooth
is a bounded two-sinusoid field; extreme is spatial-hashed +/-1 degree;
iid_location is spatial-hashed uniform [-1,1], NOT independent repeat readings.
The latter is a synthetic hash field, not an assertion of official IID noise.
Sources and their parameters are private. Only post-exit summary reveals counts.
There are no virtual-duration sleeps; movement time is rounded to microseconds.
"""

from __future__ import annotations

import hashlib
import math
import random
import struct
import threading
import time
from dataclasses import dataclass

Point = tuple[float, float]
SCENARIOS = ("random", "minimum_radius", "outward_boundary", "clustered")
ERROR_MODES = ("smooth", "extreme", "iid_location")


def _action_args(path: str, position: Point | None, channel: int | None):
    """Validate before any state mutation; match protocol coordinate limits."""
    if path not in ("/enter", "/exit", "/measure", "/clear"):
        raise ValueError("Unknown action path (paths must be exact)")
    if path in ("/enter", "/exit"):
        if position is not None or channel is not None:
            raise ValueError("enter/exit do not accept position or channel")
        return None, None
    if not isinstance(position, (tuple, list)) or len(position) != 2:
        raise ValueError("position must contain exactly two finite coordinates")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in position):
        raise ValueError("Coordinates must be JSON numbers")
    try:
        point = (float(position[0]), float(position[1]))
    except OverflowError as exc:
        raise ValueError("Coordinate outside protocol range") from exc
    if any(not math.isfinite(v) or abs(v) > 2_000_000 for v in point):
        raise ValueError("Coordinates must be finite and within +/-2000000m")
    if (
        isinstance(channel, bool)
        or not isinstance(channel, (int, float))
        or not 1 <= channel <= 20
        or int(channel) != channel
    ):
        raise ValueError("channel must be an integer in 1..20")
    return point, int(channel)


@dataclass(slots=True)
class _Source:
    position: Point
    radius: float
    normal: Point | None
    phase: float
    cleared: bool = False


class LocalSimulator:
    """One local test session; /enter initializes state, duplicate entry rejects.

    log contains only observable request/response/timing data. After termination,
    construct a new instance for another session, just as the official interface
    requires a new GUI test. Automatic deadline termination closes this session;
    no fabricated /exit response is generated in that case.
    """

    def __init__(
        self,
        seed: int,
        problem: int = 3,
        error_mode: str = "smooth",
        scenario: str = "random",
    ):
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")
        if problem not in (3, 4):
            raise ValueError("problem must be 3 or 4")
        if error_mode not in ERROR_MODES or scenario not in SCENARIOS:
            raise ValueError(f"Use scenarios {SCENARIOS} and modes {ERROR_MODES}")
        self._seed, self._problem = seed, problem
        self._error_mode, self._scenario = error_mode, scenario
        self._lock = threading.Lock()
        self._status = "ready"
        self._sources: dict[int, _Source] = {}
        self._position: Point = (0.0, 0.0)
        self._radio_channel = 1
        self._virtual_us = 0
        self._distance = 0.0
        self._measures = self._switches = self._clear_attempts = self._failed_clears = 0
        self._started: float | None = None
        self._finished: float | None = None
        self._exit_reason: str | None = None
        self.log: list[dict] = []

    def _generate(self):
        rng = random.Random(self._seed)
        n = (
            16
            if self._scenario in ("outward_boundary", "clustered")
            else rng.randint(10, 16)
        )
        channels = rng.sample(range(1, 21), n)
        if self._problem == 3:
            directional = set()
        elif self._scenario == "outward_boundary":
            directional = set(channels[:-1])
        else:
            directional = set(rng.sample(channels, rng.randint(1, n - 1)))
        rotation = rng.uniform(0, math.tau)
        center = (1650 * math.cos(rotation), 1650 * math.sin(rotation))
        sources = {}
        for i, channel in enumerate(channels):
            theta = rng.uniform(0, math.tau)
            if self._scenario == "outward_boundary":
                theta = rotation + math.tau * i / n
                position = (1800 * math.cos(theta), 1800 * math.sin(theta))
            elif self._scenario == "clustered":
                r = 35 * math.sqrt(rng.random())
                position = (
                    center[0] + r * math.cos(theta),
                    center[1] + r * math.sin(theta),
                )
            else:
                r = 1800 * math.sqrt(rng.random())
                position = (r * math.cos(theta), r * math.sin(theta))
            radius = rng.uniform(1000, 1500) if self._scenario == "random" else 1000.0
            orientation = (
                theta
                if self._scenario == "outward_boundary"
                else rng.uniform(0, math.tau)
            )
            normal = (
                (math.cos(orientation), math.sin(orientation))
                if channel in directional
                else None
            )
            sources[channel] = _Source(
                position, radius, normal, rng.uniform(0, math.tau)
            )
        self._sources = sources

    def _bearing_error(self, point: Point, channel: int, source: _Source) -> float:
        x, y = point
        if self._error_mode == "smooth":
            return 0.6 * math.sin(x / 173 + y / 251 + source.phase) + 0.4 * math.sin(
                x / 419 - y / 137 + 2 * source.phase
            )
        # Canonicalize signed zero: it is the same physical coordinate.
        packed = struct.pack("!ddB", x or 0.0, y or 0.0, channel)
        salt = str(self._seed).encode("ascii") + b":"
        value = int.from_bytes(
            hashlib.blake2b(salt + packed, digest_size=8).digest(), "big"
        )
        if self._error_mode == "extreme":
            return 1.0 if value & 1 else -1.0
        return 2 * (value / ((1 << 64) - 1)) - 1

    def _visible(self, source: _Source, point: Point) -> bool:
        dx, dy = point[0] - source.position[0], point[1] - source.position[1]
        if math.hypot(dx, dy) > source.radius:
            return False
        if source.normal is None:
            return True
        a, b = dx * source.normal[0], dy * source.normal[1]
        # Include the closed halfplane boundary despite floating-point dot error;
        # tolerance is only a handful of machine ulps, not an angular margin.
        return a + b >= -8 * math.ulp(max(abs(a), abs(b), 1.0))

    def _response(self, accepted: bool = True, **fields) -> dict:
        return {
            "accepted": accepted,
            "real_timestamp_ms": int(time.time() * 1000),
            "virtual_time_s": self._virtual_us / 1_000_000 if accepted else 0,
            **fields,
        }

    def _finish(self, reason: str):
        self._status = "exited"
        self._finished = time.monotonic()
        self._exit_reason = reason

    def act(
        self, path: str, position: Point | None = None, channel: int | None = None
    ) -> dict:
        position, channel = _action_args(path, position, channel)
        with self._lock:
            if self._status == "exited":
                raise ConnectionError(
                    "Local session interface closed after exit/timeout"
                )
            if self._started is not None and time.monotonic() >= self._started + 1200:
                self._finish("real_timeout")
                raise ConnectionError("Local session reached its real deadline")
            request = {"path": path}
            if position is not None:
                request.update(
                    position={"x": position[0], "y": position[1]}, channel=channel
                )
            before = self._virtual_us
            radio_before = self._radio_channel
            distance = 0.0
            switched = False
            action_seconds = 0
            if path == "/enter":
                if self._status != "ready":
                    response = self._response(False)
                else:
                    self._generate()
                    self._position, self._radio_channel = (0.0, 0.0), 1
                    self._virtual_us = 0
                    self._started = time.monotonic()
                    self._status = "active"
                    response = self._response(
                        max_virtual_duration_s=360000,
                        max_real_duration_s=1200,
                        remaining_real_duration_s=1200,
                    )
            elif self._status != "active":
                response = self._response(False)
            elif path == "/exit":
                self._finish("user_exit")
                response = self._response(exit_reason="user_exit")
            else:
                distance = math.dist(self._position, position)
                source = self._sources.get(channel)
                live = source is not None and not source.cleared
                if path == "/measure":
                    switched = channel != self._radio_channel
                    self._radio_channel = channel
                    self._switches += int(switched)
                    self._measures += 1
                    action_seconds = 5
                    fields = {"measure_result": "no_signal"}
                    if live and self._visible(source, position):
                        if math.dist(position, source.position) <= 5:
                            fields = {"measure_result": "near"}
                        else:
                            angle = math.degrees(
                                math.atan2(
                                    source.position[1] - position[1],
                                    source.position[0] - position[0],
                                )
                            )
                            bearing = (
                                round(
                                    (
                                        angle
                                        + self._bearing_error(position, channel, source)
                                    )
                                    % 360,
                                    2,
                                )
                                % 360
                            )
                            fields = {"measure_result": "direction", "svd_deg": bearing}
                else:
                    self._clear_attempts += 1
                    success = live and math.dist(position, source.position) <= 20
                    if success:
                        source.cleared = True
                    else:
                        self._failed_clears += 1
                    action_seconds = 5 if success else 3
                    fields = {
                        "clear_result": "success" if success else "no_target_in_range"
                    }
                self._position = position
                self._distance += distance
                self._virtual_us += (
                    round(distance / 5 * 1_000_000)
                    + (action_seconds + int(switched)) * 1_000_000
                )
                response = self._response(**fields)
                if self._virtual_us >= 360000 * 1_000_000:
                    # An action registered before the deadline is allowed to finish.
                    self._finish("virtual_timeout")
            self.log.append(
                {
                    "request": request,
                    "response": dict(response),
                    "distance_m": distance,
                    "move_time_s": round(distance / 5, 6),
                    "switch_time_s": int(switched),
                    "action_time_s": action_seconds,
                    "radio_channel_before": radio_before,
                    "radio_channel_after": self._radio_channel,
                    "action_virtual_time_s": (self._virtual_us - before) / 1_000_000,
                }
            )
            return response

    def summary(self) -> dict:
        """Evaluation only: inaccessible during a run; never consumed by planner."""
        with self._lock:
            if self._status != "exited":
                raise RuntimeError("summary is available only after session exit")
            n = len(self._sources)
            cleared = sum(source.cleared for source in self._sources.values())
            virtual_time = self._virtual_us / 1_000_000
            directional = sum(
                source.normal is not None for source in self._sources.values()
            )
            return {
                "evidence": "local_synthetic_not_official",
                "seed": self._seed,
                "problem": self._problem,
                "scenario": self._scenario,
                "error_mode": self._error_mode,
                "n_sources": n,
                "n_cleared": cleared,
                "n_omnidirectional": n - directional,
                "n_directional": directional,
                "fraction_cleared": cleared / n,
                "virtual_time_s": virtual_time,
                "average_time_s": virtual_time / cleared if cleared else None,
                "distance_m": self._distance,
                "measures": self._measures,
                "switches": self._switches,
                "clear_attempts": self._clear_attempts,
                "failed_clears": self._failed_clears,
                "real_duration_s": self._finished - self._started,
                "exit_reason": self._exit_reason,
            }
