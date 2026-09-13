
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import tempfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "report" / "generated"
FIGURES = ROOT / "report" / "figures"
WIDTH = 16 / 2.54
POLICIES = ("integrated", "enhanced")
SCENARIOS = ("minimum_radius", "outward_boundary", "clustered")
MODES = ("smooth", "extreme", "iid_location")
COLORS = ("#0072B2", "#D55E00")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, name, tolerance=1e-8):
    require(math.isfinite(actual) and math.isfinite(expected), f"{name}: nonfinite value")
    require(math.isclose(actual, expected, rel_tol=1e-10, abs_tol=tolerance),
            f"{name}: {actual!r} != {expected!r}")


def number(value):
    require(math.isfinite(value), "Nonfinite table value")
    return f"{value:.2f}"


def load(name):
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def atomic_bytes(path, content):
    require(path.parent in (GENERATED, FIGURES), "Output outside owned directories")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def table(name, headers, rows, widths, left_columns=(0, 1)):
    
    require(len(headers) == len(widths), "Invalid table widths")
    require(sum(widths) + 0.14 * (len(widths) - 1) <= 15.9, "Table exceeds 16 cm")
    columns = []
    for index, width in enumerate(widths):
        align = r"\raggedright" if index in left_columns else r"\raggedleft"
        columns.append(">{" + align + r"\arraybackslash}p{" + str(width) + "cm}")
    specification = "@{}" + r"@{\hspace{0.14cm}}".join(columns) + "@{}"
    lines = [r"\begin{tabular}{" + specification + "}", r"\toprule",
             " & ".join(headers) + r" \\", r"\midrule"]
    for row in rows:
        require(len(row) == len(headers), "Ragged table")
        lines.append(" & ".join(str(item) for item in row) + r" \\")
    lines.extend((r"\bottomrule", r"\end{tabular}"))
    atomic_bytes(GENERATED / name, ("\n".join(lines) + "\n").encode("utf-8"))


def save_figure(fig, name):
    buffer = BytesIO()
    fig.savefig(buffer, format="pdf", metadata={"CreationDate": None, "ModDate": None,
                                                "Creator": "make_enhancement_assets.py"})
    atomic_bytes(FIGURES / name, buffer.getvalue())
    plt.close(fig)


def check_run(row):
    for key in ("n_sources", "n_cleared", "measures", "switches", "clear_attempts", "failed_clears"):
        require(type(row[key]) is int and row[key] >= 0, f"Invalid {key}")
    n = row["n_sources"]
    require(n > 0 and row["n_cleared"] <= n, "Invalid per-world denominator")
    require(row["clear_attempts"] == row["n_cleared"] + row["failed_clears"],
            "Clear-attempt decomposition mismatch")
    require(row["distance_m"] >= 0, "Negative distance")
    close(row["fraction_cleared"], row["n_cleared"] / n, "Clear fraction")
    close(row["average_time_s"], row["virtual_time_s"] / n, "Per-world average")
    total = (row["distance_m"] / 5 + 5 * row["measures"] + row["switches"]
             + 3 * row["failed_clears"] + 5 * row["n_cleared"])
    
    rounding_bound = 0.5e-6 * (row["measures"] + row["clear_attempts"]) + 1e-8
    close(total, row["virtual_time_s"], "Independent cost identity", tolerance=rounding_bound)


def metrics(rows):
    require(bool(rows), "Empty group")
    values = sorted(row["average_time_s"] for row in rows)
    return {"cases": len(rows),
            "all_cleared_cases": sum(r["n_cleared"] == r["n_sources"] for r in rows),
            "mean_average_time_s": statistics.mean(values),
            "median_average_time_s": statistics.median(values),
            "p90_average_time_s": values[math.ceil(0.9 * len(values)) - 1]}


def check_summary(actual, summary, name):
    for key, value in actual.items():
        close(value, summary[key], f"{name}/{key}")


