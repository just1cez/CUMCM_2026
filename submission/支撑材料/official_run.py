

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

from submission.支撑材料.client import HTTPClient
from submission.支撑材料.field_policy import FieldPlanner
from submission.支撑材料.planner import Planner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", required=True)
    parser.add_argument("--problem", required=True, type=int, choices=(3, 4))
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument(
        "--strategy",
        choices=("field", "refined"),
        default=None,
        help="默认Q3使用refined、Q4使用field；可显式指定任一策略",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory must be new to keep separate session evidence")
    args.output_dir.mkdir(parents=True)
    client = HTTPClient(
        args.base_url, args.robot_id, str(args.output_dir / "private_requests.jsonl")
    )
    started = monotonic()
    try:
        effective_strategy = args.strategy if args.strategy is not None else ("refined" if args.problem == 3 else "field")
        planner = (
            FieldPlanner(client, problem=args.problem)
            if effective_strategy == "field"
            else Planner(client, problem=args.problem, strategy=effective_strategy)
        )
        result = planner.run()
        result.update(
            evidence="HTTP_observations_require_simulator_GUI_provenance_not_encrypted_export",
            local_wall_duration_s=monotonic() - started,
            case_code="Obtain actual case code from simulator GUI; not returned by HTTP",
            total_source_count="Not disclosed by official formal interface",
        )
        (args.output_dir / "observed_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
