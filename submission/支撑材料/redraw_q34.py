
from pathlib import Path
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Wedge, FancyArrowPatch, Rectangle
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report" / "figures"
BLUE, ORANGE, GREEN, GREY, RED = "#123B66", "#E67E22", "#1B8A70", "#687480", "#B23A48"
plt.rcParams.update({"font.family":"sans-serif", "font.sans-serif":["Arial Unicode MS","Hiragino Sans GB","Heiti SC","DejaVu Sans"], "font.size":9, "pdf.fonttype":42, "axes.unicode_minus":False})

def finish(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT/name, format="pdf", metadata={"Creator":"CUMCM Q3/Q4 redraw_q34.py"})
    plt.close(fig)

def ring():
    fig, ax = plt.subplots(figsize=(7.2,6.0), layout="constrained")
    ax.set_aspect("equal"); ax.set_xlim(-2150,2150); ax.set_ylim(-2150,2150)
    ax.add_patch(Circle((0,0),1800, facecolor="#F4F7FA", edgecolor=BLUE, lw=1.8, ls="--", label="源域 R=1800 m"))
    a=np.arange(6)*np.pi/3; pts=np.c_[1200*np.cos(a),1200*np.sin(a)]
    for p in pts: ax.add_patch(Circle(p,1000,fill=False,edgecolor=ORANGE,lw=1.0,alpha=.62))
    ax.add_patch(Circle((0,0),1000,fill=False,edgecolor=ORANGE,lw=1.0,alpha=.62))
    ax.plot(*np.vstack([pts,pts[0]]).T,color=ORANGE,lw=1.4,alpha=.8)
    ax.scatter(pts[:,0],pts[:,1],s=38,color=ORANGE,zorder=4); ax.scatter(0,0,s=42,color=BLUE,zorder=4)
    for i,p in enumerate(pts): ax.text(p[0]*1.08,p[1]*1.08,f"P{i+1}",ha="center",va="center",color=BLUE,fontsize=8)
    ax.text(70,-120,"O",color=BLUE,fontsize=9)
    g=1800*np.array([math.cos(math.pi/6),math.sin(math.pi/6)]); near=pts[0]
    ax.scatter(*g,marker="x",s=70,color=RED,lw=2,zorder=6)
    ax.plot([g[0],near[0]],[g[1],near[1]],color=GREEN,lw=2)
    ax.annotate("最坏源点  g=(1800cos30°, 1800sin30°)",xy=g,xytext=(870,1780),arrowprops=dict(arrowstyle="->",color=RED,lw=1),color=RED,fontsize=8)
    ax.annotate("最近检测点 P1",xy=near,xytext=(1220,-210),arrowprops=dict(arrowstyle="->",color=GREEN,lw=1),color=GREEN,fontsize=8)
    mid=(g+near)/2; ax.text(mid[0]+30,mid[1]+25,"968.90 m",color=GREEN,fontsize=9,weight="bold")
    ax.text(-2050,-2020,"1000 m 接收圆；最坏距离余量 1000 - 968.90 = 31.10 m",color=BLUE,fontsize=8)
    ax.set_xlabel("x / m"); ax.set_ylabel("y / m"); ax.set_title("Q3 七点环覆盖（原理示意）",color=BLUE,weight="bold")
    ax.grid(alpha=.15); finish(fig,"competition_ring.pdf")

def localize():
    fig,axs=plt.subplots(1,2,figsize=(8.0,4.1),layout="constrained")
    ax=axs[0]; ax.set_aspect("equal"); ax.set_xlim(-25,310); ax.set_ylim(-115,125)
    s=np.array([0.,0.]); z=np.array([185.,0.]); delta=25.
    ax.add_patch(Polygon([[0,0],[295,75],[295,-75]],facecolor="#FBE9D7",edgecolor=ORANGE,lw=1.2))
    ax.plot([0,295],[0,0],"--",color=BLUE,lw=1.2)
    poly=np.array([[135,-25],[215,-35],[240,-8],[225,32],[145,28]])
    ax.add_patch(Polygon(poly,facecolor="#DFE8F1",edgecolor=BLUE,lw=1.6))
    ax.scatter(*s,color=BLUE,s=30); ax.text(-8,-18,r"$s^+$",color=BLUE)
    ax.scatter(*z,color=BLUE,s=24); ax.text(z[0]-17,-12,"z",color=BLUE)
    ax.scatter([z[0],z[0]],[delta,-delta],color=ORANGE,s=32,zorder=5)
    ax.plot([z[0],z[0]],[-delta,delta],color=ORANGE,lw=1.2)
    ax.add_patch(FancyArrowPatch((185,40),(185,83),arrowstyle="-|>",mutation_scale=12,color=BLUE,lw=1.4))
    ax.text(194,76,"n",color=BLUE); ax.text(195,36,r"$z+\delta n$",color=ORANGE); ax.text(195,-55,r"$z-\delta n$",color=ORANGE)
    ax.text(255,10,r"$P_c$",color=BLUE); ax.text(12,45,"正示向楔形",color=ORANGE,fontsize=8)
    ax.set_xlabel("局部 x / m"); ax.set_ylabel("局部 y / m")
    ax.set_title("(a) 横向候选点",color=BLUE,fontsize=10)
    ax=axs[1]; ax.set_aspect("equal"); ax.set_xlim(-15,115); ax.set_ylim(-20,95)
    
    ax.add_patch(Rectangle((0,0),100,75,facecolor="#F4F7FA",edgecolor=BLUE,lw=1.5))
    for v in (25,50,75): ax.plot([v,v],[0,75],color=GREY,alpha=.4,lw=.6)
    for v in (25,50): ax.plot([0,100],[v,v],color=GREY,alpha=.4,lw=.6)
    for y in (12.5,37.5,62.5):
        for x in (12.5,37.5,62.5,87.5):
            ax.add_patch(Circle((x,y),19.9,fill=False,edgecolor=ORANGE,lw=.9,alpha=.8)); ax.scatter(x,y,s=12,color=ORANGE,zorder=3)
    ax.plot([87.5,107.4],[62.5,62.5],color=BLUE,lw=1.3)
    ax.annotate("19.9 m",xy=(99,62.5),xytext=(63,85),arrowprops=dict(arrowstyle="-",color=BLUE,lw=.8),color=BLUE,fontsize=8)
    ax.set_xlabel("矩形坐标 x / m"); ax.set_ylabel("矩形坐标 y / m")
    ax.set_title("(b) 整个矩形的圆盘覆盖",color=BLUE,fontsize=10)
    fig.suptitle("局部定位与光学兜底（原理示意，非观测轨迹）",color=BLUE,fontsize=10)
    finish(fig,"competition_localize.pdf")