def paired(control, enhanced):
    require([r["seed"] for r in control] == [r["seed"] for r in enhanced], "Unpaired seeds")
    for a, b in zip(control, enhanced):
        require(all(a[key] == b[key] for key in
                    ("problem", "scenario", "error_mode", "n_sources")), "Unpaired world metadata")
    delta = [a["average_time_s"] - b["average_time_s"] for a, b in zip(control, enhanced)]
    mean = statistics.mean(delta)
    return delta, {"cases": len(delta), "mean_saved_s_per_source": mean,
                   "mean_reduction_pct": 100 * mean / metrics(control)["mean_average_time_s"],
                   "faster_cases": sum(value > 0 for value in delta)}


def load_enhancement():
    data = load("enhancement_experiments.json")
    require(data["main_seed_range"] == [1100000, 1100499], "Unexpected held-out seeds")
    require(data["stress_seed_range"] == [1110000, 1110029], "Unexpected pressure seeds")
    groups = defaultdict(list)
    for row in data["runs"]:
        check_run(row)
        require(row["strategy"] in POLICIES, "Unexpected enhancement policy")
        groups[(row["problem"], row["scenario"], row["error_mode"], row["strategy"])].append(row)
    expected = {(q, scenario, mode, policy) for q in (3, 4) for policy in POLICIES
                for scenario, mode in [("random", "smooth")] +
                [(s, m) for s in SCENARIOS for m in MODES]}
    require(set(groups) == expected, "Missing or extra enhancement groups")
    for key, rows in groups.items():
        rows.sort(key=lambda r: r["seed"])
        start, end = data["main_seed_range"] if key[1] == "random" else data["stress_seed_range"]
        require([r["seed"] for r in rows] == list(range(start, end + 1)),
                f"{key}: incomplete or duplicate seeds")
    require(len(data["runs"]) == data["total_runs"] == 3080, "Run total mismatch")
    require(set(data["summary"]) == {f"Q{q}_{p}" for q in (3, 4) for p in POLICIES},
            "Unexpected main summary groups")
    require(set(data["comparison"]) == {"Q3", "Q4"}, "Unexpected main comparisons")
    require(set(data["stress"]) == {f"Q{q}_{s}_{m}" for q in (3, 4)
                                    for s in SCENARIOS for m in MODES}, "Expected 18 pressure groups")
    for q in (3, 4):
        controls = groups[q, "random", "smooth", "integrated"]
        enhancements = groups[q, "random", "smooth", "enhanced"]
        for policy in POLICIES:
            check_summary(metrics(groups[q, "random", "smooth", policy]),
                          data["summary"][f"Q{q}_{policy}"], f"Q{q}/{policy}")
        check_summary(paired(controls, enhancements)[1], data["comparison"][f"Q{q}"], f"Q{q}/paired")
        for scenario in SCENARIOS:
            for mode in MODES:
                key = f"Q{q}_{scenario}_{mode}"
                for policy in POLICIES:
                    check_summary(metrics(groups[q, scenario, mode, policy]),
                                  data["stress"][key][policy], key + "/" + policy)
                check_summary(paired(*(groups[q, scenario, mode, p] for p in POLICIES))[1],
                              data["stress"][key]["paired"], key + "/paired")
    return data, groups


