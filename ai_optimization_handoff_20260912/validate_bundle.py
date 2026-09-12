"""Read-only integrity checks for the Q3/Q4 AI optimization handoff bundle."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPECTED_ROBOT_ID = "TEAM_REDACTED"


def robot_ids(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "robot_id":
                yield child
            yield from robot_ids(child)
    elif isinstance(value, list):
        for child in value:
            yield from robot_ids(child)


def main() -> None:
    with (ROOT / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 20, f"expected 20 manifest rows, got {len(rows)}"
    assert {(int(r["problem"]), int(r["round"])) for r in rows} == {
        (problem, round_no) for problem in (3, 4) for round_no in range(1, 11)
    }
    assert len({r["case_code"] for r in rows}) == 20
    assert len({r["simulator_result"] for r in rows}) == 20

    aggregates = defaultdict(lambda: {"cleared": 0, "virtual_time_s": 0.0})
    total_records = 0

    for row in rows:
        problem = int(row["problem"])
        request_path = ROOT / row["private_requests"]
        observed_path = ROOT / row["observed_result"]
        simulator_path = ROOT / row["simulator_result"]
        assert request_path.is_file(), request_path
        assert observed_path.is_file(), observed_path
        assert simulator_path.is_file(), simulator_path

        observed = json.loads(observed_path.read_text(encoding="utf-8"))
        simulator = json.loads(simulator_path.read_text(encoding="utf-8"))
        cleared = int(observed["n_cleared"])
        source_count = int(simulator["jammer_count"])

        assert int(observed["problem"]) == problem
        assert int(simulator["problem_no"]) == problem
        assert simulator["case_code"] == row["case_code"]
        assert str(simulator["practice_run_no"]) == row["practice_run_no"]
        assert source_count == int(row["source_count"])
        assert cleared == int(row["cleared"]) == source_count
        assert observed["certificate_complete"] is True
        assert math.isclose(
            float(observed["average_time_s"]),
            float(observed["virtual_time_s"]) / cleared,
            rel_tol=0.0,
            abs_tol=1e-9,
        )

        run_records = 0
        found_redacted_id = False
        with request_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                record = json.loads(line)
                run_records += 1
                for value in robot_ids(record):
                    assert value == EXPECTED_ROBOT_ID, (
                        f"unexpected robot_id in {request_path}:{line_no}"
                    )
                    found_redacted_id = True
        assert run_records > 0, f"empty request log: {request_path}"
        assert found_redacted_id, f"no redacted robot_id in {request_path}"
        total_records += run_records

        aggregates[problem]["cleared"] += cleared
        aggregates[problem]["virtual_time_s"] += float(observed["virtual_time_s"])

    for problem in (3, 4):
        item = aggregates[problem]
        weighted_average = item["virtual_time_s"] / item["cleared"]
        print(
            f"Q{problem}: 10 runs, {item['cleared']} / {item['cleared']} cleared, "
            f"weighted average {weighted_average:.6f} s"
        )
    print(f"Validated 20 runs and {total_records} JSONL records; bundle is complete.")


if __name__ == "__main__":
    main()
