"""Run local synthetic practice; official GUI sessions require client.HTTPClient separately."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from environment import LocalSimulator
from planner import Planner


def run_local(
    seed: int,
    problem: int,
    scenario: str = "random",
    error_mode: str = "smooth",
    strategy: str = "enhanced",
) -> dict:
    env = LocalSimulator(
        seed, problem=problem, scenario=scenario, error_mode=error_mode
    )
    planner = Planner(env, problem=problem, strategy=strategy)
    planner_result = planner.run()
    result = {"planner": planner_result, "simulator": env.summary()}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--problem", type=int, choices=(3, 4), default=3)
    parser.add_argument("--scenario", default="random")
    parser.add_argument("--error-mode", default="smooth")
    parser.add_argument(
        "--strategy",
        choices=("baseline", "batched", "integrated", "enhanced"),
        default="enhanced",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_local(
        args.seed, args.problem, args.scenario, args.error_mode, args.strategy
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