def enhancement_tables(data, groups):
    performance_rows, cost_rows, macros = [], [], []
    for q, word in ((3, "Three"), (4, "Four")):
        control, enhanced = (groups[q, "random", "smooth", p] for p in POLICIES)
        for policy, rows in zip(POLICIES, (control, enhanced)):
            stats = metrics(rows)
            label = "原集成" if policy == "integrated" else "增强"
            performance_rows.append((f"Q{q}", label,
                                     number(stats["mean_average_time_s"]),
                                     number(stats["median_average_time_s"]),
                                     number(stats["p90_average_time_s"]),
                                     f'{stats["all_cleared_cases"]}/{stats["cases"]}'))
            
            components = [statistics.mean(value(r) / r["n_sources"] for r in rows)
                          for value in (lambda r: r["distance_m"] / 5,
                                        lambda r: 5 * r["measures"], lambda r: r["switches"],
                                        lambda r: 3 * r["failed_clears"], lambda r: 5 * r["n_cleared"])]
            rounding_bound = statistics.mean(
                (0.5e-6 * (r["measures"] + r["clear_attempts"]) + 1e-8) / r["n_sources"]
                for r in rows)
            close(sum(components), stats["mean_average_time_s"], "Mean cost identity", tolerance=rounding_bound)
            cost_rows.append((f"Q{q}", label, *(number(v) for v in components),
                              number(stats["mean_average_time_s"])))
        comparison = paired(control, enhanced)[1]
        macros.extend(((f"EnhancedQ{word}Time", number(metrics(enhanced)["mean_average_time_s"])),
                       (f"EnhancedQ{word}Gain", number(comparison["mean_reduction_pct"]))))
    macros.extend((("EnhancementRuns", str(len(data["runs"]))),
                   ("ContractedRadius", number(data["contracted_ring"]["radius_m"]))))
    atomic_bytes(GENERATED / "enhancement_numbers.tex",
                 ("% Gains are percentage reductions of paired-group mean T/N.\n" +
                  "\n".join("\\newcommand{\\" + key + "}{" + value + "}" for key, value in macros)
                  + "\n").encode("utf-8"))
    table("enhancement_table.tex", ("问题", "策略", "均值/s", "中位数/s", "$P_{90}$/s", "全清/世界"),
          performance_rows, (0.9, 1.7, 2.6, 2.6, 2.6, 2.6))
    table("enhancement_costs.tex", ("问题", "策略", "$L/(5N)$", "$5M/N$", "$S/N$", "$3F/N$", "$5K/N$", "合计/s"),
          cost_rows, (0.9, 1.5, 2.1, 1.8, 1.7, 1.7, 1.7, 2.1))
    scenario_labels = {"minimum_radius": "最小半径", "outward_boundary": "边界朝外", "clustered": "聚集"}
    mode_labels = {"smooth": "平滑", "extreme": "极端", "iid_location": "位置独立"}
    pressure_rows = []
    for q in (3, 4):
        for scenario in SCENARIOS:
            for mode in MODES:
                control, enhanced = (groups[q, scenario, mode, p] for p in POLICIES)
                comparison = paired(control, enhanced)[1]
                both_clear = sum(a["n_cleared"] == a["n_sources"] and b["n_cleared"] == b["n_sources"]
                                 for a, b in zip(control, enhanced))
                pressure_rows.append((f"Q{q}", scenario_labels[scenario], mode_labels[mode],
                                      number(metrics(control)["mean_average_time_s"]),
                                      number(metrics(enhanced)["mean_average_time_s"]),
                                      number(comparison["mean_saved_s_per_source"]),
                                      f'{comparison["faster_cases"]}/{len(control)}',
                                      f"{both_clear}/{len(control)}"))
    table("enhancement_stress.tex", ("问题", "场景", "误差", "原集成/s", "增强/s", "节省/s", "更快/对", "双全清/对"),
          pressure_rows, (0.8, 1.7, 1.7, 2.1, 2.1, 2.1, 1.6, 2.0), left_columns=(0, 1, 2))


