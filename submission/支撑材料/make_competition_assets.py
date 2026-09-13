"""Generate compact competition-paper vector figures.

This module is intentionally data-light: ring/direction/localization panels are
schematics, while ``competition_costs.pdf`` uses only the frozen field log.
Run from ``b_solution`` with the project conda environment.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle, FancyArrowPatch
import numpy as np

ROOT = Path(__file__).resolve().parent
FIGURES = ROOT / "report" / "figures"
GENERATED = ROOT / "report" / "generated"
BLUE, ORANGE, GREEN, GREY = "#0072B2", "#E69F00", "#009E73", "#666666"


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / name, format="pdf", metadata={"Creator": "CUMCM competition assets"})
    plt.close(fig)


def base(title):
    fig, ax = plt.subplots(figsize=(16 / 2.54, 7 / 2.54), layout="constrained")
    ax.set_title(title, fontsize=11, pad=5)
    ax.axis("off")
    return fig, ax


def taskmap():
    fig, ax = base("四问：从几何覆盖到定向定位")
    xs = [0.08, .31, .54, .77]; labels = ["Q1\n几何边界", "Q2\n接收盘与覆盖", "Q3\n全向清除", "Q4\n定向定位"]
    for i, (x, lab) in enumerate(zip(xs, labels)):
        ax.add_patch(Rectangle((x, .38), .15, .25, facecolor="#EAF2F8" if i < 2 else "#FFF2DF", edgecolor=BLUE if i < 2 else ORANGE, lw=1.5))
        ax.text(x + .075, .505, lab, ha="center", va="center", fontsize=9)
        if i < 3: ax.add_patch(FancyArrowPatch((x+.15,.505),(xs[i+1],.505),arrowstyle="->",lw=1.4,color=GREY))
    ax.text(.5, .18, "可行域 → 最小包围盘 → 扫描停止 → 局部测向与光学覆盖", ha="center", fontsize=8, color=GREY)
    save(fig, "competition_taskmap.pdf")


def ring():
    fig, ax = base("Q3 环形布点")
    ax.set_aspect("equal"); ax.set_xlim(-2050,2050); ax.set_ylim(-2050,2050)
    ax.add_patch(Circle((0,0),1800,fill=False,ls="--",color=GREY,lw=1))
    u=np.array([np.cos(np.pi/6),np.sin(np.pi/6)]); g=1800*u; p=np.array([1200.,0.]);
    angles=np.arange(6)*np.pi/3; pts=np.c_[1200*np.cos(angles),1200*np.sin(angles)]
    ax.plot(*np.vstack([pts,pts[0]]).T,color=ORANGE,lw=1.5); ax.scatter(pts[:,0],pts[:,1],s=20,color=ORANGE,zorder=3)
    g=np.array([1800*np.cos(np.pi/6),1800*np.sin(np.pi/6)]); nearest=1200*np.array([1.,0.]); ax.scatter(*g,color="#D55E00",marker="x",s=45,zorder=4); ax.plot([g[0],nearest[0]],[g[1],nearest[1]],color=GREEN,lw=2)
    ax.annotate("最坏源点",xy=g,xytext=(g[0]+120,g[1]+120),fontsize=8); ax.annotate("968.90 m，余量31.10 m",xy=((g[0]+nearest[0])*.5,(g[1]+nearest[1])*.5),fontsize=8,color=GREEN)
    for c in pts: ax.add_patch(Circle(c,1000,fill=False,color=BLUE,lw=.8,alpha=.65))
    ax.text(-1750,-1930,"7 个接收盘（半径 1000 m）；6 环点 + 原点",fontsize=8,color=BLUE)
    save(fig,"competition_ring.pdf")


def direction():
    fig, axes = plt.subplots(1,2,figsize=(16/2.54,7/2.54),layout="constrained")
    for ax in axes: ax.set_aspect("equal"); ax.axis("off")
    ax=axes[0]; ax.add_patch(Circle((0,0),1,fill=False,color=BLUE)); g=np.array([.7,.7]); ax.scatter(*g,color=ORANGE); ax.arrow(*g,.35,.35,width=.015,color=ORANGE); ax.fill_between([-.9,.9],-.9,.9,color=ORANGE,alpha=.08); ax.text(-.9,-1.15,"g 在源圆周；前向半平面朝外",fontsize=8)
    ax=axes[1]; tri=np.array([[-.8,-.6],[.75,-.5],[.05,.65]]); ax.add_patch(Polygon(tri,fill=False,color=BLUE,lw=1.5)); g=np.array([-.05,.25]); n=np.array([.45,.25]); h=g+5*n; ax.scatter(*g,color=ORANGE); ax.scatter(*h,color=GREEN); c=tri.mean(0); ax.scatter(*c,color=GREY); ax.plot([c[0],0],[c[1],-.95],"--",color=GREEN); ax.text(-.9,-1.15,"含 h=g+5n 的三角形重心投影",fontsize=8); ax.text(*g," g",fontsize=8); ax.text(*h," h",fontsize=8)
    fig.text(.5,.98,"Q4 方向性与双环（原理示意，非观测轨迹）",ha="center",va="top",fontsize=10); save(fig,"competition_direction.pdf")


def localize():
    fig, axes = plt.subplots(1,2,figsize=(16/2.54,7/2.54),layout="constrained")
    for ax in axes: ax.set_aspect("equal"); ax.axis("off")
    ax=axes[0]; n=np.array([0.,1.]); z=np.array([-.6,0.]); delta=.18; ax.plot([-1,1],[0,0],color=BLUE); ax.plot([-1,1],[delta,delta],"--",color=ORANGE); ax.plot([-1,1],[-delta,-delta],"--",color=ORANGE); ax.scatter(np.linspace(-.8,.8,5),np.zeros(5),color=BLUE,s=16); ax.arrow(*z,*n,width=.01,color=GREEN); ax.text(-.95,-.95,"横向测点：z plus/minus delta n",fontsize=8)
    ax=axes[1]; ax.add_patch(Rectangle((-.9,-.65),1.8,1.3,fill=False,color=BLUE)); xx=np.linspace(-.75,.75,5); yy=np.linspace(-.5,.5,4); X,Y=np.meshgrid(xx,yy)
    for x,y in zip(X.flat,Y.flat): ax.add_patch(Circle((x,y),.12,fill=False,color=ORANGE,lw=.7))
    ax.scatter(X,Y,s=10,color=ORANGE); ax.text(-.9,-.95,"半径 19.9 m 圆覆盖矩形网格（2 面板）",fontsize=8)
    fig.text(.5,.98,"局部测向与光学覆盖（原理示意）",ha="center",va="top",fontsize=10); save(fig,"competition_localize.pdf")


def dispatch():
    fig, ax = base("Q3 扫描闭环")
    ax.text(.5,.78,"公开观测",ha="center",fontsize=9); ax.add_patch(FancyArrowPatch((.5,.72),(.5,.58),arrowstyle="->",color=GREY))
    ax.text(.5,.52,"选择扫描 / 定位",ha="center",fontsize=9); ax.add_patch(FancyArrowPatch((.5,.46),(.5,.31),arrowstyle="->",color=GREY))
    ax.text(.5,.24,"清除频道并更新骨架",ha="center",fontsize=9); ax.add_patch(FancyArrowPatch((.5,.18),(.3,.08),connectionstyle="arc3,rad=.3",arrowstyle="->",color=GREY))
    ax.text(.3,.03,"继续循环",ha="center",fontsize=8,color=BLUE); ax.text(.76,.08,"停止：各频道已清除 / 全骨架无信号\n或 16 个不同频道已清除",ha="center",fontsize=8,color=GREEN)
    save(fig,"competition_dispatch.pdf")


def costs():
    d=json.loads((ROOT/"results/field_confirmation.json").read_text(encoding="utf-8"))
    rows=[r for r in d["runs"] if 7100000<=int(r["seed"])<=7100999]
    assert len(rows)==6000
    groups=[]
    for p in (3,4):
        for cfg in (("control","控制"),("field","field")):
            rr=[r for r in rows if r["problem"]==p and r["configuration"]==cfg[0]]; assert len(rr)==1000
            vals=[]
            for r in rr:
                op=5*r["measures"]+r["switches"]+3*r["failed_clears"]+5*r["n_cleared"]
                move=r["virtual_time_s"]-op
                assert math.isclose(move,r["distance_m"]/5,abs_tol=1e-5)
                vals.append((move/r["n_cleared"],op/r["n_cleared"]))
            groups.append((f"Q{p} {cfg[1]}",np.mean(vals,axis=0)))
    fig,ax=plt.subplots(figsize=(16/2.54,7/2.54),layout="constrained"); x=np.arange(4); mv=np.array([g[1][0] for g in groups]); op=np.array([g[1][1] for g in groups]); ax.bar(x,mv,color=BLUE,label="移动"); ax.bar(x,op,bottom=mv,color=ORANGE,label="操作"); ax.set_xticks(x,[g[0] for g in groups],fontsize=8); ax.set_ylabel("T/K（s）"); ax.set_title("主组成本分解",fontsize=10); ax.legend(fontsize=8); ax.grid(axis="y",alpha=.2); save(fig,"competition_costs.pdf")
def main():
    plt.rcParams.update({"font.size":9,"font.family":"sans-serif","font.sans-serif":["FandolSong","Arial Unicode MS","PingFang SC","DejaVu Sans"],"pdf.fonttype":42})
    for f in (taskmap,ring,direction,localize,dispatch,costs): f()
    inputs=[ROOT/"results/field_confirmation.json",ROOT/"geometry.py",ROOT/"coverage.py",Path(__file__)]
    meta={"generator":str(Path(__file__).relative_to(ROOT)),"figures":[f"figures/competition_{n}.pdf" for n in ("taskmap","ring","direction","localize","dispatch","costs")],"input_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}}
    GENERATED.mkdir(parents=True,exist_ok=True); (GENERATED/"competition_metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

if __name__ == "__main__": main()

