
from pathlib import Path
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report" / "figures"
NAVY, ORANGE, TEAL, GREY = "#12355B", "#E07A28", "#2A9D8F", "#607080"
plt.rcParams.update({"font.family":"sans-serif", "font.sans-serif":["Arial Unicode MS"], "font.size":10, "pdf.fonttype":42, "axes.unicode_minus":False})

def save(fig, name):
    fig.savefig(OUT/name, format="pdf", bbox_inches="tight", metadata={"Creator":"redraw_results.py"}); plt.close(fig)

def taskmap():
    fig, ax = plt.subplots(figsize=(10,3.2)); ax.axis("off"); ax.set_xlim(0,1); ax.set_ylim(0,1)
    ax.text(.5,.92,"四问依赖流程（原理示意）",ha="center",color=NAVY,weight="bold",fontsize=14)
    labs=[("Q1","几何边界\n可行域与交会"),("Q2","覆盖建模\n接收盘与光学"),("Q3","全向清除\n扫描—证书"),("Q4","定向定位\n测向—覆盖")]
    xs=[.08,.32,.56,.80]
    for i,(q,t) in enumerate(labs):
        p=FancyBboxPatch((xs[i],.37),.15,.29,boxstyle="round,pad=.02",fc="#F5F8FC",ec=NAVY,lw=1.8)
        ax.add_patch(p); ax.text(xs[i]+.075,.59,q,ha="center",color=ORANGE,weight="bold",fontsize=12); ax.text(xs[i]+.075,.47,t,ha="center",va="center",color=NAVY)
        if i<3: ax.add_patch(FancyArrowPatch((xs[i]+.16,.515),(xs[i+1]-.015,.515),arrowstyle="-|>",mutation_scale=15,lw=1.5,color=GREY))
    ax.text(.5,.15,"前一问输出作为后一问的约束与初始证书",ha="center",color=GREY,style="italic")
    save(fig,"competition_taskmap.pdf")

def dispatch():
    fig,ax=plt.subplots(figsize=(8,5.6)); ax.axis("off"); ax.set_xlim(0,1); ax.set_ylim(0,1)
    ax.text(.5,.96,"Q3/Q4 任务调度闭环（原理示意）",ha="center",color=NAVY,weight="bold",fontsize=14)
    nodes=[(.5,.83,"初始化\n候选骨架与频道"),(.5,.66,"骨架检测\n保留发现义务"),(.5,.49,"正观测建域\n更新可行多边形"),(.5,.32,"局部清除 / 光学兜底\n按证书执行"),(.5,.15,"更新频道证书\n记录清除或覆盖")]
    for x,y,t in nodes:
        ax.add_patch(FancyBboxPatch((x-.17,y-.045),.34,.09,boxstyle="round,pad=.015",fc="#F5F8FC",ec=NAVY,lw=1.5)); ax.text(x,y,t,ha="center",va="center",color=NAVY)
    for (_,y1,_),(_,y2,_) in zip(nodes,nodes[1:]): ax.add_patch(FancyArrowPatch((.5,y1-.055),(.5,y2+.055),arrowstyle="-|>",mutation_scale=13,color=ORANGE,lw=1.5))
    ax.add_patch(FancyArrowPatch((.32,.15),(.12,.83),connectionstyle="arc3,rad=-.28",arrowstyle="-|>",mutation_scale=14,color=TEAL,lw=1.8))
    ax.text(.06,.49,"未停止：\n重新选择任务",rotation=90,ha="center",va="center",color=TEAL)
    ax.text(.77,.57,"停止条件：每个频道已清除或\n覆盖认证缺失；或已清除16个不同频道",ha="center",va="center",color=GREY,fontsize=9,bbox=dict(boxstyle="round",fc="#FFF8F0",ec=ORANGE,alpha=.8))
    save(fig,"competition_dispatch.pdf")

