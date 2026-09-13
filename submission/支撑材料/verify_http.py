"""HTTP fault-injection regression. Local test server, never the official simulator.

Start --server with hub; run without --server as a finite client verification.
The server executes the first measure, truncates its HTTP body, then answers its
same-ID retry from cache. Passing requires exactly-once virtual-time effects.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from submission.支撑材料.client import AmbiguousActionError, HTTPClient
from submission.支撑材料.environment import LocalSimulator


def serve(port, case):
    environment = LocalSimulator(20260910)
    cache = {}
    truncated = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_POST(self):
            nonlocal truncated
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            identity = body["request_id"]
            key = (self.path, raw)
            if identity in cache:
                old_key, response = cache[identity]
                if key != old_key:
                    self.send_error(409)
                    return
            else:
                point = body.get("position")
                point = None if point is None else (point["x"], point["y"])
                response = environment.act(self.path, point, body.get("channel"))
                cache[identity] = (key, response)
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if self.path == "/measure" and not truncated:
                truncated = True
                if case == "deadline":
                    size = max(1, len(encoded) // 8)
                    for start in range(0, len(encoded), size):
                        self.wfile.write(encoded[start : start + size])
                        self.wfile.flush()
                        time.sleep(0.3)
                else:
                    self.wfile.write(encoded[: len(encoded) // 2])
                    self.wfile.flush()
                    self.close_connection = True
            else:
                self.wfile.write(encoded)

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"HTTP fault fixture ready on {port}", flush=True)
    server.serve_forever()


def verify(port, case):
    Path("results").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="b-http-check-") as directory:
        path = Path(directory) / "requests.jsonl"
        client = HTTPClient(f"http://127.0.0.1:{port}", "local-regression", str(path))
        try:
            client.act("/enter")
            if case == "deadline":
                client._ACTION_RETRY_BUDGET_S = 0.5
                started = time.monotonic()
                try:
                    client.act("/measure", (300.0, 400.0), 1)
                except AmbiguousActionError:
                    elapsed = time.monotonic() - started
                else:
                    raise AssertionError("Slow response bypassed the absolute deadline")
                assert elapsed < 1.5, elapsed
                assert client.virtual_time_s == 0
                try:
                    client.act("/measure", (0.0, 0.0), 2)
                except AmbiguousActionError:
                    pass
                else:
                    raise AssertionError(
                        "Different action sent after an ambiguous timeout"
                    )
                result = {
                    "evidence": "local_HTTP_fault_fixture_not_official",
                    "absolute_deadline_fail_closed": True,
                    "deadline_s": 0.5,
                    "observed_elapsed_s": elapsed,
                    "no_unconfirmed_state_advance": True,
                }
                output = Path("results/http_deadline_verification.json")
            else:
                assert (
                    client.act("/measure", (300.0, 400.0), 1)["virtual_time_s"] == 105
                )
                assert (
                    client.act("/measure", (300.0, 400.0), 2)["virtual_time_s"] == 111
                )
                clear = client.act("/clear", (300.0, 0.0), 3)
                expected = 196 if clear["clear_result"] == "success" else 194
                assert clear["virtual_time_s"] == expected
                assert client.radio_channel == 2
                assert (
                    client.act("/measure", (300.0, 0.0), 2)["virtual_time_s"]
                    == expected + 5
                )
                assert client.act("/exit")["virtual_time_s"] == expected + 5
                result = {
                    "evidence": "local_HTTP_fault_fixture_not_official",
                    "truncated_response_recovered": True,
                    "retry_reused_identical_request": True,
                    "virtual_time_exactly_once": True,
                    "clear_kept_radio_channel": True,
                    "final_virtual_time_s": expected + 5,
                }
                output = Path("results/http_verification.json")
        finally:
            client.close()
        events = [json.loads(line) for line in path.read_text().splitlines()]
        requests = [
            row
            for row in events
            if row["event"] == "request" and row["path"] == "/measure"
        ]
        if case == "deadline":
            assert len(requests) == 1
        else:
            assert requests[0]["request_id"] == requests[1]["request_id"]
            assert requests[0]["body"] == requests[1]["body"]
        output.write_text(json.dumps(result, indent=2) + "\n")
        output.with_suffix(".jsonl").write_text(path.read_text())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--port", type=int, default=12026)
    parser.add_argument(
        "--case", choices=("truncated", "deadline"), default="truncated"
    )
    arguments = parser.parse_args()
    serve(arguments.port, arguments.case) if arguments.server else verify(
        arguments.port, arguments.case
    )