def candidate_table():
    static = load("route_candidate_comparison.json")
    adaptive = load("adaptive_candidate_comparison.json")
    require(set(static["summary"]) == set(adaptive["summary"]) == {"Q3", "Q4"},
            "Unexpected candidate problems")
    static_start, static_end = static["seed_range"]
    adaptive_start, adaptive_end = adaptive["seed_range"]
    require(type(static_start) is int and type(static_end) is int and static_end >= static_start,
            "Invalid static seed range")
    require(type(adaptive_start) is int and type(adaptive_end) is int and adaptive_end >= adaptive_start,
            "Invalid adaptive seed range")
    static_count, adaptive_count = static_end - static_start + 1, adaptive_end - adaptive_start + 1
    static_groups = defaultdict(list)
    for pair in static.get("runs", []):
        require(pair["problem"] in (3, 4), "Unexpected static problem")
        nearest, two_opt = pair["nearest"], pair["two_opt"]
        check_run(nearest)
        check_run(two_opt)
        require(nearest["seed"] == two_opt["seed"] == pair["seed"]
                and nearest["problem"] == two_opt["problem"] == pair["problem"],
                "Static pair metadata mismatch")
        static_groups[pair["problem"]].append(pair)
    adaptive_groups = defaultdict(list)
    for pair in adaptive.get("runs", []):
        require(pair["problem"] in (3, 4), "Unexpected adaptive problem")
        for policy in ("fixed", "adaptive"):
            row = pair[policy]
            check_run(row)
            require(row["seed"] == pair["seed"] and row["problem"] == pair["problem"],
                    "Adaptive pair metadata mismatch")
        adaptive_groups[pair["problem"]].append(pair)
    rows = []
    for q in (3, 4):
        pairs = sorted(static_groups[q], key=lambda p: p["seed"])
        require([p["seed"] for p in pairs] == list(range(static_start, static_end + 1)),
                "Static seed mismatch")
        nearest = [p["nearest"] for p in pairs]
        two_opt = [p["two_opt"] for p in pairs]
        deltas = [a["average_time_s"] - b["average_time_s"]
                  for a, b in zip(nearest, two_opt)]
        s = {"cases": static_count,
             "all_nearest_cleared": sum(a["fraction_cleared"] == 1 for a in nearest),
             "all_two_opt_cleared": sum(b["fraction_cleared"] == 1 for b in two_opt),
             "nearest_mean_s_per_source": statistics.mean(a["average_time_s"] for a in nearest),
             "two_opt_mean_s_per_source": statistics.mean(b["average_time_s"] for b in two_opt),
             "mean_saved_s_per_source": statistics.mean(deltas),
             "faster_cases": sum(d > 0 for d in deltas)}
        for key, value in s.items():
            if key in static["summary"][f"Q{q}"]:
                close(value, static["summary"][f"Q{q}"][key], f"Static Q{q}/{key}")
        close(s["nearest_mean_s_per_source"] - s["two_opt_mean_s_per_source"],
              s["mean_saved_s_per_source"], "Static mean difference")
        rows.append((f"Q{q}", "静态2-opt", number(s["nearest_mean_s_per_source"]),
                     number(s["two_opt_mean_s_per_source"]), number(s["mean_saved_s_per_source"]),
                     f'{s["faster_cases"]}/{static_count}',
                     f'{s["all_nearest_cleared"]}/{s["all_two_opt_cleared"]}'))
        pairs = sorted(adaptive_groups[q], key=lambda p: p["seed"])
        require([p["seed"] for p in pairs] == list(range(adaptive_start, adaptive_end + 1)),
                "Adaptive seed mismatch")
        fixed, adapted = [p["fixed"] for p in pairs], [p["adaptive"] for p in pairs]
        fixed_metrics, adapted_metrics = metrics(fixed), metrics(adapted)
        delta, comparison = paired(fixed, adapted)
        actual = {"cases": len(pairs), "fixed_all_cleared": fixed_metrics["all_cleared_cases"],
                  "adaptive_all_cleared": adapted_metrics["all_cleared_cases"],
                  "fixed_mean_s_per_source": fixed_metrics["mean_average_time_s"],
                  "adaptive_mean_s_per_source": adapted_metrics["mean_average_time_s"],
                  "mean_saved_s_per_source": comparison["mean_saved_s_per_source"],
                  "median_saved_s_per_source": statistics.median(delta),
                  "faster_cases": comparison["faster_cases"]}
        check_summary(actual, adaptive["summary"][f"Q{q}"], f"Adaptive Q{q}")
        rows.append((f"Q{q}", "自适应探测", number(actual["fixed_mean_s_per_source"]),
                     number(actual["adaptive_mean_s_per_source"]), number(actual["mean_saved_s_per_source"]),
                     f'{actual["faster_cases"]}/{adaptive_count}',
                     f'{actual["fixed_all_cleared"]}/{actual["adaptive_all_cleared"]}'))
    table("candidate_table.tex", ("问题", "候选", "对照/s", "候选/s", "节省/s", "更快/对", "全清数\\newline 对照/候选"),
          rows, (0.8, 2.4, 2.1, 2.1, 2.1, 1.9, 2.6))