def load_field(): return json.loads((ROOT/"results/field_confirmation.json").read_text(encoding="utf-8"))
def costs():
    runs=[r for r in load_field()["runs"] if 7100000<=r["seed"]<=7100999]; groups=[]
    for p,cfg in [(3,"control"),(3,"field"),(4,"control"),(4,"field")]:
        rr=[r for r in runs if r["problem"]==p and r["configuration"]==cfg]
        vals=[]
        for r in rr:
            n=r["n_sources"]; parts=np.array([r["distance_m"]/5,5*r["measures"],r["switches"],3*r["failed_clears"],5*r["n_cleared"]],float)/n
            assert abs(r["average_time_s"]-sum(parts)) < 2e-5
            vals.append(parts)
        groups.append((f"Q{p} {cfg}",np.mean(vals,axis=0)))
    a=np.array([v for _,v in groups]); fig,ax=plt.subplots(figsize=(9,4.8)); x=np.arange(4); bottom=np.zeros(4)
    cols=[NAVY,ORANGE,TEAL,"#C95D63","#8D99AE"]; labs=["移动 distance/5","测量 5×measures","换频 switches","失败清除 3×failed_clears","成功清除 5×n_cleared"]
    for j in range(5): ax.bar(x,a[:,j],bottom=bottom,color=cols[j],label=labs[j]); bottom+=a[:,j]
    ax.set_xticks(x,[g[0] for g in groups]); ax.set_ylabel("平均耗时 (s/source)"); ax.set_title("主组成本分解（6000行，按世界与源平均）",color=NAVY,weight="bold"); ax.legend(ncol=2,fontsize=8); ax.grid(axis="y",alpha=.2); save(fig,"competition_costs.pdf")

def field_performance():
    runs=load_field()["runs"]
    runs=[r for r in runs if 7100000<=r["seed"]<=7100999]
    fig,axs=plt.subplots(1,2,figsize=(10,4.3),sharey=False)
    for ax,p in zip(axs,[3,4]):
        c=sorted([r for r in runs if r["problem"]==p and r["configuration"]=="control"],key=lambda r:r["seed"]); f=sorted([r for r in runs if r["problem"]==p and r["configuration"]=="field"],key=lambda r:r["seed"])
        for rr,col,lab in [(c,NAVY,"control"),(f,ORANGE,"field")]:
            v=np.sort([r["average_time_s"] for r in rr]); ax.plot(v,np.linspace(.001,1,len(v)),color=col,lw=2,label=lab)
        d=np.array([x["average_time_s"]-y["average_time_s"] for x,y in zip(c,f)]); ax.text(.04,.08,f"1000对；field快 {np.sum(d>0):d}/1000\n均值差 {d.mean():.1f} s/source",transform=ax.transAxes,fontsize=9,color=TEAL)
        ax.set_title(f"Q{p}",color=NAVY,weight="bold"); ax.set_xlabel("逐世界平均耗时 (s/source)"); ax.set_ylabel("ECDF" ); ax.legend(); ax.grid(alpha=.2)
    fig.suptitle("field_confirmation：控制与field同世界配对",color=NAVY,weight="bold"); save(fig,"field_performance.pdf")

def research_performance():
    d=json.loads((ROOT/"results/research_experiments.json").read_text(encoding="utf-8")); s=d["summary"]; fig,ax=plt.subplots(figsize=(9,4.8)); keys=["Q3_control","Q3_joint_all","Q3_refined","Q4_control","Q4_joint_all","Q4_refined"]; labels=["Q3 control","Q3 joint_all","Q3 refined","Q4 control","Q4 joint_all","Q4 refined"]; vals=[s[k]["mean_average_time_s"] for k in keys]; cols=[GREY,TEAL,ORANGE,GREY,TEAL,ORANGE]; bars=ax.bar(labels,vals,color=cols); ax.set_ylabel("平均耗时 (s/source)"); ax.set_title("历史 refined 研究实验（非 field 数据）",color=NAVY,weight="bold"); ax.grid(axis="y",alpha=.2)
    for b,v in zip(bars,vals): ax.text(b.get_x()+b.get_width()/2,v+max(vals)*.015,f"{v:.1f}",ha="center",fontsize=9)
    ax.text(.02,.95,"输入：results/research_experiments.json 主组，1000 cases/problem",transform=ax.transAxes,va="top",color=GREY,fontsize=9); ax.tick_params(axis="x",rotation=18); save(fig,"research_performance.pdf")

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for f in (taskmap,dispatch,costs,field_performance,research_performance): f()
if __name__=="__main__": main()
