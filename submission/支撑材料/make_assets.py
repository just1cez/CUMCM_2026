"""Deterministic local-evidence assets; run with conda run -n py314 python make_assets.py.

No official service is accessed. Replay logs contain public observations, not source
coordinates. Wall-clock durations in raw replay evidence are inherently variable;
figures, table values, and virtual-time paths do not depend on those durations.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Polygon

from submission.支撑材料.coverage import directional_waypoints, omni_waypoints
from submission.支撑材料.environment import LocalSimulator
from submission.支撑材料.geometry import BEARING_ERROR_DEG, clip_bearing, enclosing_circle, initial_polygon
from submission.支撑材料.planner import Planner

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "report" / "generated"
FIGURES = ROOT / "report" / "figures"
POLICIES = ("baseline", "batched", "integrated")
SCENARIOS = ("random", "minimum_radius", "outward_boundary", "clustered")
SCENARIO_LABELS = ("Random", "Min. radius", "Outward boundary", "Clustered")
COLORS = ("#0072B2", "#E69F00", "#009E73")
WIDTH = 16 / 2.54


def require(condition, message):
    if not condition:
        raise ValueError(message)


def atomic_bytes(path, content):
    """Replace only our named outputs; never remove/rewrite source evidence."""
    require(path.parent in (GENERATED, FIGURES), "Output outside owned directories")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(name, value):
    atomic_bytes(
        GENERATED / name,
        (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8"),
    )


def save_figure(fig, name):
    # Fixed physical width, not bbox_inches=tight (which changes final font scale).
    from io import BytesIO

    buffer = BytesIO()
    fig.savefig(
        buffer,
        format="pdf",
        metadata={"CreationDate": None, "ModDate": None, "Creator": "make_assets.py"},
    )
    atomic_bytes(FIGURES / name, buffer.getvalue())
    plt.close(fig)


def tex_escape(value):
    return str(value).replace("_", r"\_").replace("%", r"\%")


def table(name, headers, rows, alignment=None):
    alignment = alignment or "l" + "r" * (len(headers) - 1)
    lines = [
        r"\begin{tabular}{" + alignment + "}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        require(len(row) == len(headers), "Ragged table")
        lines.append(" & ".join(str(v) for v in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    atomic_bytes(GENERATED / name, ("\n".join(lines) + "\n").encode("utf-8"))


def number(value):
    require(
        isinstance(value, (int, float)) and math.isfinite(value), "Nonfinite metric"
    )
    return f"{value:.2f}"


def metrics(rows):
    values = sorted(row["average_time_s"] for row in rows)
    require(bool(values), "Empty evidence group")
    return {
        "cases": len(rows),
        "all_cleared_cases": sum(r["fraction_cleared"] == 1 for r in rows),
        "mean_average_time_s": statistics.mean(values),
        "median_average_time_s": statistics.median(values),
        "p90_average_time_s": values[math.ceil(0.9 * len(values)) - 1],
        "mean_failed_clears": statistics.mean(r["failed_clears"] for r in rows),
    }


def validate_group(rows, summary, name):
    actual = metrics(rows)
    for key, value in actual.items():
        require(
            key in summary
            and math.isclose(value, summary[key], rel_tol=1e-10, abs_tol=1e-8),
            f"{name}: summary mismatch for {key}",
        )
    return rows


def load_inputs():
    names = (
        "final_experiments.json",
        "geometry_verification.json",
        "http_verification.json",
        "second_point_example.json",
    )
    data, hashes = {}, {}
    for name in names:
        raw = (ROOT / "results" / name).read_bytes()
        data[name] = json.loads(raw)
        hashes["results/" + name] = hashlib.sha256(raw).hexdigest()
    final = data[names[0]]
    require(
        final["evidence"] == "local_synthetic_not_official", "Not synthetic evidence"
    )
    require(final["total_runs"] == len(final["runs"]), "Run denominator mismatch")
    for row in final["runs"]:
        require(
            row["evidence"] == "local_synthetic_not_official"
            and row["fraction_cleared"] == 1,
            "Incomplete or wrongly attributed run",
        )
        require(row["n_sources"] == row["n_cleared"] > 0, "Invalid clearing count")
        require(
            math.isclose(
                row["average_time_s"],
                row["virtual_time_s"] / row["n_sources"],
                rel_tol=1e-10,
            ),
            "Metric is not per-world T/N",
        )
        require(row["timing_independently_verified"] is True, "Missing timing evidence")
        require(row["certificate_complete"] is True, "Missing complete certificate")
        require(row["loss_recovery"] is (row["problem"] == 4 and row.get("loss_recovery_requested", True)),
                "Effective recovery mismatch")
    main, recovery = {}, {}
    n = final["paired_random_cases_per_problem"]
    for problem in (3, 4):
        for strategy in POLICIES:
            key = f"Q{problem}_{strategy}"
            rows = sorted(
                (
                    r
                    for r in final["runs"]
                    if r["problem"] == problem
                    and r["strategy"] == strategy
                    and 600000 <= r["seed"] < 600000 + n
                ),
                key=lambda r: r["seed"],
            )
            require(
                [r["seed"] for r in rows] == list(range(600000, 600000 + n)),
                "Missing/duplicate paired seed",
            )
            main[key] = validate_group(rows, final["summary"][key], key)
        paired = final["paired_comparison"][f"Q{problem}"]
        saved = statistics.mean(
            a["average_time_s"] - b["average_time_s"]
            for a, b in zip(
                main[f"Q{problem}_baseline"], main[f"Q{problem}_integrated"]
            )
        )
        require(
            paired["paired_cases"] == n
            and math.isclose(saved, paired["mean_saved_s_per_source"], rel_tol=1e-10),
            "Pairing mismatch",
        )
        require(
            math.isclose(
                paired["mean_time_reduction_pct"],
                100
                * saved
                / final["summary"][f"Q{problem}_baseline"]["mean_average_time_s"],
                rel_tol=1e-10,
            ),
            "Gain mismatch",
        )
        for scenario in SCENARIOS[1:]:
            for mode in ("smooth", "extreme", "iid_location"):
                key = f"Q{problem}_{scenario}_{mode}"
                rows = [
                    r
                    for r in final["runs"]
                    if r["problem"] == problem
                    and r["scenario"] == scenario
                    and r["error_mode"] == mode
                    and 700000 <= r["seed"] < 700020
                ]
                validate_group(rows, final["stress"][key], key)
        for scale in (0.12, 0.22, 0.40):
            key = f"Q{problem}_probe_{scale}"
            rows = [
                r
                for r in final["runs"]
                if r["problem"] == problem
                and r["probe_scale"] == scale
                and 800000 <= r["seed"] < 800030
            ]
            validate_group(rows, final["sensitivity"][key], key)
    for spacing in (900.0, 950.0, 990.0):
        key = f"Q4_spacing_{spacing}"
        rows = [
            r
            for r in final["runs"]
            if r["problem"] == 4
            and r["spacing_m"] == spacing
            and 900000 <= r["seed"] < 900030
        ]
        validate_group(rows, final["sensitivity"][key], key)
    for scenario in SCENARIOS:
        for enabled in (False, True):
            key = f"{scenario}_recovery_{enabled}"
            rows = sorted(
                (
                    r
                    for r in final["runs"]
                    if r["problem"] == 4
                    and r["scenario"] == scenario
                    and r["loss_recovery"] is enabled
                    and 610000 <= r["seed"] < 610100
                ),
                key=lambda r: r["seed"],
            )
            require(
                [r["seed"] for r in rows] == list(range(610000, 610100)),
                "Recovery pairing mismatch",
            )
            recovery[key] = validate_group(rows, final["recovery_ablation"][key], key)
    geometry, http, second = (data[name] for name in names[1:])
    require(
        geometry["evidence"]
        == "independent_numerical_checks_not_a_substitute_for_analytic_proofs",
        "Geometry evidence mismatch",
    )
    require(
        http["evidence"] == "local_HTTP_fault_fixture_not_official",
        "HTTP evidence mismatch",
    )
    require(
        second["evidence"] == "illustrative_Q2_grid_score_not_global_optimum",
        "Q2 evidence mismatch",
    )
    for key in (
        "truncated_response_recovered",
        "retry_reused_identical_request",
        "virtual_time_exactly_once",
        "clear_kept_radio_channel",
    ):
        require(http[key] is True, f"Failed fixture: {key}")
    return final, geometry, http, second, main, recovery, hashes


def generate_tables(final, geometry, http):
    summary = final["summary"]
    macros = {"ExperimentRuns": str(final["total_runs"])}
    for problem, word in ((3, "Three"), (4, "Four")):
        macros[f"Q{word}Time"] = number(
            summary[f"Q{problem}_integrated"]["mean_average_time_s"]
        )
        macros[f"Q{word}Baseline"] = number(
            summary[f"Q{problem}_baseline"]["mean_average_time_s"]
        )
        # Numeric macro: paper supplies its own percent sign and unit.
        macros[f"Q{word}Gain"] = number(
            final["paired_comparison"][f"Q{problem}"]["mean_time_reduction_pct"]
        )
    atomic_bytes(
        GENERATED / "numbers.tex",
        (
            "\n".join(
                r"\newcommand{" + "\\" + k + "}{" + v + "}" for k, v in macros.items()
            )
            + "\n"
        ).encode(),
    )
    rows = []
    for problem in (3, 4):
        for policy in POLICIES:
            s = summary[f"Q{problem}_{policy}"]
            rows.append(
                (
                    f"Q{problem} {policy}",
                    number(s["mean_average_time_s"]),
                    number(s["median_average_time_s"]),
                    number(s["p90_average_time_s"]),
                    f"{s['all_cleared_cases']}/{s['cases']}",
                )
            )
    table(
        "comparison_table.tex",
        ("Policy", r"Mean $T/N$ (s)", "Median (s)", "$p_{90}$ (s)", "Complete"),
        rows,
    )
    rows = []
    for scenario, label in zip(SCENARIOS[1:], SCENARIO_LABELS[1:]):
        for mode, mode_label in (
            ("smooth", "Smooth"),
            ("extreme", r"$\pm1^\circ$ hash"),
            ("iid_location", "Uniform hash"),
        ):
            s3, s4 = (final["stress"][f"Q{p}_{scenario}_{mode}"] for p in (3, 4))
            require(s3["cases"] == s4["cases"], "Stress denominator mismatch")
            rows.append(
                (
                    label,
                    mode_label,
                    number(s3["mean_average_time_s"]),
                    number(s4["mean_average_time_s"]),
                    str(s3["cases"]),
                )
            )
    table(
        "stress_table.tex",
        ("Geometry", "Error field", "Q3 mean (s)", "Q4 mean (s)", "$n$/Q"),
        rows,
        "llrrr",
    )
    rows = []
    for key, s in final["sensitivity"].items():
        problem, parameter, value = key.split("_")
        label = (
            r"$\lambda=" + value + "$"
            if parameter == "probe"
            else "$s=" + f"{float(value):.0f}" + r"\,\mathrm{m}$"
        )
        rows.append(
            (
                problem,
                label,
                number(s["mean_average_time_s"]),
                number(s["p90_average_time_s"]),
                str(s["cases"]),
            )
        )
    table(
        "sensitivity_table.tex",
        ("Problem", "Setting", "Mean (s)", "$p_{90}$ (s)", "$n$"),
        rows,
        "llrrr",
    )
    rows = []
    for scenario, label in zip(SCENARIOS, SCENARIO_LABELS):
        off, on = (
            final["recovery_ablation"][f"{scenario}_recovery_{enabled}"]
            for enabled in (False, True)
        )
        rows.append(
            (
                label,
                number(off["mean_average_time_s"]),
                number(on["mean_average_time_s"]),
                number(off["mean_failed_clears"]),
                number(on["mean_failed_clears"]),
                str(on["cases"]),
            )
        )
    table(
        "recovery_table.tex",
        ("Scenario", "$T/N$ off", "$T/N$ on", "Fails off", "Fails on", "Pairs"),
        rows,
    )
    rows = [
        (
            "MEC reference",
            str(geometry["mec_reference_cases"]),
            f"{geometry['maximum_mec_radius_error_m']:.2e} m",
        ),
        (
            "Bearing containment",
            str(geometry["containment_cases"]),
            f"{geometry['bearings_per_case']} readings/case",
        ),
        (
            "Optical cover samples",
            str(geometry["optical_interior_samples"]),
            "Contained",
        ),
        (
            "Discovery samples",
            str(geometry["coverage_source_samples"]),
            "Both geometries",
        ),
        (
            "Triple-lens samples",
            str(geometry["triple_lens_samples"]),
            "Reception checked",
        ),
        ("Local HTTP fixture", "1", "Four checks passed"),
    ]
    table(
        "verification_table.tex",
        ("Numerical / local check", "Cases / points", "Observed result"),
        rows,
        "lrl",
    )


def spatial_axis(ax, limit, unit="km"):
    ax.set(
        xlim=(-limit, limit),
        ylim=(-limit, limit),
        xlabel=f"x ({unit})",
        ylabel=f"y ({unit})",
        aspect="equal",
    )
    ax.grid(alpha=0.18)


def coverage_figure(geometry):
    cert = geometry["coverage_certificate"]
    omni, lattice = np.array(omni_waypoints()), np.array(directional_waypoints())
    require(
        len(omni) == cert["omni"]["waypoint_count"]
        and len(lattice) == cert["directional"]["waypoint_count"],
        "Coverage count mismatch",
    )
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.7))
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.30, top=0.88, wspace=0.4)
    for ax in axes:
        spatial_axis(ax, 3.0)
        ax.add_patch(
            Circle(
                (0, 0), cert["arena_radius_m"] / 1000, fill=False, color="black", lw=1.3
            )
        )
    for point in omni / 1000:
        axes[0].add_patch(
            Circle(
                point,
                cert["omni"]["cover_radius_m"] / 1000,
                color=COLORS[0],
                fill=False,
                alpha=0.6,
                lw=0.8,
            )
        )
    axes[0].scatter(
        *(omni / 1000).T, s=20, color=COLORS[0], label=f"{len(omni)} detectors"
    )
    inside = np.linalg.norm(lattice, axis=1) <= cert["arena_radius_m"]
    require(
        int((~inside).sum()) == cert["directional"]["outside_arena_count"],
        "Outside-node count mismatch",
    )
    # Draw only nearest-neighbour lattice edges, including exterior nodes.
    for i, p in enumerate(lattice):
        for q in lattice[:i]:
            if math.isclose(
                math.dist(p, q), cert["directional"]["spacing_m"], abs_tol=1e-6
            ):
                axes[1].plot(
                    [p[0] / 1000, q[0] / 1000],
                    [p[1] / 1000, q[1] / 1000],
                    color="0.78",
                    lw=0.6,
                    zorder=0,
                )
    axes[1].scatter(
        *(lattice[inside] / 1000).T,
        color=COLORS[0],
        s=22,
        label=f"Inside: {int(inside.sum())}",
    )
    axes[1].scatter(
        *(lattice[~inside] / 1000).T,
        color="#D55E00",
        marker="^",
        s=30,
        label=f"Outside: {int((~inside).sum())}",
    )
    axes[0].set_title("Q3: 900 m covering disks")
    axes[1].set_title(f"Q4: {len(lattice)} lattice nodes")
    for ax in axes:
        box = ax.get_position()
        ax.legend(loc="lower center", bbox_to_anchor=((box.x0 + box.x1) / 2, 0.01),
                  bbox_transform=fig.transFigure, frameon=False)
    save_figure(fig, "coverage.pdf")


def geometry_figure(geometry):
    example = geometry["realizable_counterexample"]
    polygon = initial_polygon()
    for station, bearing in zip(example["stations"], example["bearings_deg"]):
        polygon = clip_bearing(polygon, tuple(station), bearing, error_deg=1.0)
    center, radius = enclosing_circle(polygon)
    require(
        math.isclose(radius, example["mec_radius_m"], abs_tol=1e-6),
        "Triangle reconstruction mismatch",
    )
    a, b = max(
        ((a, b) for a in polygon for b in polygon), key=lambda pair: math.dist(*pair)
    )
    midpoint = tuple((x + y) / 2 for x, y in zip(a, b))
    fig, ax = plt.subplots(figsize=(WIDTH, 3.6), layout="constrained")
    ax.add_patch(Polygon(polygon, facecolor="#56B4E9", alpha=0.35, edgecolor=COLORS[0]))
    ax.plot(
        *zip(*(polygon + [polygon[0]])),
        color=COLORS[0],
        label=f"Feasible region: D={example['diameter_m']:.0f} m",
    )
    ax.add_patch(
        Circle(
            midpoint,
            example["diameter_m"] / 2,
            fill=False,
            color="#D55E00",
            ls="--",
            label=f"Diameter circle: {example['diameter_m'] / 2:.2f} m",
        )
    )
    ax.add_patch(
        Circle(
            center,
            radius,
            fill=False,
            color=COLORS[2],
            lw=1.5,
            label=f"MEC: {radius:.2f} m > 20 m",
        )
    )
    ax.scatter(*center, color=COLORS[2], marker="+", s=60)
    ax.set(
        xlim=(-9, 49), ylim=(-22, 40), xlabel="x (m)", ylabel="y (m)", aspect="equal"
    )
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    ax.grid(alpha=0.2)
    save_figure(fig, "geometry.pdf")


def second_point_figure(second):
    require(
        second["first_station"] == [0, 0] and second["first_reading_deg"] == 0,
        "Q2 figure expects normalized illustrative case",
    )
    alpha = math.radians(BEARING_ERROR_DEG)
    centers = np.array(
        [
            (0, 0),
            (1000 * math.cos(alpha), 1000 * math.sin(alpha)),
            (1000 * math.cos(alpha), -1000 * math.sin(alpha)),
        ]
    )
    t = np.linspace(0, 1000, 1001)
    lower = np.full_like(t, -np.inf)
    upper = np.full_like(t, np.inf)
    for x, y in centers:
        h = np.sqrt(np.maximum(0, 1000**2 - (t - x) ** 2))
        lower, upper = np.maximum(lower, y - h), np.minimum(upper, y + h)
    mask = lower <= upper
    fig, ax = plt.subplots(figsize=(WIDTH, 3.6), layout="constrained")
    ax.fill_between(
        t,
        lower,
        upper,
        where=mask,
        color="#56B4E9",
        alpha=0.35,
        label="Triple-disk reception lens",
    )
    ax.plot(t[mask], lower[mask], color=COLORS[0])
    ax.plot(t[mask], upper[mask], color=COLORS[0])
    candidates = second["candidates"]
    ax.scatter(
        [c["t_m"] for c in candidates],
        [c["b_m"] for c in candidates],
        color="0.55",
        marker=".",
        s=12,
        label="Finite candidate grid",
    )
    for key, label, marker, color in (
        ("best_sampled_geometry", "Sampled choice", "*", COLORS[2]),
        ("collinear_control", "Collinear control", "s", "#D55E00"),
    ):
        c = second[key]
        require(
            all(math.dist(c["point"], p) <= 1000 + 1e-6 for p in centers),
            "Candidate outside lens",
        )
        ax.scatter(
            c["t_m"],
            c["b_m"],
            s=90,
            marker=marker,
            color=color,
            label=f"{label}\nSampled max R={c['sampled_worst_mec_radius_m']:.2f} m",
        )
    ax.scatter(0, 0, color="black", s=20)
    ax.axhline(0, color="0.6", lw=0.6, ls="--")
    ax.set(
        xlabel="Along first bearing t (m)",
        ylabel="Transverse b (m)",
        xlim=(-40, 1040),
        ylim=(-920, 920),
    )
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    save_figure(fig, "q2_lens.pdf")


def performance_figure(main):
    fig, axes = plt.subplots(
        1, 2, figsize=(WIDTH, 3.7), layout="constrained", sharey=True
    )
    for problem, ax in zip((3, 4), axes):
        for policy, color, style in zip(POLICIES, COLORS, ("-", "--", "-.")):
            rows = main[f"Q{problem}_{policy}"]
            values = sorted(r["average_time_s"] for r in rows)
            ax.step(
                values,
                np.arange(1, len(values) + 1) / len(values),
                where="post",
                color=color,
                ls=style,
                label=policy.capitalize(),
            )
        ax.set(
            title=f"Q{problem}: {len(rows)} matched worlds",
            xlabel="Per-world T/N (s)",
            ylim=(0, 1.02),
        )
        ax.grid(alpha=0.2)
        ax.legend(loc="lower right", frameon=False)
    axes[0].set_ylabel("Empirical cumulative fraction")
    save_figure(fig, "performance.pdf")


def replay_trajectories():
    traces = []
    for problem in (3, 4):
        env = LocalSimulator(
            20260910, problem=problem, error_mode="smooth", scenario="random"
        )
        planner = Planner(
            env, problem=problem, strategy="enhanced", loss_recovery=True
        )
        result = planner.run()
        summary = env.summary()  # Evaluation after termination; never supplied to Planner.
        require(summary["fraction_cleared"] == 1, "Trajectory replay incomplete")
        require(result["certificate_complete"] is True, "Trajectory certificate incomplete")
        points, clears = [[0.0, 0.0]], []
        for event in env.log:
            request, response = event["request"], event["response"]
            if not response["accepted"] or "position" not in request:
                continue
            point = [request["position"]["x"], request["position"]["y"]]
            if point != points[-1]:
                points.append(point)
            if response.get("clear_result") == "success":
                clears.append(
                    {
                        "channel": request["channel"],
                        "point": point,
                        "virtual_time_s": response["virtual_time_s"],
                    }
                )
        require(
            len(clears) == summary["n_cleared"] == result["n_cleared"],
            "Replay clear count mismatch",
        )
        trace = {
            "evidence": "local_synthetic_not_official",
            "seed": 20260910,
            "problem": problem,
            "strategy": "enhanced",
            "scenario": "random",
            "error_mode": "smooth",
            "requested_loss_recovery": True,
            "effective_loss_recovery": problem == 4,
            "point_semantics": "Accepted robot coordinates; successful clear within 20 m, not source coordinates",
            "path": points,
            "successful_clears": clears,
            "planner": result,
            "post_exit_summary": summary,
            "observable_log": env.log,
        }
        write_json(f"trajectory_q{problem}.json", trace)
        traces.append(trace)
    write_json(
        "trajectory_summary.json",
        [
            {k: t[k] for k in ("problem", "seed", "planner", "post_exit_summary")}
            for t in traces
        ],
    )
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.8), layout="constrained")
    limit = max(
        2.0, max(abs(v) / 1000 for t in traces for p in t["path"] for v in p) + 0.15
    )
    for ax, trace in zip(axes, traces):
        path = np.array(trace["path"]) / 1000
        clear = np.array([c["point"] for c in trace["successful_clears"]]) / 1000
        spatial_axis(ax, limit)
        ax.add_patch(Circle((0, 0), 1.8, color="0.5", fill=False, ls="--"))
        ax.plot(*path.T, color=COLORS[0], lw=0.8, label="Accepted path")
        ax.scatter(
            *clear.T,
            color="#D55E00",
            marker="x",
            s=26,
            label="Successful clear",
            zorder=3,
        )
        ax.scatter(0, 0, color="black", marker="s", s=22, label="Start", zorder=4)
        ax.set_title(
            f"Q{trace['problem']}: {len(clear)} clears\nT/N={trace['post_exit_summary']['average_time_s']:.2f} s"
        )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, frameon=False)
    save_figure(fig, "trajectories.pdf")
    return traces


def recovery_figure(final):
    fig, axes = plt.subplots(
        2, 1, figsize=(WIDTH, 5.2), layout="constrained", sharex=True
    )
    x = np.arange(len(SCENARIOS))
    for enabled, offset, color, hatch, label in (
        (False, -0.18, COLORS[0], "//", "Recovery off"),
        (True, 0.18, COLORS[2], "", "Recovery on"),
    ):
        summaries = [
            final["recovery_ablation"][f"{s}_recovery_{enabled}"] for s in SCENARIOS
        ]
        for ax, metric in zip(axes, ("mean_average_time_s", "mean_failed_clears")):
            ax.bar(
                x + offset,
                [s[metric] for s in summaries],
                width=0.34,
                color=color,
                hatch=hatch,
                label=label,
            )
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
    axes[0].set_ylabel("Mean T/N (s)")
    axes[1].set_ylabel("Mean failed clears")
    axes[1].set_xticks(x, SCENARIO_LABELS, rotation=12, ha="right")
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    counts = sorted({v["cases"] for v in final["recovery_ablation"].values()})
    require(len(counts) == 1, "Recovery counts differ")
    axes[0].set_title(f"Q4: {counts[0]} matched worlds per scenario")
    save_figure(fig, "recovery.pdf")


def main():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 10,
            "axes.labelsize": 10,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "pdf.fonttype": 42,
            "savefig.transparent": False,
            "figure.facecolor": "white",
        }
    )
    final, geometry, http, second, main_rows, _recovery_rows, hashes = load_inputs()
    generate_tables(final, geometry, http)
    coverage_figure(geometry)
    geometry_figure(geometry)
    second_point_figure(second)
    performance_figure(main_rows)
    traces = replay_trajectories()
    recovery_figure(final)
    for name in (
        "make_assets.py",
        "planner.py",
        "environment.py",
        "geometry.py",
        "coverage.py",
        "second_point.py",
    ):
        hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    enhancement_input = ROOT / "results" / "enhancement_experiments.json"
    if enhancement_input.exists():
        hashes["results/enhancement_experiments.json"] = hashlib.sha256(enhancement_input.read_bytes()).hexdigest()
    ring_sweep_input = ROOT / "results" / "ring_sweep.json"
    if ring_sweep_input.exists():
        hashes["results/ring_sweep.json"] = hashlib.sha256(ring_sweep_input.read_bytes()).hexdigest()
    write_json(
        "metadata.json",
        {
            "evidence": "local_synthetic_not_official",
            "official_calls": 0,
            "asset_set": "base_comparison_with_enhanced_trajectory",
            "input_sha256": hashes,
            "matplotlib_version": matplotlib.__version__,
            "figures": [
                "coverage.pdf", "geometry.pdf", "q2_lens.pdf", "performance.pdf",
                "trajectories.pdf", "recovery.pdf", "enhancement_geometry.pdf",
                "enhancement_performance.pdf",
            ],
            "tables": [
                "comparison_table.tex", "stress_table.tex", "sensitivity_table.tex",
                "recovery_table.tex", "verification_table.tex", "enhancement_table.tex",
                "enhancement_costs.tex", "enhancement_stress.tex", "candidate_table.tex",
                "coverage_limits_table.tex",
            ],
            "enhancement_metadata": "enhancement_metadata.json",
            "layout": {
                "width_cm": 16,
                "minimum_font_pt": 10,
                "backend": "Agg",
                "format": "vector PDF",
            },
            "metric": "Mean, median and nearest-rank p90 of per-world T/N; never pooled sum(T)/sum(N). Gains are reduction of group means; ECDFs use the same seeds per policy.",
            "denominators": {
                "all_runs_including_paired_repeats": final["total_runs"],
                "main_worlds_per_problem": final["paired_random_cases_per_problem"],
                "trajectory_replays_additional_to_experiments": len(traces),
            },
            "seed_ranges": {
                "main": [600000, 600000 + final["paired_random_cases_per_problem"] - 1],
                "stress": [700000, 700019],
                "probe_sensitivity": [800000, 800029],
                "spacing_sensitivity": [900000, 900029],
                "recovery": [610000, 610099],
                "trajectory": 20260910,
            },
            "parameters": {
                "strategy": "enhanced",
                "anchor_policy_Q3": "nearest",
                "anchor_policy_Q4": "rolling",
                "ring_radius_Q3_m": 1200,
                "spacing_Q4_m": 990,
                "probe_scale": 0.22,
                "max_probes": 6,
                "loss_recovery_Q4": True,
                "bearing_halfwidth_deg": BEARING_ERROR_DEG,
                "Q2_source_samples": second["source_samples"],
                "Q2_second_errors_deg": second["second_error_values_deg"],
                "Q2_optimality": "Finite candidate/sample comparison only, no global or continuous minimax certificate",
            },
            "distributions": {
                "random": "N uniform integer 10..16; distinct channels uniformly sampled; positions iid area-uniform radius-1800 disk; radii uniform [1000,1500]; orientations uniform [0,2pi). Q3 all omni; Q4 uniform directional count 1..N-1 and uniform subset.",
                "minimum_radius": "Random geometry, radio radius exactly 1000 m.",
                "outward_boundary": "16 equally spaced boundary sources with seeded rotation, radius 1000; Q4 15 outward directional and one omni.",
                "clustered": "16 area-uniform sources in radius-35 disk with center at radius1650; radio radius1000.",
            },
            "error_fields": {
                "smooth": "Deterministic bounded two-sinusoid field.",
                "extreme": "Coordinate/seed/channel hash selecting +/-1 degree.",
                "iid_location": "Coordinate/seed/channel hash uniform [-1,1], not independent repeat measurements.",
            },
            "trajectory_evidence": "trajectory_q3.json and trajectory_q4.json preserve complete observable logs, accepted paths, successful robot clearing locations and post-exit aggregate summaries. No hidden source coordinates inspected.",
            "determinism": "PDF creation timestamps suppressed; no random plotting jitter. Raw real-duration/timing observations may vary between replays; figures use virtual time only.",
        },
    )
    print(
        "Generated six local-evidence PDFs, five tabular fragments, numbers.tex, metadata.json and two complete observable replay logs."
    )


if __name__ == "__main__":
    main()
