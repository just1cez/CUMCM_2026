"""Checked field-policy assets; official observations and synthetic gains stay separate."""

from __future__ import annotations
from collections import defaultdict
import hashlib
import json
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from field_study import pair_stats, summarize
from make_assets import (
    ROOT,
    GENERATED,
    atomic_bytes,
    table,
    number,
    save_figure,
    write_json,
)
from make_research_assets import checked_rows

LABELS = {
    "control": "原refined",
    "route_only": "仅路线改进",
    "route_info": "路线与信息",
    "field": "新field",
}


def main():
    data = json.loads((ROOT / "results/field_confirmation.json").read_text())
    development = json.loads((ROOT / "results/field_development.json").read_text())
    official = json.loads(
        (ROOT / "results/official_practice_analysis.json").read_text()
    )
    assert data["total_runs"] == 9400 and development["total_runs"] == 2250
    checked_rows(data)
    checked_rows(development)
    groups = defaultdict(list)
    for row in data["runs"]:
        groups[
            row["problem"],
            row["scenario"],
            row["error_mode"],
            row["configuration"],
            row["seed"] // 10000,
        ].append(row)
    main_groups = {}
    comparison_rows = []
    cost_rows = []
    macros = []
    ablation = []
    for p in (3, 4):
        names = (
            ("control", "route_only", "route_info", "field")
            if p == 3
            else ("control", "field")
        )
        for name in names:
            group = groups[p, "random", "smooth", name, 710]
            assert [r["seed"] for r in group] == list(range(7100000, 7101000))
            summary = summarize(group)
            assert summary == data["summary"][f"Q{p}_{name}"]
            main_groups[p, name] = group
            comparison_rows.append(
                [
                    f"Q{p}",
                    LABELS[name],
                    number(summary["mean"]),
                    number(summary["p90"]),
                    number(summary["worst"]),
                    f"{summary['all_clear']}/1000",
                ]
            )
            if name in ("control", "field"):
                # Recover the charged movement component from the independently
                # verified total and integer action costs, retaining microsecond rounding.
                costs = [
                    statistics.mean(
                        (
                            r["virtual_time_s"]
                            - 5 * r["measures"]
                            - r["switches"]
                            - 3 * r["failed_clears"]
                            - 5 * r["n_cleared"]
                        )
                        / r["n_sources"]
                        for r in group
                    ),
                    statistics.mean(5 * r["measures"] / r["n_sources"] for r in group),
                    statistics.mean(r["switches"] / r["n_sources"] for r in group),
                    statistics.mean(
                        3 * r["failed_clears"] / r["n_sources"] for r in group
                    ),
                    5.0,
                ]
                assert abs(sum(costs) - summary["mean"]) < 1e-9
                cost_rows.append(
                    [
                        f"Q{p}",
                        LABELS[name],
                        *[number(v) for v in costs],
                        number(summary["mean"]),
                    ]
                )
        pair = pair_stats(main_groups[p, "control"], main_groups[p, "field"])
        assert pair == data["comparison"][f"Q{p}"]
        word = "Three" if p == 3 else "Four"
        s = data["summary"][f"Q{p}_field"]
        macros.extend(
            [
                (f"FieldQ{word}Time", number(s["mean"])),
                (
                    f"FieldQ{word}Control",
                    number(data["summary"][f"Q{p}_control"]["mean"]),
                ),
                (f"FieldQ{word}Gain", number(pair["saving_pct"])),
                (f"FieldQ{word}Saved", number(pair["mean_saved_s"])),
                (f"FieldQ{word}Lower", number(pair["approx_95pct_ci"][0])),
                (f"FieldQ{word}Upper", number(pair["approx_95pct_ci"][1])),
                (f"FieldQ{word}Faster", str(pair["faster_cases"])),
                (f"FieldQ{word}Wall", f"{s['max_real_s']:.3f}"),
            ]
        )
        for a, b in zip(names, names[1:]):
            values = pair_stats(main_groups[p, a], main_groups[p, b])
            ablation.append(
                [
                    f"Q{p}",
                    LABELS[a] + "至" + LABELS[b],
                    number(values["mean_saved_s"]),
                    "["
                    + number(values["approx_95pct_ci"][0])
                    + ", "
                    + number(values["approx_95pct_ci"][1])
                    + "]",
                ]
            )
    macros.extend([("FieldRuns", "9400"), ("FieldDevelopmentRuns", "2250")])
    atomic_bytes(
        GENERATED / "field_numbers.tex",
        (
            "\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k, v in macros) + "\n"
        ).encode(),
    )
    table(
        "field_comparison.tex",
        ["问题", "策略", "均值", "$p_{90}$", "最坏", "全清"],
        comparison_rows,
    )
    table(
        "field_costs.tex",
        ["问题", "策略", "移动", "检测", "换频", "失败清除", "成功清除", "合计"],
        cost_rows,
    )
    table(
        "field_ablation.tex",
        ["问题", "相邻配置", "节省均值", r"近似95\%区间"],
        ablation,
    )
    stress_rows = []
    for key, item in data["stress"].items():
        p = int(key[1])
        scenario = next(
            s
            for s in ("minimum_radius", "outward_boundary", "clustered", "random")
            if key.startswith(f"Q{p}_{s}_")
        )
        mode = key[len(f"Q{p}_{scenario}_") :]
        seed_prefix = 721 if scenario == "random" else 720
        a = groups[p, scenario, mode, "control", seed_prefix]
        b = groups[p, scenario, mode, "field", seed_prefix]
        assert pair_stats(a, b) == item["paired"]
        assert summarize(a) == item["control"] and summarize(b) == item["field"]
        labels = {
            "minimum_radius": "最小半径",
            "outward_boundary": "边界外向",
            "clustered": "聚集",
            "random": "随机",
        }
        modes = {"smooth": "平滑", "extreme": "端点", "iid_location": "位置哈希"}
        stress_rows.append(
            [
                f"Q{p}",
                labels[scenario],
                modes[mode],
                str(len(a)),
                number(item["paired"]["mean_saved_s"]),
                "["
                + number(item["paired"]["approx_95pct_ci"][0])
                + ", "
                + number(item["paired"]["approx_95pct_ci"][1])
                + "]",
                f"{item['paired']['faster_cases']}/{len(a)}",
            ]
        )
    table(
        "field_stress.tex",
        ["问题", "场景", "误差", "配对数", "节省", r"近似95\%区间", "更快"],
        stress_rows,
    )
    # Official evidence has no new field outcomes; plot only actual cost shares.
    official_rows = []
    for p in (3, 4):
        s = official["summary"][str(p)]
        official_rows.append(
            [
                f"Q{p}",
                "10",
                str(s["source_total"]),
                number(s["mean_per_source_s"]),
                number(s["weighted_s_per_source"]),
                number(100 * s["cost_fractions"]["move_time_s"]),
                number(s["mean_measures"]),
            ]
        )
    table(
        "official_cost_summary.tex",
        ["问题", "局数", "全清源数", "局等权T/K", "汇总T/K", "移动占比/\%", "检测/局"],
        official_rows,
    )
    plt.rcParams.update({"font.size": 10, "pdf.fonttype": 42})
    fig, axes = plt.subplots(1, 2, figsize=(16 / 2.54, 3.3), layout="constrained")
    for p, ax in zip((3, 4), axes):
        for name, color in [("control", "#0072B2"), ("field", "#D55E00")]:
            values = sorted(r["average_time_s"] for r in main_groups[p, name])
            ax.plot(
                values,
                np.arange(1, len(values) + 1) / len(values),
                label="refined" if name == "control" else "field",
                color=color,
            )
        ax.set(
            title=f"Q{p}: 1,000 fresh paired worlds",
            xlabel="Full virtual time / source (s)",
            ylabel="Empirical cumulative probability",
            ylim=(0, 1),
        )
        ax.legend(loc="lower right")
        ax.grid(alpha=0.2)
    save_figure(fig, "field_performance.pdf")
    inputs = [
        "results/field_confirmation.json",
        "results/field_development.json",
        "results/field_verification.json",
        "results/official_practice_analysis.json",
        "field_policy.py",
        "negative_geometry.py",
        "route_portfolio.py",
        "field_study.py",
        "field_confirmation.py",
        "official_analysis.py",
        "make_field_assets.py",
        "planner.py",
        "geometry.py",
    ]
    write_json(
        "field_metadata.json",
        {
            "evidence": data["evidence"],
            "official_calls_by_generator": 0,
            "official_practice_runs_analyzed": 20,
            "field_main_worlds_per_problem": 1000,
            "field_confirmation_runs": 9400,
            "field_development_runs": 2250,
            "main_comparison": data["comparison"],
            "input_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in inputs
            },
        },
    )
    print(
        json.dumps(
            {
                "confirmation_runs": 9400,
                "development_runs": 2250,
                "main": data["comparison"],
                "official_runs": 20,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
