
from __future__ import annotations

import math
from pathlib import Path

import matplotlib as mpl
mpl.use("pdf")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Wedge
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report" / "figures"
NAVY, ORANGE, TEAL, GREY = "#12355B", "#E67E22", "#17807E", "#68737D"
mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial Unicode MS"],
    "axes.unicode_minus": False, "pdf.fonttype": 42, "font.size": 9,
})


def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def geometry_figure():
    D = 36.0
    tri = np.array([(0, 0), (D, 0), (D / 2, math.sqrt(3) * D / 2)])
    mec_r = D / math.sqrt(3)
    fig, ax = plt.subplots(1, 2, figsize=(10.8, 4.6), gridspec_kw={"width_ratios": [1, 1.18]})
    
    a = ax[0]
    a.add_patch(Polygon(tri, closed=True, facecolor=ORANGE, alpha=.18, edgecolor=NAVY, lw=2.1, label="可行域（等边三角形）"))
    stations = []
    L = 18 * math.sqrt(3) / math.tan(math.radians(2)) - 18
    for p, q, bearing in zip(tri, np.roll(tri, -1, axis=0), (1, 121, 241)):
        e = (q - p) / D
        s = p - L * e
        stations.append(s)
        a.plot([s[0], p[0]], [s[1], p[1]], color=GREY, lw=1, ls="--")
        a.scatter(*s, s=24, color=TEAL, zorder=4)
        a.annotate(f"测站 {len(stations)}\n{bearing}°", s, xytext=(0, -17 if len(stations) == 1 else 10),
                   textcoords="offset points", ha="center", fontsize=7, color=TEAL)
    for label, p, offset in zip("ABC", tri, ((-8, -10), (7, -10), (0, 8))):
        a.scatter(*p, color=NAVY, s=20, zorder=5); a.annotate(label, p, xytext=offset, textcoords="offset points", color=NAVY, weight="bold")
    a.annotate("D=36 m", (18, 0), xytext=(0, -17), textcoords="offset points", ha="center", color=NAVY)
    a.set_title("(a) 可实现的测向可行域", color=NAVY, weight="bold")
    a.set_xlabel("x / m"); a.set_ylabel("y / m"); a.set_aspect("equal"); a.grid(alpha=.18)
    a.legend(loc="upper right", fontsize=7, frameon=False)
    a.set_xlim(-L*.08, D+L*.08); a.set_ylim(-L*.03, tri[2,1]+12)
    
    b = ax[1]
    b.add_patch(Polygon(tri, closed=True, facecolor=ORANGE, alpha=.15, edgecolor=NAVY, lw=2, label="三角形可行域"))
    b.add_patch(Circle((18, tri[2,1]/3), D/2, fill=False, color=GREY, lw=1.8, ls="--", label="直径圆 r=18 m"))
    b.add_patch(Circle((18, tri[2,1]/3), mec_r, fill=False, color=ORANGE, lw=2.2, label=f"最小包围圆 r={mec_r:.3f} m"))
    b.scatter([18], [tri[2,1]/3], color=ORANGE, s=22, zorder=4)
    b.annotate("MEC 圆心", (18, tri[2,1]/3), xytext=(8, 10), textcoords="offset points", color=ORANGE, fontsize=8)
    for label, p in zip("ABC", tri): b.scatter(*p, color=NAVY, s=18, zorder=4); b.annotate(label, p, xytext=(5, 4), textcoords="offset points", color=NAVY, weight="bold")
    b.set_title("(b) 直径圆不足，需用最小包围圆", color=NAVY, weight="bold")
    b.set_xlabel("x / m"); b.set_ylabel("y / m"); b.set_aspect("equal"); b.grid(alpha=.18)
    b.legend(loc="upper right", fontsize=7, frameon=False)
    b.set_xlim(-5, 41); b.set_ylim(-7, 40)
    fig.tight_layout(); save(fig, "geometry.pdf")


def lens_figure():
    alpha = math.radians(1.005); ts = np.linspace(0, 1000, 500)
    
    centers = np.array([(0., 0.), (1000*math.cos(alpha), 1000*math.sin(alpha)), (1000*math.cos(alpha), -1000*math.sin(alpha))])
    lim = 1030; gx = np.linspace(-30, lim, 700); gy = np.linspace(-530, 530, 500); X,Y=np.meshgrid(gx,gy)
    mask = np.ones_like(X, dtype=bool)
    for c in centers: mask &= (X-c[0])**2+(Y-c[1])**2 <= 1000**2
    fig, ax = plt.subplots(1, 2, figsize=(10.8, 4.8), gridspec_kw={"width_ratios":[1.12,1]})
    a=ax[0]; a.contourf(X,Y,mask,levels=[.5,1],colors=[ORANGE],alpha=.28)
    for c in centers: a.add_patch(Circle(c,1000,fill=False,color=NAVY,lw=1.2,alpha=.6))
    a.add_patch(Wedge((0,0),1000,-math.degrees(alpha),math.degrees(alpha),facecolor=TEAL,alpha=.10,edgecolor=TEAL,lw=1.2))
    a.plot([0,1000],[0,0],color=TEAL,lw=1.4,label="首次测向方向 theta_1=0 deg")
    a.scatter(0,0,color=NAVY,s=28,zorder=4); a.annotate("S1=(0,0)",(0,0),xytext=(7,8),textcoords="offset points",color=NAVY)
    a.set_title("(a) 全局：三圆交的安全候选域",color=NAVY,weight="bold"); a.set_xlabel("沿首次方向 / m"); a.set_ylabel("横向 / m"); a.set_aspect("equal"); a.grid(alpha=.18); a.legend(fontsize=7,frameon=False,loc="upper right"); a.set_xlim(-30,1030); a.set_ylim(-530,530)
    b=ax[1]; b.contourf(X,Y,mask,levels=[.5,1],colors=[ORANGE],alpha=.3)
    
    def bound(t): return min(math.sqrt(max(0,1000**2-t*t)), math.sqrt(max(0,1000**2-(t-1000*math.cos(alpha))**2))-1000*math.sin(alpha))
    valid=[t for t in ts if bound(t)>=0]
    b.plot(valid,[bound(t) for t in valid],color=ORANGE,lw=1.8,label="|b| <= b_max(t)"); b.plot(valid,[-bound(t) for t in valid],color=ORANGE,lw=1.8)
    for t in (125,250,375,500,625,750,875):
        bb=bound(t)
        for frac in (.25,.5,.75): b.scatter([t,t],[frac*bb,-frac*bb],s=10,color=TEAL,alpha=.7)
    b.scatter(750,-496.078,s=35,color=NAVY,zorder=5,label="示例候选 (750,-496.078)")
    b.scatter(750,0,s=28,color=GREY,zorder=5,label="共线对照 (750,0)")
    b.annotate("横向正/负候选",(500,250),xytext=(0,12),textcoords="offset points",ha="center",color=ORANGE)
    b.set_title("(b) 局部：(t,b) 横向候选与共线对照",color=NAVY,weight="bold"); b.set_xlabel("t / m（沿首次方向）"); b.set_ylabel("b / m（横向）"); b.set_aspect("equal"); b.grid(alpha=.18); b.legend(fontsize=7,frameon=False,loc="lower left"); b.set_xlim(-30,1030); b.set_ylim(-530,530)
    fig.tight_layout(); save(fig,"q2_lens.pdf")

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    geometry_figure(); lens_figure()
    print("wrote", OUT / "geometry.pdf", OUT / "q2_lens.pdf")
