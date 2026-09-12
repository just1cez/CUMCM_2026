"""Connect the policy to an already started OFFICIAL simulator session.

Never starts a formal test or supplies team credentials automatically. Use the
real GUI to choose the intended practice/formal module, then invoke this CLI.
Plaintext request logs include robot_id and are private working files: do not
put them unredacted in anonymous submission. Official encrypted logs are exported
separately from the simulator with unchanged filenames.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

from client import HTTPClient
from field_policy import FieldPlanner
from planner import Planner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-id", required=True)
    parser.add_argument("--problem", required=True, type=int, choices=(3, 4))
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument(
        "--strategy",
        choices=("field", "refined"),
        default="field",
        help="field: new policy; refined: unchanged controller used in the 20 practice runs",
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
        planner = (
            FieldPlanner(client, problem=args.problem)
            if args.strategy == "field"
            else Planner(client, problem=args.problem, strategy="refined")
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