def direction():
    fig,axs=plt.subplots(1,2,figsize=(8.5,4.0),layout="constrained")
    ax=axs[0]; ax.set_aspect("equal"); ax.set_xlim(-2150,2150); ax.set_ylim(-2150,2150)
    ax.add_patch(Circle((0,0),1800,fill=False,color=BLUE,lw=1.3,ls="--"));
    ai=np.arange(12)*np.pi/6; ae=ai+np.pi/12
    I=np.c_[940*np.cos(ai),940*np.sin(ai)]; E=np.c_[1870*np.cos(ae),1870*np.sin(ae)]
    ax.scatter(I[:,0],I[:,1],s=20,color=ORANGE,label="内环 I（12点）"); ax.scatter(E[:,0],E[:,1],s=20,color=GREEN,label="外环 E（12点）"); ax.scatter(0,0,s=28,color=BLUE,label="O")
    g=1800*np.array([math.cos(np.pi/4),math.sin(np.pi/4)]); n=g/1800
    ax.scatter(*g,color=RED,marker="x",s=58,lw=2); ax.add_patch(FancyArrowPatch(g,g+650*n,arrowstyle="-|>",mutation_scale=14,color=RED,lw=2))
    ax.text(-2050,-2020,"25点：O + 内环12 + 外环12；外环点位于源域外",fontsize=7.8,color=BLUE)
    ax.text(730,1700,"前向",color=RED,fontsize=8); ax.text(-850,1350,"背面失效",color=GREY,fontsize=8)
    ax.set_title("定向源：距离条件还需满足 n dot (p-g) >= 0",color=BLUE,fontsize=8.5); ax.legend(fontsize=7,loc="lower left"); ax.set_xlabel("x / m"); ax.set_ylabel("y / m")
    ax=axs[1]; ax.set_aspect("equal"); ax.set_xlim(-1.25,1.35); ax.set_ylim(-1.05,1.1)
    tri=np.array([[-.9,-.62],[.88,-.58],[.05,.82]]); ax.add_patch(Polygon(tri,fill=False,color=BLUE,lw=1.7));
    g=np.array([-.25,.10]); n=np.array([.72,.22]); n=n/np.linalg.norm(n); h=g+0.42*n; c=tri.mean(0)
    ax.scatter(*g,color=RED,s=36); ax.scatter(*h,color=GREEN,s=36); ax.scatter(*c,color=GREY,s=28)
    ax.add_patch(FancyArrowPatch(g,h,arrowstyle="-|>",mutation_scale=12,color=GREEN,lw=1.8)); ax.plot([c[0],h[0]],[c[1],h[1]],"--",color=GREY,lw=1.2)
    ax.text(g[0]-.18,g[1]-.17,"g",color=RED); ax.text(h[0]+.04,h[1]+.04,"h=g+5n",color=GREEN,fontsize=8); ax.text(c[0]+.05,c[1],"重心投影",color=GREY,fontsize=8)
    ax.text(-1.15,-.92,"任意方向 -> 辅助点 h 属于三角形 -> 至少一个顶点前向",fontsize=7.8,color=BLUE)
    ax.set_title("三角形重心投影证明",color=BLUE,weight="bold"); ax.axis("off")
    fig.suptitle("Q4 方向覆盖（原理示意，非观测轨迹）",color=BLUE,weight="bold",fontsize=10)
    finish(fig,"competition_direction.pdf")

if __name__ == "__main__":
    ring(); localize(); direction()
