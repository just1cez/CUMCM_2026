"""Serial, append-only-logged HTTP adapter for an already-open simulator test.

This module does NOT authenticate, launch a GUI, or start a formal test. The user
must first start the intended test in the official GUI and wait for readiness.
Only explicit act calls cause simulator actions; close never sends /exit.

A new logical action receives a UUID. Transient retries preserve exactly the
same bytes, path, and request ID. Exhausted ambiguous actions fail closed: no
new action can be submitted on this client because the previous action may have
executed. Logs are ordinary plaintext observations, NOT official encrypted logs.
Real sleeps are used solely for short transport-retry backoff, never virtual time.
"""

from __future__ import annotations

import http.client
import json
import math
import queue
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from submission.支撑材料.environment import Point, _action_args


class ClientError(RuntimeError):
    """An action did not produce a verified accepted response."""


class RejectedActionError(ClientError):
    def __init__(self, status: int, response: dict):
        self.status, self.response = status, response
        super().__init__(
            f"Simulator rejected action: HTTP {status}, accepted={response.get('accepted')!r}"
        )


class AmbiguousActionError(ClientError):
    """The action may have executed; consult the log and simulator GUI."""


class ClientProtocolError(ClientError):
    pass


class DeadlineExceeded(ClientError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never let urllib turn a POST into a GET or send identifiers elsewhere.
        return None


def _number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate response key: {key}")
        result[key] = value
    return result


class HTTPClient:
    """Official wire schema, no truth API, one in-flight logical action at a time.

    Cached public position/radio_channel/virtual_time_s describe only confirmed
    accepted actions. The real deadline uses /enter.remaining_real_duration_s,
    conservatively subtracting all elapsed time since its first send, including
    transport retries. Before entry, a bounded 20-second connection budget applies
    because the actual GUI window deadline is not available through the API.
    """

    _MAX_ATTEMPTS = 4
    _REQUEST_TIMEOUT_S = 5.0
    _ACTION_RETRY_BUDGET_S = 20.0
    _MAX_RESPONSE_BYTES = 65536
    _TRANSIENT_HTTP = frozenset((429, 500, 502, 503, 504))

    def __init__(self, base_url: str, robot_id: str, log_path: str):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "base_url must be an HTTP(S) origin, without credentials/path/query"
            )
        # Force port validation before sending anything.
        _ = parsed.port
        if (
            not isinstance(robot_id, str)
            or not 1 <= len(robot_id.encode("utf-8")) <= 64
        ):
            raise ValueError("robot_id must contain 1..64 UTF-8 bytes")
        if any(unicodedata.category(c) in ("Cc", "Cf") for c in robot_id):
            raise ValueError("robot_id cannot contain control or format characters")
        self._base_url, self._robot_id = base_url.rstrip("/"), robot_id
        self._lock = threading.Lock()
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._closed = False
        self._uncertain = False
        self._entered = self._exited = False
        self._deadline: float | None = None
        self._max_virtual_duration_s: float | None = None
        self.position: Point = (0.0, 0.0)
        self.radio_channel = 1
        self.virtual_time_s = 0.0
        self._log = Path(log_path).open("a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lifecycle closed by close()

    @property
    def remaining_real_duration_s(self) -> float | None:
        """Locally conservative seconds left; unknown until accepted /enter."""
        return (
            None
            if self._deadline is None
            else max(0.0, self._deadline - time.monotonic())
        )

    def _record(self, event: dict):
        self._log.write(
            json.dumps(
                {"logged_at_ms": int(time.time() * 1000), **event},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        self._log.flush()

    def _decode(self, raw: bytes) -> dict:
        if len(raw) > self._MAX_RESPONSE_BYTES:
            raise ClientProtocolError("Response exceeds bounded JSON body size")
        try:
            response = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ClientProtocolError(
                "Response is not valid unambiguous UTF-8 JSON"
            ) from exc
        if not isinstance(response, dict) or type(response.get("accepted")) is not bool:
            raise ClientProtocolError("Response lacks a boolean accepted field")
        if (
            not _number(response.get("real_timestamp_ms"))
            or not _number(response.get("virtual_time_s"))
            or response["virtual_time_s"] < 0
        ):
            raise ClientProtocolError("Response lacks valid numeric timestamps")
        return response

    def _validate_accepted(self, path: str, response: dict):
        virtual_time = response["virtual_time_s"]
        if path == "/enter":
            remaining = response.get("remaining_real_duration_s")
            if (
                not _number(remaining)
                or not 0 <= remaining <= 1200
                or int(remaining) != remaining
            ):
                raise ClientProtocolError("Invalid actual remaining real duration")
            if (
                not _number(response.get("max_virtual_duration_s"))
                or response["max_virtual_duration_s"] <= 0
                or not _number(response.get("max_real_duration_s"))
                or response["max_real_duration_s"] <= 0
                or virtual_time != 0
            ):
                raise ClientProtocolError(
                    "Invalid accepted entry limits or initial time"
                )
        elif virtual_time < self.virtual_time_s:
            raise ClientProtocolError("Accepted action moved virtual time backwards")
        if path == "/measure":
            result = response.get("measure_result")
            if result not in ("near", "no_signal", "direction"):
                raise ClientProtocolError("Unknown measure result")
            if result == "direction":
                angle = response.get("svd_deg")
                if not _number(angle) or not 0 <= angle < 360:
                    raise ClientProtocolError("Invalid direction angle")
            elif "svd_deg" in response:
                raise ClientProtocolError("Bearing supplied without direction result")
        elif path == "/clear" and response.get("clear_result") not in (
            "success",
            "no_target_in_range",
        ):
            raise ClientProtocolError("Unknown clear result")
        elif path == "/exit" and response.get("exit_reason") != "user_exit":
            raise ClientProtocolError("Unexpected successful exit reason")

    def _commit(
        self,
        path: str,
        position: Point | None,
        channel: int | None,
        response: dict,
        first_send: float,
    ):
        if path == "/enter":
            self._entered = True
            self.position, self.radio_channel = (0.0, 0.0), 1
            self._deadline = first_send + response["remaining_real_duration_s"]
            self._max_virtual_duration_s = response["max_virtual_duration_s"]
        elif path == "/exit":
            self._exited = True
        else:
            self.position = position
            if path == "/measure":
                self.radio_channel = channel
        self.virtual_time_s = response["virtual_time_s"]
        self._uncertain = False

    def _exchange(self, request: Request, deadline: float) -> tuple[int, bytes]:
        """Bound connection, headers and body together, not just idle sockets.

        On expiry the daemon may finish the same in-flight request, but cannot
        mutate client state or send another action. act remains fail-closed.
        """
        completed = queue.Queue(maxsize=1)

        def receive():
            try:
                available = deadline - time.monotonic()
                if available <= 0:
                    raise TimeoutError("Absolute HTTP deadline elapsed")
                try:
                    stream = self._opener.open(
                        request, timeout=min(self._REQUEST_TIMEOUT_S, available)
                    )
                except HTTPError as exc:
                    stream = exc
                with stream:
                    status = stream.code
                    expected_length = stream.headers.get("Content-Length")
                    if expected_length is not None:
                        try:
                            expected_length = int(expected_length)
                        except ValueError as exc:
                            raise ClientProtocolError("Invalid Content-Length") from exc
                        if not 0 <= expected_length <= self._MAX_RESPONSE_BYTES:
                            raise ClientProtocolError(
                                "Response exceeds bounded JSON body size"
                            )
                    raw = stream.read(self._MAX_RESPONSE_BYTES + 1)
                    if expected_length is not None and len(raw) < expected_length:
                        raise http.client.IncompleteRead(
                            raw, expected_length - len(raw)
                        )
                completed.put((True, (status, raw)))
            except (
                ClientError,
                OSError,
                ValueError,
                TypeError,
                TimeoutError,
                http.client.HTTPException,
            ) as exc:
                completed.put((False, exc))

        threading.Thread(target=receive, daemon=True, name="simulator-response").start()
        try:
            succeeded, value = completed.get(
                timeout=max(0.0, deadline - time.monotonic())
            )
        except queue.Empty as exc:
            raise TimeoutError(
                "Absolute HTTP deadline elapsed; outcome remains unknown"
            ) from exc
        if not succeeded:
            raise value
        return value

    def act(
        self, path: str, position: Point | None = None, channel: int | None = None
    ) -> dict:
        position, channel = _action_args(path, position, channel)
        with self._lock:
            if self._closed:
                raise ClientError("Client is closed")
            if self._uncertain:
                raise AmbiguousActionError(
                    "Previous outcome is unresolved; no different action may be sent"
                )
            if self._exited:
                raise ClientError("Session already exited; do not query /exit again")
            if self._deadline is not None and time.monotonic() >= self._deadline:
                raise DeadlineExceeded(
                    "Actual remaining real duration has elapsed; interface may be closed"
                )
            if (
                self._max_virtual_duration_s is not None
                and self.virtual_time_s >= self._max_virtual_duration_s
            ):
                raise DeadlineExceeded(
                    "Virtual deadline reached; no post-timeout /exit query is legal"
                )
            if path == "/enter" and self._entered:
                raise ClientError("Cannot enter the same test twice")
            if path != "/enter" and not self._entered:
                raise ClientError(
                    "Explicit successful /enter is required before other actions"
                )
            request_id = uuid.uuid4().hex
            payload = {
                "arena_id": "default",
                "robot_id": self._robot_id,
                "request_id": request_id,
            }
            if position is not None:
                payload.update(
                    position={"x": position[0], "y": position[1]}, channel=channel
                )
            body = json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            first_send = time.monotonic()
            stop = first_send + self._ACTION_RETRY_BUDGET_S
            if self._deadline is not None:
                stop = min(stop, self._deadline)
            last_error = "No response"
            for attempt in range(1, self._MAX_ATTEMPTS + 1):
                available = stop - time.monotonic()
                if available <= 0:
                    break
                self._record(
                    {
                        "event": "request",
                        "path": path,
                        "request_id": request_id,
                        "attempt": attempt,
                        "body": payload,
                    }
                )
                request = Request(
                    self._base_url + path,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                # From this point until a valid outcome, execution is uncertain.
                self._uncertain = True
                try:
                    status, raw = self._exchange(request, stop)
                    self._record(
                        {
                            "event": "response",
                            "path": path,
                            "request_id": request_id,
                            "attempt": attempt,
                            "http_status": status,
                            "body_utf8": raw.decode("utf-8", errors="replace"),
                        }
                    )
                except (URLError, OSError, http.client.HTTPException) as exc:
                    # Includes connection refusal, broken connections, timeouts,
                    # truncated HTTP bodies. No state is inferred from any of these.
                    last_error = f"{type(exc).__name__}: {exc}"
                    self._record(
                        {
                            "event": "transport_error",
                            "path": path,
                            "request_id": request_id,
                            "attempt": attempt,
                            "error": last_error,
                        }
                    )
                else:
                    if status in self._TRANSIENT_HTTP:
                        last_error = f"Transient HTTP {status}"
                    else:
                        response = self._decode(raw)
                        if status != 200 or response["accepted"] is not True:
                            if response["accepted"] is True:
                                raise ClientProtocolError(
                                    "accepted=true with non-200 HTTP status"
                                )
                            self._uncertain = False
                            raise RejectedActionError(status, response)
                        self._validate_accepted(path, response)
                        radio_before = self.radio_channel
                        distance = (
                            math.dist(self.position, position)
                            if position is not None
                            else 0.0
                        )
                        switch = int(path == "/measure" and channel != radio_before)
                        self._record(
                            {
                                "event": "accepted",
                                "path": path,
                                "request_id": request_id,
                                "distance_m": distance,
                                "radio_channel_before": radio_before,
                                "radio_channel_after": channel
                                if path == "/measure"
                                else radio_before,
                                "switch_time_s": switch,
                                "action_virtual_time_s": response["virtual_time_s"]
                                - self.virtual_time_s,
                            }
                        )
                        self._commit(path, position, channel, response, first_send)
                        return response
                if attempt < self._MAX_ATTEMPTS:
                    delay = min(
                        0.2 * 2 ** (attempt - 1), max(0.0, stop - time.monotonic())
                    )
                    if delay > 0:
                        time.sleep(delay)
            raise AmbiguousActionError(
                f"Action {request_id} has no confirmed outcome after bounded retries: {last_error}"
            )

    def close(self):
        """Close only this adapter's log. Never start/end a simulator session."""
        with self._lock:
            if not self._closed:
                self._log.close()
                self._closed = True
