"""Draw five additional body figures without changing any strategy or result.

Run with the project's py314 interpreter. Geometry panels use stated analytic
examples; the trajectory and formal comparison use existing saved observations.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon
from matplotlib.ticker import MaxNLocator
import numpy as np

from intersection import solve_intersection
from geometry import BEARING_ERROR_DEG

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "report" / "figures"
BLUE, ORANGE, TEAL, GREY = "#12355B", "#E67E22", "#17807E", "#68737D"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial Unicode MS", "DejaVu Sans"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def save(fig, directory, name):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    fig.savefig(path, format="pdf", metadata={
        "Creator": "redraw_additional.py", "CreationDate": None, "ModDate": None,
    })
    plt.close(fig)
    return path


def wedge_figure(directory):
    """Two legal bearings and an exact, bounded half-plane intersection."""
    stations = [(0.0, 0.0), (950.0, 0.0)]
    source = (600.0, 650.0)
    bearings = [round(math.degrees(math.atan2(source[1]-y, source[0]-x)), 2)
                for x, y in stations]
    result = solve_intersection(stations, bearings, BEARING_ERROR_DEG)
    assert result["status"] == "bounded"
    vertices = np.asarray(result["vertices"])
    for (x, y), bearing in zip(stations, bearings):
        actual = math.degrees(math.atan2(source[1]-y, source[0]-x))
        assert abs(actual-bearing) <= BEARING_ERROR_DEG
        assert math.dist((x, y), source) < 1000
    i, j = max(itertools.combinations(range(len(vertices)), 2),
               key=lambda ij: np.linalg.norm(vertices[ij[0]]-vertices[ij[1]]))
    diameter = float(np.linalg.norm(vertices[i]-vertices[j]))
    assert math.isclose(diameter, result["diameter_m"], abs_tol=1e-8)

    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.85), layout="constrained")
    ax = axes[0]
    for k, (station, bearing, color) in enumerate(zip(stations, bearings, (BLUE, ORANGE)), 1):
        theta = math.radians(bearing)
        alpha = math.radians(BEARING_ERROR_DEG)
        endpoints = [np.asarray(station)+1050*np.array([math.cos(theta+d), math.sin(theta+d)])
                     for d in (-alpha, alpha)]
        ax.add_patch(Polygon([station, *endpoints], facecolor=color, alpha=.16, edgecolor="none"))
        for endpoint in endpoints:
            ax.plot([station[0], endpoint[0]], [station[1], endpoint[1]], color=color, lw=.85)
        ax.plot([station[0], source[0]], [station[1], source[1]], color=color, lw=.8, ls="--")
        ax.scatter(*station, color=color, s=25, zorder=5)
        ax.annotate(rf"$s_{k}$", station, xytext=(4, -15), textcoords="offset points", color=color)
    ax.scatter(*source, marker="*", color=TEAL, s=50, zorder=6)
    ax.annotate(r"$g$", source, xytext=(6, 5), textcoords="offset points", color=TEAL)
    ax.set(xlim=(-70, 1050), ylim=(-100, 920), xlabel="x / m", ylabel="y / m",
           title=r"(a) 两次示向，$\alpha=1.005^\circ$")
    ax.set_aspect("equal")
    ax.grid(alpha=.13)

    ax = axes[1]
    ax.add_patch(Polygon(vertices, facecolor=TEAL, edgecolor=TEAL, alpha=.24, lw=1.3))
    ax.scatter(vertices[:, 0], vertices[:, 1], color=TEAL, s=15, zorder=4)
    ax.plot(vertices[[i, j], 0], vertices[[i, j], 1], color=ORANGE, lw=1.8, label="最远顶点连线")
    ax.scatter(*source, marker="*", color=BLUE, s=50, zorder=6, label="算例源位置")
    ax.text(.05, .95, rf"$D(P)={diameter:.2f}$ m", transform=ax.transAxes,
            va="top", color=BLUE, fontsize=9)
    extent = np.max(np.ptp(vertices, axis=0)) * .80
    center = (vertices.min(axis=0)+vertices.max(axis=0))/2
    ax.set(xlim=(center[0]-extent, center[0]+extent),
           ylim=(center[1]-extent, center[1]+extent),
           xlabel="x / m", ylabel="y / m", title=r"(b) 交集 $P=W_1\cap W_2$ 放大")
    ax.set_aspect("equal")
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.yaxis.set_major_locator(MaxNLocator(4))
    ax.legend(loc="lower left", frameon=False, fontsize=7.5)
    ax.grid(alpha=.13)
    path = save(fig, directory, "q1_wedge.pdf")
    return path, {"kind": "analytic_example", "stations_m": stations,
                  "source_m": source, "bearings_deg": bearings,
                  "error_deg": BEARING_ERROR_DEG, "vertices_m": result["vertices"],
                  "diameter_m": diameter}


def angle_figure(directory):
    """Only compare the angle factor with ranges and angular error fixed."""
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.75), layout="constrained")
    source = np.array([0., 0.])
    s1 = np.array([-600., 0.])
    s2a = -600*np.array([math.cos(math.radians(20)), math.sin(math.radians(20))])
    s2b = np.array([0., -600.])
    ax = axes[0]
    for point, color, label, offset in (
        (s1, BLUE, r"$S_1$", (-12, 8)),
        (s2a, GREY, r"$S_{2a}$", (-12, -15)),
        (s2b, ORANGE, r"$S_{2b}$", (7, -3)),
    ):
        ax.plot([0, point[0]], [0, point[1]], color=color, lw=1.2)
        ax.scatter(*point, s=22, color=color)
        ax.annotate(label, point, xytext=offset, textcoords="offset points", color=color)
    ax.add_patch(Arc(source, 290, 290, theta1=180, theta2=200, color=GREY, lw=1.1))
    ax.add_patch(Arc(source, 185, 185, theta1=180, theta2=270, color=ORANGE, lw=1.1))
    ax.text(-365, -115, r"$20^\circ$", fontsize=9, color=GREY)
    ax.text(-215, -245, r"$90^\circ$", fontsize=9, color=ORANGE)
    ax.scatter(*source, marker="*", s=60, color=TEAL, zorder=5)
    ax.annotate(r"$g$", source, xytext=(7, 6), textcoords="offset points", color=TEAL)
    ax.set(xlim=(-760, 160), ylim=(-720, 160), xlabel="x / m", ylabel="y / m",
           title=r"(a) 固定 $r_1=r_2=600$ m")
    ax.set_aspect("equal")
    ax.grid(alpha=.13)

    ax = axes[1]
    beta = np.linspace(10, 170, 481)
    factor = 1 / np.sin(np.radians(beta))
    ax.plot(beta, factor, color=BLUE, lw=1.8)
    for angle, color in ((20, GREY), (90, ORANGE)):
        value = 1 / math.sin(math.radians(angle))
        ax.scatter(angle, value, color=color, s=24, zorder=4)
        ax.annotate(f"({angle}°, {value:.2f})", (angle, value), xytext=(9, 10),
                    textcoords="offset points", color=color, fontsize=8)
    ax.axvline(90, color=ORANGE, lw=.8, ls="--")
    ax.set(xlim=(5, 175), ylim=(.7, 6.3), xlabel=r"交会角 $\beta$ / (°)",
           ylabel=r"相对面积 $1/|\sin\beta|$", title="(b) 固定距离下的角度影响")
    ax.set_xticks([20, 60, 90, 120, 160])
    ax.grid(alpha=.17)
    path = save(fig, directory, "q2_angle.pdf")
    return path, {"kind": "analytic_approximation", "ranges_m": [600, 600],
                  "beta_range_deg": [10, 170], "factor_20_deg": 1/math.sin(math.radians(20)),
                  "factor_90_deg": 1.0, "varying_distance_effect_included": False}


def q3_tradeoff_figure(directory):
    R = 1800.0
    dmax = 900 * math.sqrt(3)
    ds = np.linspace(1200, dmax, 500)
    rho = np.maximum(ds / math.sqrt(3), np.sqrt(R**2 + ds**2 - math.sqrt(3)*R*ds))
    travel = 6 * ds
    assert np.all(rho < 1000) and np.all(np.diff(rho) <= 1e-9)
    assert math.isclose(rho[-1], 900, abs_tol=1e-8)
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.55), layout="constrained")
    axes[0].plot(ds, rho, color=BLUE, lw=1.8)
    axes[0].axhline(1000, color=GREY, ls="--", lw=.8)
    axes[0].text(1280, 1003, "接收下界 1000 m", fontsize=8, color=GREY)
    axes[0].scatter([1200, dmax], [rho[0], rho[-1]], color=ORANGE, s=22, zorder=4)
    axes[0].annotate(f"{rho[0]:.2f} m", (1200, rho[0]), xytext=(9, 8),
                     textcoords="offset points", color=BLUE, fontsize=8)
    axes[0].text(.97, .16, "900.00 m", transform=axes[0].transAxes,
                 ha="right", color=BLUE, fontsize=8)
    axes[0].set(xlabel=r"环半径 $d$ / m", ylabel=r"覆盖半径 $\rho(d)$ / m",
                ylim=(890, 1016), title="(a) 环增大，最坏覆盖距离缩短")
    axes[1].plot(ds, travel, color=ORANGE, lw=1.8)
    axes[1].scatter([1200, dmax], [travel[0], travel[-1]], color=BLUE, s=22, zorder=4)
    axes[1].annotate("7200 m", (1200, 7200), xytext=(12, 18),
                     textcoords="offset points", color=BLUE, fontsize=8,
                     bbox=dict(facecolor="white", edgecolor="none", pad=.15))
    axes[1].annotate(f"{travel[-1]:.1f} m", (dmax, travel[-1]), xytext=(-10, -24),
                     textcoords="offset points", ha="right", color=ORANGE, fontsize=8,
                     bbox=dict(facecolor="white", edgecolor="none", pad=.15))
    axes[1].set(xlabel=r"环半径 $d$ / m", ylabel="纯骨架行程 / m",
                ylim=(7000, 9690), title="(b) 开放骨架行程为 6d")
    for ax in axes:
        ax.set_xlim(1185, 1580)
        ax.set_xticks([1200, 1350, 1500])
        ax.grid(alpha=.17)
    path = save(fig, directory, "q3_tradeoff.pdf")
    return path, {"kind": "analytic_curves", "ring_radius_range_m": [1200, dmax],
                  "coverage_at_1200_m": float(rho[0]), "travel_at_1200_m": 7200,
                  "travel_at_900sqrt3_m": float(travel[-1]),
                  "localization_or_measurement_cost_included": False}


def q4_route_figure(directory):
    a, b = 940.0, 1870.0
    angle = np.arange(12)*np.pi/6
    inner = np.column_stack([a*np.cos(angle), a*np.sin(angle)])
    outer = np.column_stack([b*np.cos(angle+np.pi/12), b*np.sin(angle+np.pi/12)])
    route = np.vstack([[0., 0.], inner, outer[::-1]])
    length = sum(math.dist(p, q) for p, q in zip(route, route[1:]))
    formula = a+22*(a+b)*math.sin(math.pi/12)+math.sqrt(a*a+b*b-2*a*b*math.cos(math.pi/12))
    assert len(route) == 25 and math.isclose(length, formula, abs_tol=1e-7)

    trace_path = ROOT / "report/generated/research_trajectory_q4.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["evidence"] == "observable_local_synthetic_trajectory_not_official"
    assert trace["planner"]["strategy"] == "refined" and trace["seed"] == 20260910
    points, cleared = [(0., 0.)], []
    elapsed_us, radio, distance = 0, 1, 0.0
    for event in trace["observable_log"]:
        req, resp = event["request"], event["response"]
        if resp.get("accepted") is not True:
            continue
        if req["path"] in ("/measure", "/clear"):
            point = (req["position"]["x"], req["position"]["y"])
            step = math.dist(points[-1], point)
            distance += step
            elapsed_us += round(step / 5 * 1_000_000)
            if req["path"] == "/measure":
                elapsed_us += (5+int(radio != req["channel"]))*1_000_000
                radio = req["channel"]
            else:
                success = resp["clear_result"] == "success"
                elapsed_us += (5 if success else 3)*1_000_000
                if success:
                    cleared.append(point)
            if point != points[-1]:
                points.append(point)
        assert abs(elapsed_us / 1_000_000-resp["virtual_time_s"]) <= 1e-6
    actual = trace["post_exit_evaluation"]
    assert trace["planner"]["certificate_complete"]
    assert len(cleared) == actual["n_sources"] == actual["n_cleared"]
    assert math.isclose(distance, actual["distance_m"], abs_tol=1e-6)
    assert math.isclose(elapsed_us/1_000_000, actual["virtual_time_s"], abs_tol=1e-6)

    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.05), layout="constrained")
    for ax in axes:
        ax.add_patch(Circle((0, 0), 1800, fill=False, color=GREY, ls="--", lw=.8))
        ax.set(xlim=(-2140, 2140), ylim=(-2140, 2140), xlabel="x / m", ylabel="y / m")
        ax.set_aspect("equal")
        ax.set_xticks([-1800, 0, 1800])
        ax.set_yticks([-1800, 0, 1800])
        ax.grid(alpha=.13)
    ax = axes[0]
    ax.plot(route[:, 0], route[:, 1], lw=1.05, color=BLUE, zorder=2)
    for p, q in zip(route[:-1:3], route[1::3]):
        ax.add_patch(FancyArrowPatch(p+.3*(q-p), p+.7*(q-p), arrowstyle="-|>",
                                     mutation_scale=9, color=BLUE, lw=.85))
    ax.scatter(inner[:, 0], inner[:, 1], s=14, color=ORANGE, label="内环点")
    ax.scatter(outer[:, 0], outer[:, 1], s=14, color=TEAL, label="外环点")
    ax.scatter(0, 0, s=25, marker="D", color=BLUE)
    ax.set_title(f"(a) 骨架可行路线：{length/1000:.2f} km")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.23), ncol=2, frameon=False)

    ax = axes[1]
    points, cleared = np.asarray(points), np.asarray(cleared)
    ax.plot(points[:, 0], points[:, 1], color=BLUE, lw=.8, alpha=.8)
    ax.scatter(cleared[:, 0], cleared[:, 1], color=ORANGE, s=17, label="成功清除位置", zorder=4)
    ax.scatter(0, 0, color=TEAL, marker="D", s=25, label="起点", zorder=5)
    ax.scatter(*points[-1], color=BLUE, marker="s", s=20, label="终点", zorder=5)
    ax.set_title(f"(b) refined 本地轨迹：{distance/1000:.2f} km")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.23), ncol=2, frameon=False, fontsize=7.5)
    path = save(fig, directory, "q4_route.pdf")
    return path, {"kind": "analytic_route_and_saved_local_simulation",
                  "source_file": trace_path.relative_to(ROOT).as_posix(),
                  "static_route_m": length, "seed": trace["seed"], "strategy": "refined",
                  "simulated_route_m": distance, "simulated_virtual_time_s": elapsed_us/1_000_000,
                  "cleared_count": len(cleared), "markers_are": "successful_clear_positions_not_source_truth",
                  "timing_independently_recomputed": True}


def formal_compare_figure(directory):
    source = ROOT / "results/formal_results.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = sorted(data["rows"], key=lambda r: (r["problem"], r["attempt"]))
    assert data["formal"] is True
    assert [(r["problem"], r["attempt"]) for r in rows] == [(p, i) for p in (3, 4) for i in (1, 2, 3)]
    for row in rows:
        assert row["K"] > 0 and row["certificate_complete"] is True
        assert math.isclose(row["T_over_K_s"], row["virtual_time_s"]/row["K"], abs_tol=1e-8)
    values = np.asarray([r["virtual_time_s"]/r["K"] for r in rows])
    x = np.arange(6)
    fig, ax = plt.subplots(figsize=(6.3, 2.65), layout="constrained")
    ax.bar(x, values, color=[BLUE]*3+[ORANGE]*3, width=.58, zorder=3)
    for j, (value, row) in enumerate(zip(values, rows)):
        ax.annotate(f"{value:.1f}", (j, value), xytext=(0, 7),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8,
                    bbox=dict(facecolor="white", edgecolor="none", pad=.15), zorder=6)
        ax.text(j, value-22, f"K={row['K']}", ha="center", va="top", fontsize=8,
                color="white", zorder=6)
    for left, right, group, color, label in ((-.45, 2.45, values[:3], BLUE, "Q3"), (2.55, 5.45, values[3:], ORANGE, "Q4")):
        mean = float(group.mean())
        ax.hlines(mean, left, right, colors=color, lw=1.1, linestyles="--", zorder=4)
        ax.text((left+right)/2, 775, f"{label} 等权均值 {mean:.3f}", ha="center", color=color, fontsize=9)
    ax.axvline(2.5, color=GREY, alpha=.4, lw=.7)
    ax.set_xticks(x, [f"Q{r['problem']}-{r['attempt']}" for r in rows])
    ax.set(ylabel="单源时间 / (s/源)", ylim=(0, 820), xlabel="正式测试序号（均采用 field）")
    ax.grid(axis="y", alpha=.17, zorder=0)
    path = save(fig, directory, "formal_compare.pdf")
    return path, {"kind": "observed_formal_summary", "source_file": source.relative_to(ROOT).as_posix(),
                  "T_over_K_s": values.tolist(), "K": [r["K"] for r in rows],
                  "equal_run_means": {"Q3": float(values[:3].mean()), "Q4": float(values[3:].mean())},
                  "cases_are_paired": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=FIGURES)
    args = parser.parse_args()
    figures = {}
    for fn in (wedge_figure, angle_figure, q3_tradeoff_figure, q4_route_figure, formal_compare_figure):
        path, evidence = fn(args.output_dir)
        figures[path.name] = evidence
    inputs = [Path(__file__), ROOT/"geometry.py", ROOT/"intersection.py",
              ROOT/"results/formal_results.json", ROOT/"report/generated/research_trajectory_q4.json"]
    metadata = {"generator": "redraw_additional.py", "figures": figures,
                "input_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    (args.output_dir/"additional_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({name: data["kind"] for name, data in figures.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