def coverage_limits_table():
    certificate = load("coverage_limits.json")
    witnesses = certificate["witnesses"]
    require(len(witnesses) == certificate["parameters"]["point_count"] == 31,
            "Witness count mismatch")
    target_distances = [row["target_distance"] for row in witnesses]
    other_distances = [row["second_detector_distance"] for row in witnesses]
    rows = [
        ("Q3 q=900 lower bound", "7", "six boundary arcs at equality; origin uncovered"),
        ("Q3 fixed seven-set at q=1000", "7", "five ring arcs leave a boundary gap"),
        ("Q4 outer-boundary lower bound", "7", "arbitrary placements; outer detectors only"),
        ("Q4 current lattice witnesses", str(len(witnesses)),
         f"target d={min(target_distances):.3f}--{max(target_distances):.3f} m"),
        ("Q4 nearest other lattice point", f"{min(other_distances):.3f} m",
         "every witness remains outside near threshold"),
    ]
    table("coverage_limits_table.tex", ("Statement", "Value", "Interpretation"), rows,
          (4.1, 2.0, 8.7), left_columns=(0, 2))


def ring_sweep_table():
    data = load("ring_sweep.json")
    require(data["development_seed_range"] == [1000000, 1000149], "Ring development seeds")
    require(data["held_out_seed_range"] == [2300000, 2300499], "Ring fresh confirmation seeds")
    candidates = data["candidate_radii_m"]
    require(candidates == [1200., 1250., 1300., 1350., 1400., 1450., 1500., 1550.],
            "Unexpected frozen ring candidates")
    count = 0
    for phase, seed_key in (("development", "development_seed_range"),
                            ("held_out", "held_out_seed_range")):
        start, end = data[seed_key]
        for key, group in data[phase].items():
            runs = group["runs"]
            require([r["seed"] for r in runs] == list(range(start, end + 1)), "Ring paired seeds")
            count += len(runs)
            radius = float(key)
            envelope = max(radius / math.sqrt(3),
                           math.sqrt(1800**2 + radius**2 - math.sqrt(3) * 1800 * radius))
            close(envelope, group["exact_cover_radius_m"], "Ring envelope")
            require(envelope < 1000, "Unsafe ring candidate")
            for row in runs:
                check_run(row)
                require(row["problem"] == 3 and row["strategy"] == "enhanced"
                        and row["scenario"] == "random" and row["error_mode"] == "smooth",
                        "Ring world contract")
                close(row["ring_radius_m"], radius, "Ring run geometry")
                require(row["certificate_complete"] and row["timing_independently_verified"]
                        and row["n_cleared"] == row["n_sources"], "Incomplete ring run")
            check_summary(metrics(runs), group["summary"], "Ring summary")
    require(count == data["total_runs"] == 2200, "Ring run denominator")
    ordered = sorted(data["development"], key=lambda k:
                     data["development"][k]["summary"]["mean_average_time_s"])
    winner, runner_up = ordered[:2]
    close(float(winner), data["development_winner_m"], "Ring development winner")
    close(float(runner_up), data["development_runner_up_m"], "Ring runner-up")
    control = "1200.0" if winner != "1200.0" else runner_up
    comparison = data["held_out_comparison"]
    close(comparison["candidate_ring_radius_m"], float(winner), "Ring candidate")
    close(comparison["control_ring_radius_m"], float(control), "Ring control")
    deltas, calculated = paired(data["held_out"][control]["runs"], data["held_out"][winner]["runs"])
    require(deltas == comparison["deltas_s_per_source"], "Ring raw paired deltas")
    require(comparison["faster_candidate_cases"] == calculated["faster_cases"], "Ring win count")
    close(calculated["mean_saved_s_per_source"], comparison["mean_saved_s_per_source"], "Ring mean")
    se = statistics.stdev(deltas) / math.sqrt(len(deltas))
    for observed, expected in zip(comparison["approx_95pct_ci_s"],
                                  (statistics.mean(deltas) - 1.96 * se,
                                   statistics.mean(deltas) + 1.96 * se), strict=True):
        close(observed, expected, "Ring paired CI")
    rows = []
    for radius in candidates:
        key = str(float(radius))
        group = data["development"][key]
        held = data["held_out"].get(key)
        rows.append((f"{radius:.0f}", number(group["exact_cover_radius_m"]),
                     number(group["summary"]["mean_average_time_s"]),
                     number(held["summary"]["mean_average_time_s"]) if held else "--",
                     number(comparison["mean_saved_s_per_source"]) if key == winner else "--",
                     "保留" if key == winner else ("次优" if key == runner_up else "")))
    table("ring_sweep_table.tex", ("环半径/m", "解析覆盖/m", "开发T/N", "新样本T/N", "相对对照节省/s", "选择"),
          rows, (1.5, 2.2, 2.0, 2.1, 2.6, 1.0), left_columns=(5,))
    macros = {
        "RingSelectedTime": number(data["held_out"][winner]["summary"]["mean_average_time_s"]),
        "RingControlTime": number(data["held_out"][control]["summary"]["mean_average_time_s"]),
        "RingSaving": f'{comparison["mean_saved_s_per_source"]:.3f}',
        "RingLowerCI": f'{comparison["approx_95pct_ci_s"][0]:.3f}',
        "RingUpperCI": f'{comparison["approx_95pct_ci_s"][1]:.3f}',
        "RingFaster": str(comparison["faster_candidate_cases"]),
    }
    atomic_bytes(GENERATED / "ring_numbers.tex", "".join(
        "\\newcommand{\\" + key + "}{" + value + "}\n" for key, value in macros.items()).encode())


