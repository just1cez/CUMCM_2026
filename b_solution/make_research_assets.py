"""Generate checked research tables, vector figures and observable trajectories."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from coverage import directional_waypoints
from environment import LocalSimulator
from experiments import aggregate
from make_assets import atomic_bytes, table, save_figure, number, write_json, GENERATED, ROOT
from planner import Planner
from polar_coverage_candidate import polar_certificate, polar_waypoints
from refinement_study import paired

plt.rcParams.update({"font.size":10,"axes.labelsize":10,"legend.fontsize":9,
                     "pdf.fonttype":42,"ps.fonttype":42,"axes.spines.top":False,"axes.spines.right":False})
LABELS={"control":"原增强", "refined":"最终策略", "polar_only":"仅双环", "joint_all":"联合调度", 
        "optical":"条带光学", "joint_center":"中心联合", "joint_guarded":"半径联合",
        "joint_unknown":"中心联合+未知扫描", "joint_useful":"中心联合+筛选补测",
        "polar_seed":"双环990/1865", "polar_compact":"双环940/1870",
        "polar_joint":"双环+中心联合", "polar_guarded":"双环+半径联合",
        "polar_unknown":"双环联合+未知扫描", "polar_useful":"双环联合+筛选补测", "combined":"双环中心联合+条带"}


def checked_rows(data):
    assert data["total_runs"] == len(data["runs"])
    for row in data["runs"]:
        assert row["evidence"] == "local_synthetic_not_official"
        assert row["certificate_complete"] and row["timing_independently_verified"]
        assert row["n_cleared"] == row["n_sources"] and row["fraction_cleared"] == 1
        assert row["exit_reason"] == "user_exit"
        assert math.isclose(row["average_time_s"],row["virtual_time_s"]/row["n_cleared"],abs_tol=1e-9)
        cost=row["distance_m"]/5+5*row["measures"]+row["switches"]+3*row["failed_clears"]+5*row["n_cleared"]
        assert abs(cost-row["virtual_time_s"]) <= (row["measures"]+row["clear_attempts"])*.000001+1e-8
    return data["runs"]


def main_tables(data):
    groups=defaultdict(list)
    for row in checked_rows(data):
        if 4100000 <= row["seed"] <= 4100999:
            assert row["scenario"]=="random" and row["error_mode"]=="smooth"
            groups[row["problem"],row["configuration"]].append(row)
    comparison_rows=[];cost_rows=[];ablation_rows=[];macro=[]
    for problem,configs in data["configs"].items():
        problem=int(problem)
        for name in configs:
            current=sorted(groups[problem,name],key=lambda r:r["seed"])
            assert [row["seed"] for row in current]==list(range(4100000,4101000))
            assert aggregate(current)==data["summary"][f"Q{problem}_{name}"]
            s=aggregate(current)
            comparison_rows.append([f"Q{problem}",LABELS[name],number(s["mean_average_time_s"]),
                number(s["median_average_time_s"]),number(s["p90_average_time_s"]),
                number(s["worst_average_time_s"]),f'{s["all_cleared_cases"]}/{s["cases"]}'])
            if name in ("control","refined"):
                parts=[statistics.mean(row["distance_m"]/(5*row["n_sources"]) for row in current),
                       statistics.mean(5*row["measures"]/row["n_sources"] for row in current),
                       statistics.mean(row["switches"]/row["n_sources"] for row in current),
                       statistics.mean(3*row["failed_clears"]/row["n_sources"] for row in current),5.]
                cost_rows.append([f"Q{problem}",LABELS[name],*[number(v) for v in parts],number(s["mean_average_time_s"])])
        pair=paired(groups[problem,"control"],groups[problem,"refined"])
        assert pair==data["comparison"][f"Q{problem}"]
        word="Three" if problem==3 else "Four"
        macro.extend([(f"ResearchQ{word}Time",number(data["summary"][f"Q{problem}_refined"]["mean_average_time_s"])),
                      (f"ResearchQ{word}Gain",number(pair["reduction_pct"]))])
        macro.extend([(f"ResearchQ{word}Saved",number(pair["mean_saved_s_per_source"])),
                      (f"ResearchQ{word}Lower",number(pair["approx_95pct_ci_s"][0])),
                      (f"ResearchQ{word}Upper",number(pair["approx_95pct_ci_s"][1]))])
        for key,value in data["comparison"][f"Q{problem}_incremental"].items():
            a,b=key.split("_to_")
            assert paired(groups[problem,a],groups[problem,b])==value
            ablation_rows.append([f"Q{problem}",LABELS[a]+"至"+LABELS[b],number(value["mean_saved_s_per_source"]),
                f'[{number(value["approx_95pct_ci_s"][0])}, {number(value["approx_95pct_ci_s"][1])}]',f'{value["faster_cases"]}/1000'])
    macro.append(("ResearchRuns",str(data["total_runs"])))
    atomic_bytes(GENERATED/"research_numbers.tex",("\n".join("\\newcommand{\\"+k+"}{"+v+"}" for k,v in macro)+"\n").encode())
    table("research_comparison.tex",["问题","配置","均值","中位数","$p_{90}$","最坏","全清"],comparison_rows)
    table("research_costs.tex",["问题","配置","移动","检测","换频","失败","成功","合计"],cost_rows)
    table("research_ablation.tex",["问题","单步增量","节省均值",r"近似95\%区间","更快案例"],ablation_rows)
    return groups


def auxiliary_tables(data,development):
    scenario_labels={"minimum_radius":"最小半径","outward_boundary":"边界外向","clustered":"边缘聚集","random":"随机位置"}
    mode_labels={"smooth":"平滑","extreme":"端点","iid_location":"位置哈希"}
    pressure=[]
    for key,item in data["stress"].items():
        problem=int(key[1]);suffix=key[3:]
        scenario=next(s for s in scenario_labels if suffix.startswith(s+"_"))
        mode=suffix[len(scenario)+1:]
        control=[r for r in data["runs"] if r["problem"]==problem and r["scenario"]==scenario and r["error_mode"]==mode and r["configuration"]=="control" and 4200000<=r["seed"]<4220000]
        refined=[r for r in data["runs"] if r["problem"]==problem and r["scenario"]==scenario and r["error_mode"]==mode and r["configuration"]=="refined" and 4200000<=r["seed"]<4220000]
        assert aggregate(control)==item["control"] and aggregate(refined)==item["refined"]
        assert paired(control,refined)==item["paired"]
        pressure.append([f"Q{problem}",scenario_labels[scenario],mode_labels[mode],
            number(item["control"]["mean_average_time_s"]),number(item["refined"]["mean_average_time_s"]),
            number(item["paired"]["mean_saved_s_per_source"]),f'{item["paired"]["faster_cases"]}/{len(control)}'])
    table("research_stress.tex",["问题","位置场景","误差场","对照","最终","节省","更快"],pressure)
    sensitivities=[]
    for key,value in data["sensitivity"].items():
        p=int(key[1]);scale=float(key.split("_")[-1])
        current=[r for r in data["runs"] if r["problem"]==p and 4300000<=r["seed"]<4300050 and r["probe_scale"]==scale]
        assert aggregate(current)==value
        sensitivities.append([f"Q{p}",str(scale),number(value["mean_average_time_s"]),number(value["p90_average_time_s"]),f'{value["all_cleared_cases"]}/50'])
    table("research_sensitivity.tex",["问题","横偏移比例","均值","$p_{90}$","全清"],sensitivities)
    checked_rows(development)
    screens=[]
    for key,value in development["summary"].items():
        p=int(key[1]);name=key[3:]
        current=[r for r in development["runs"] if r["problem"]==p and r["configuration"]==name]
        assert len(current)==150
        screens.append([f"Q{p}",LABELS[name],number(value["mean_average_time_s"]),number(value["mean_saved_s_per_source"]),f'{value["all_cleared_cases"]}/150'])
    table("research_screen.tex",["问题","开发候选","均值","较对照节省","全清"],screens)


def coverage_figure():
    fig,axes=plt.subplots(1,2,figsize=(16/2.54,3.5),layout="constrained")
    for ax,points,label in zip(axes,[directional_waypoints(),polar_waypoints("compact25")],["Control: 31 lattice points","Refined: 25 polar points"]):
        points=np.asarray(points)
        ax.add_patch(plt.Circle((0,0),1800,fill=False,color="black",lw=1.4,label="Source disk"))
        ax.scatter(points[:,0],points[:,1],s=15,color="#0072B2",zorder=3)
        if "25" in label:
            for t in polar_certificate("compact25")["triangles_ccw"]:
                p=points[list(t)+[t[0]]]
                ax.plot(p[:,0],p[:,1],color="#56B4E9",lw=.5,alpha=.7)
        ax.set(xlim=(-2800,2800),ylim=(-2800,2800),xlabel="East (m)",ylabel="North (m)",title=label)
        ax.set_aspect("equal");ax.set_xticks([-2000,0,2000]);ax.set_yticks([-2000,0,2000]);ax.grid(alpha=.15)
    save_figure(fig,"research_coverage.pdf")


def performance_figure(groups):
    fig,axes=plt.subplots(1,2,figsize=(16/2.54,3.2),layout="constrained")
    for p,ax in zip((3,4),axes):
        for name,color in (("control","#0072B2"),("refined","#D55E00")):
            values=sorted(r["average_time_s"] for r in groups[p,name])
            ax.plot(values,np.arange(1,len(values)+1)/len(values),label="Control" if name=="control" else "Refined",color=color,lw=1.5)
        ax.set(xlabel="Total time / cleared source (s)",ylabel="Empirical cumulative probability",title=f"Q{p}: 1,000 paired worlds",ylim=(0,1))
        ax.legend(loc="lower right");ax.grid(alpha=.2)
    save_figure(fig,"research_performance.pdf")


def trajectories():
    fig,axes=plt.subplots(1,2,figsize=(16/2.54,3.8),layout="constrained")
    summaries={}
    for p,ax in zip((3,4),axes):
        environment=LocalSimulator(20260910,problem=p)
        planner=Planner(environment,problem=p)
        result=planner.run();truth_after_exit=environment.summary()
        assert result["strategy"]=="refined" and result["certificate_complete"]
        assert result["n_cleared"]==truth_after_exit["n_sources"]
        route=[(0.,0.)];clears=[]
        for event in environment.log:
            request,response=event["request"],event["response"]
            if response["accepted"] and "position" in request:
                point=(request["position"]["x"],request["position"]["y"])
                route.append(point)
                if response.get("clear_result")=="success":clears.append(point)
        route=np.asarray(route);clears=np.asarray(clears);anchors=np.asarray(planner.waypoints)
        ax.add_patch(plt.Circle((0,0),1800,fill=False,color="black",lw=1))
        ax.plot(route[:,0],route[:,1],color="#0072B2",lw=.65,alpha=.75,label="Accepted movement")
        ax.scatter(anchors[:,0],anchors[:,1],color="gray",s=12,marker="+",label="Discovery points")
        ax.scatter(clears[:,0],clears[:,1],color="#D55E00",s=18,marker="x",label="Successful clear positions")
        ax.set(xlim=(-2350,2350),ylim=(-2350,2350),xlabel="East (m)",ylabel="North (m)",title=f"Q{p}: T={result['virtual_time_s']:.1f} s")
        ax.set_aspect("equal");ax.set_xticks([-2000,0,2000]);ax.set_yticks([-2000,0,2000]);ax.grid(alpha=.15)
        evidence={"evidence":"observable_local_synthetic_trajectory_not_official","seed":20260910,
                  "planner":result,"post_exit_evaluation":truth_after_exit,"observable_log":environment.log}
        write_json(f"research_trajectory_q{p}.json",evidence)
        summaries[f"Q{p}"]={k:result[k] for k in ("n_cleared","virtual_time_s","average_time_s","certificate_complete")}
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="outside lower center",ncol=1,fontsize=8)
    save_figure(fig,"research_trajectories.pdf")
    return summaries


def main():
    data=json.loads((ROOT/"results/research_experiments.json").read_text())
    development=json.loads((ROOT/"results/refinement_development.json").read_text())
    assert data["total_runs"]==10700 and development["total_runs"]==2550
    groups=main_tables(data);auxiliary_tables(data,development)
    coverage_figure();performance_figure(groups);traces=trajectories()
    inputs=["results/research_experiments.json","results/refinement_development.json","results/research_verification.json",
            "planner.py","geometry.py","coverage.py","environment.py","polar_coverage_candidate.py",
            "joint_dispatch_candidate.py","make_research_assets.py","research_experiments.py","refinement_study.py"]
    write_json("research_metadata.json",{"evidence":data["evidence"],"official_calls":0,"total_runs":10700,
               "development_runs":2550,"input_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in inputs},
               "summary":data["summary"],"comparison":data["comparison"],"trajectory_summary":traces})
    print(json.dumps({"research_runs":10700,"development_runs":2550,"main_groups":len(groups),"trajectory_summary":traces},indent=2))


if __name__=="__main__":
    main()