def geometry_figure(data, groups):
    certificate = load("coverage_limits.json")
    arena = certificate["parameters"]["arena_radius"]
    radio = certificate["parameters"]["receive_radius"]
    legacy = certificate["q1000_static_seven_irreducible"]["origin_to_ring"]
    contracted = data["contracted_ring"]
    radius = contracted["radius_m"]
    for policy, expected in (("integrated", legacy), ("enhanced", radius)):
        for row in groups[3, "random", "smooth", policy]:
            close(row["ring_radius_m"], expected, "Ring geometry/run mismatch")
    def exact_cover(r):
        return max(r / math.sqrt(3), math.sqrt(arena**2 + r**2 - math.sqrt(3) * arena * r))
    q = exact_cover(radius)
    close(q, contracted["exact_cover_radius_m"], "Contracted cover radius")
    close(radio - q, contracted["radio_margin_m"], "Contracted radial distance margin")
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 4.5))
    fig.subplots_adjust(left=0.10, right=0.99, bottom=0.37, top=0.85, wspace=0.30)
    for ax, r, color, title in zip(axes, (legacy, radius), COLORS, ("Integrated", "Contracted")):
        centers = [(0., 0.)] + [(r * math.cos(k * math.pi / 3), r * math.sin(k * math.pi / 3))
                                for k in range(6)]
        for x, y in centers:
            ax.add_patch(Circle((x / 1000, y / 1000), radio / 1000,
                                facecolor=color, edgecolor=color, alpha=0.12, linewidth=0.8))
            if title == "Contracted":
                ax.add_patch(Circle((x / 1000, y / 1000), q / 1000, fill=False,
                                    edgecolor=color, linestyle="--", linewidth=0.7))
        ax.add_patch(Circle((0, 0), arena / 1000, fill=False, color="black", linewidth=1.1))
        ax.scatter([x / 1000 for x, _ in centers], [y / 1000 for _, y in centers],
                   color=color, s=16, zorder=4)
        boundary = (arena * math.cos(math.pi / 6), arena * math.sin(math.pi / 6))
        ax.plot([r / 1000, boundary[0] / 1000], [0, boundary[1] / 1000], color="black", linewidth=1.1)
        ax.plot(boundary[0] / 1000, boundary[1] / 1000, "kx", markersize=5)
        ax.set(xlim=(-2.7, 2.7), ylim=(-2.7, 2.7), xlabel="x (km)", ylabel="y (km)",
               title=f"{title}\nr = {r:.2f} m")
        ax.set_xticks((-2, 0, 2))
        ax.set_yticks((-2, 0, 2))
        ax.set_aspect("equal")
        ax.grid(alpha=0.15)
        ax.text(0.5, -0.27, f"q = {exact_cover(r):.2f} m\nmargin = {radio-exact_cover(r):.2f} m",
                transform=ax.transAxes, ha="center", va="top", fontsize=10)
    handles = [Line2D([], [], color="black", label="Source arena"),
               Line2D([], [], color=COLORS[0], alpha=0.5, label=f"Radio: {radio:.0f} m"),
               Line2D([], [], color=COLORS[1], linestyle="--", label=f"Cover: {q:.2f} m (right)")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.005),
               ncol=1, frameon=False, fontsize=10)
    save_figure(fig, "enhancement_geometry.pdf")


def ecdf(ax, values, **kwargs):
    ordered = sorted(values)
    require(bool(ordered), "Empty ECDF")
    ax.step([ordered[0]] + ordered, [0.] + [(i + 1) / len(ordered) for i in range(len(ordered))],
            where="post", **kwargs)


def performance_figure(groups):
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 5.8), sharey=True)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.93, bottom=0.14, hspace=0.56, wspace=0.34)
    for column, q in enumerate((3, 4)):
        control, enhanced = (groups[q, "random", "smooth", p] for p in POLICIES)
        delta, _ = paired(control, enhanced)
        ax = axes[0, column]
        ecdf(ax, delta, color=COLORS[column], linewidth=1.5)
        ax.axvline(0, color="0.4", linestyle="--", linewidth=0.8)
        ax.set(title=f"Q{q}: paired savings", xlabel="Integrated - enhanced (s/source)")
        ax = axes[1, column]
        for rows, color, label in zip((control, enhanced), COLORS, ("Integrated", "Enhanced")):
            ecdf(ax, [r["average_time_s"] for r in rows], color=color, linewidth=1.5, label=label)
        ax.set(title=f"Q{q}: time distributions", xlabel="T/N (s/source)")
    for ax in axes.flat:
        ax.set_ylim(0, 1.02)
        ax.set_yticks((0, 0.5, 1))
        ax.grid(alpha=0.18)
        ax.tick_params(axis="x", labelrotation=0)
    for ax in axes[:, 0]:
        ax.set_ylabel("Empirical probability")
    handles, labels = axes[1, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.015))
    save_figure(fig, "enhancement_performance.pdf")


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.titlesize": 10, "axes.labelsize": 10,
                         "xtick.labelsize": 10, "ytick.labelsize": 10,
                         "legend.fontsize": 10, "pdf.fonttype": 42,
                         "savefig.transparent": False, "figure.facecolor": "white"})
    data, groups = load_enhancement()
    enhancement_tables(data, groups)
    candidate_table()
    coverage_limits_table()
    ring_sweep_table()
    geometry_figure(data, groups)
    performance_figure(groups)
    print(f"Generated enhancement assets from {len(data['runs'])} saved runs; "
          "raw candidate pairs and ring sweep validated. No simulator executed.")
    input_names = ("enhancement_experiments.json", "route_candidate_comparison.json",
                   "adaptive_candidate_comparison.json", "coverage_limits.json",
                   "ring_sweep.json", "refinement_verification.json", "anchor_development.json")
    output_names = ("enhancement_numbers.tex", "enhancement_table.tex", "enhancement_costs.tex",
                    "enhancement_stress.tex", "candidate_table.tex", "coverage_limits_table.tex",
                    "ring_sweep_table.tex", "ring_numbers.tex", "enhancement_geometry.pdf", "enhancement_performance.pdf")
    metadata = {
        "evidence": "held_out_local_synthetic_not_official",
        "policy": {"Q3": "enhanced ring radius 1200m selected by a development-only sweep, nearest anchor",
                    "Q4": "enhanced 990m triangular lattice, rolling remaining-anchor route",
                    "probe": "fixed probe and bounded recovery; adaptive candidate is negative control"},
        "input_sha256": {"results/" + name: hashlib.sha256((ROOT / "results" / name).read_bytes()).hexdigest()
                         for name in input_names},
        "outputs": list(output_names),
        "main_seed_range": data["main_seed_range"],
        "stress_seed_range": data["stress_seed_range"],
        "total_runs": data["total_runs"],
        "ring_sweep_runs": 2200,
        "ring_confirmation_seed_range": [2300000, 2300499],
        "metric": "per-world T/N; paired savings are control minus enhanced",
        "official_calls": 0,
        "reproducibility": "Generated after validating every raw run, paired seed and cost decomposition",
    }
    atomic_bytes(GENERATED / "enhancement_metadata.json",
                 (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
